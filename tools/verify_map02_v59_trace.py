#!/usr/bin/env python3
"""v59: fail-closed audit of exact VHT1 original PC GPU trace, and full-frame replay.

The artifact is SYNTHETIC; traces with retail data must never be uploaded.
Validates each frame's LoadImage, PutDrawEnv, real TrcPrim code/type and
in-order E6/FT4 packets + full original native/2x byte-level hash roundtrip.
"""
from __future__ import annotations
import argparse
import json
import re
import struct
from pathlib import Path

E6=0xe6000000
FRAMES=[
    ("mark_skip",0x0010,(0,0,320,240),0,[(E6+1,0x001f,0),(E6+2,0x03e0,0)]),
    ("reopen",0x0010,(0,0,320,240),0,[(E6+1,0x001f,0),(E6+2,0x03e0,0),
                                     (E6+0,0x7c00,0),(E6+2,0x03e0,0)]),
    ("stp_abr2",0x0010,(0,0,320,240),2,[(E6+1,0x001f,0),(E6+0,0x7c00,0),
                                       (E6+2,0x83e0,1)]),
    ("clip_mask",0x0010,(75,74,10,12),0,[(E6+1,0x001f,0),(E6+3,0x83e0,1)])
]
TOTAL_MASK=sum(len(f[4]) for f in FRAMES)
FNV_RE=re.compile(r"^V59FRAME phase=(record|replay) frame=([0-9]+) nativehash=([a-f0-9]{16}) hihash=([a-f0-9]{16})$")
REPLAY_RE=re.compile(r"^REPLAY frames=([0-9]+) combined=([a-f0-9]{16})$")
class BadTrace(ValueError):pass

def parse_vht(data:bytes):
    if not data.startswith(b"VHT1"):raise BadTrace("invalid VHT1 magic")
    result=[]
    offset=4
    while offset<len(data):
        if len(data)-offset<9:raise BadTrace("truncated VHT1 record header")
        op=data[offset:offset+1]
        offset+=1
        (na,)=struct.unpack_from("<I",data,offset)
        offset+=4
        if na>64 or offset+na+4>len(data):raise BadTrace("invalid VHT1 first payload")
        a=data[offset:offset+na];offset+=na
        (nb,)=struct.unpack_from("<I",data,offset)
        offset+=4
        if nb>8192 or offset+nb>len(data):raise BadTrace("invalid VHT1 second payload")
        b=data[offset:offset+nb];offset+=nb
        if op not in (b"L",b"E",b"P",b"Z"):raise BadTrace("unexpected GPU trace operation")
        result.append((op,a,b))
    return result

def check_packet(item,typ,expected_command=None,step=0,semi=0,abr=0):
    op,a,b=item
    if op!=b"P" or len(a)!=4:raise BadTrace("missing real primitive trace")
    (seen,)=struct.unpack("<I",a)
    if seen!=typ:raise BadTrace("OT primitive type/order changed")
    sizes={5:12,6:12,2:40,4:16}
    if len(b)!=sizes[typ]:raise BadTrace("OT primitive serialized size mismatch")
    if typ==6:
        if b[7]!=6:raise BadTrace("mask OT primitive code changed")
        (cmd,)=struct.unpack_from("<I",b,8)
        if cmd!=expected_command:raise BadTrace("E6 mask command changed or moved")
    if typ==2:
        if b[7]!=(2 | (0x80 if semi else 0)):
            raise BadTrace("FT4 semi/primitive GPU code changed")
        if (b[12],b[13])!=(20+step,192):
            raise BadTrace("FT4 texture source UV changed")
        (tpage,)=struct.unpack_from("<H",b,22)
        if (tpage>>5)&3!=abr:raise BadTrace("FT4 ABR state changed")
        x0,y0=struct.unpack_from("<hh",b,8)
        if (x0,y0)!=(70,70):raise BadTrace("FT4 geometry changed")
    if typ==4:
        if b[7]!=4:raise BadTrace("filler TILE code changed")

def audit_trace(blob:bytes):
    records=parse_vht(blob)
    at=0
    for index,(name,bg,clip,abr,steps) in enumerate(FRAMES):
        if at+4>=len(records):raise BadTrace("missing GPU frame")
        for upload in range(2):
            op,a,b=records[at];at+=1
            if op!=b"L" or len(a)!=8:raise BadTrace("missing real VRAM upload")
            rect=struct.unpack("<hhhh",a)
            if upload==0:
                if rect!=(64,64,48,48) or b!=struct.pack("<H",bg)*(48*48):
                    raise BadTrace(f"{name}: wrong uploaded framebuffer/background")
            else:
                if rect!=(468,192,4,1):
                    raise BadTrace(f"{name}: wrong uploaded 15bpp source position")
                pixels=[s[1] for s in steps]+[0]*(4-len(steps))
                if b!=struct.pack("<4H",*pixels):
                    raise BadTrace(f"{name}: changed real source texels")
        op,a,b=records[at];at+=1
        if op!=b"E" or len(a)!=0 or len(b)<24:
            raise BadTrace(f"{name}: missing PutDrawEnv trace")
        if struct.unpack_from("<hhhh",b,0)!=clip:
            raise BadTrace(f"{name}: drawing area changed")
        check_packet(records[at],5);at+=1
        for j,(cmd,tex,semi) in enumerate(steps):
            check_packet(records[at],6,expected_command=cmd);at+=1
            check_packet(records[at],2,step=j,semi=semi,abr=abr);at+=1
        for j in range(64):
            check_packet(records[at],4);at+=1
        if at>=len(records) or records[at]!=(b"Z",b"",b""):
            raise BadTrace(f"{name}: missing frame end/Z")
        at+=1
    if at!=len(records):raise BadTrace("unexpected extra frame or trace tail")
    return {
        "status":"synthetic_vht1_ot_verified",
        "frames":len(FRAMES),
        "gpu_mask_packets":TOTAL_MASK,
        "gpu_quad_packets":TOTAL_MASK,
        "gpu_filler_packets":64*len(FRAMES),
        "trace_operations":len(records),
        "genuine_retail_gpu_packets_proven":False,
        "HD_replacement_approved":False
    }

def parse_frames(log:str,phase:str):
    rows={}
    for line in log.splitlines():
        m=FNV_RE.fullmatch(line)
        if not m:continue
        kind,num,native,hd=m.groups()
        i=int(num)
        if kind!=phase or i in rows:raise BadTrace("incorrect or duplicated actual framebuffer log")
        rows[i]=(native,hd)
    if set(rows)!=set(range(len(FRAMES))):
        raise BadTrace(f"{phase}: missing actual recorded or replayed framebuffer hashes")
    return rows

def verify(blob,record,workers):
    result=audit_trace(blob)
    original=parse_frames(record,"record")
    replay_hashes={}
    combined=[]
    for w in (1,2,4):
        if w not in workers:raise BadTrace("all 1/2/4 worker replays required")
        log=workers[w]
        rows=parse_frames(log,"replay")
        for i in range(len(FRAMES)):
            if rows[i]!=original[i]:
                raise BadTrace(f"frame={i} real replay differs from actual original recording at workers={w}")
        tokens=[REPLAY_RE.fullmatch(line) for line in log.splitlines()]
        tokens=[m for m in tokens if m is not None]
        if len(tokens)!=1 or int(tokens[0].group(1))!=len(FRAMES):
            raise BadTrace("original PC_GpuReplayTrace did not finish expected frames")
        combined.append(tokens[0].group(2))
        replay_hashes[str(w)]=rows
    if len(set(combined))!=1:raise BadTrace("combined original GPU replay signature changes with workers")
    result.update({
        "status":"original_vht1_e6_roundtrip_verified",
        "threads_checked":[1,2,4],
        "original_trace_record_replay_frames":len(FRAMES)*3,
        "independent_full_frame_native_hash_equalities":len(FRAMES)*3,
        "independent_full_frame_hd_hash_equalities":len(FRAMES)*3,
        "original_replay_combined_hash":combined[0],
        "genuine_retail_gpu_packets_proven":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False
    })
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("trace",type=Path)
    ap.add_argument("record",type=Path)
    ap.add_argument("replay1",type=Path)
    ap.add_argument("replay2",type=Path)
    ap.add_argument("replay4",type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    try:
        out=verify(args.trace.read_bytes(),args.record.read_text(),
                   {1:args.replay1.read_text(),2:args.replay2.read_text(),4:args.replay4.read_text()})
    except (OSError,BadTrace) as err:
        out={"status":"refused","errors":[str(err)],"HD_replacement_approved":False}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps(out,sort_keys=True))
    return 0 if out["status"]=="original_vht1_e6_roundtrip_verified" else 1

if __name__=="__main__":
    raise SystemExit(main())
