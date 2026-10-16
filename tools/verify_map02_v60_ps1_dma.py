#!/usr/bin/env python3
"""v60 bounded *hardware-format* PS1 GPU DMA2 linked-list and GP0 parser.

This is NOT the PC-port's VHT1 format. Parses a caller-supplied raw, little-
endian RAM slice plus an explicit address/entry-point manifest. Deliberately
restricted GP0 subset: abort unsupported opcodes rather than scanning data
words for E6 or inventing command boundaries. Never self-certifies retail
origin from bytes or user-supplied metadata alone.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from .verify_map02_v59_trace import parse_vht

class DmaError(ValueError):
    pass

MAX_RAM=4*1024*1024
MAX_NODES=4096
MAX_COMMANDS=65536
MAX_FRAMES=256
FORMAT="ps1-dma2-linked-list-ram-v1"
MANIFEST_KEYS={"format","source_class","base_address","entry_points","sha256"}

def manifest_check(data:bytes, manifest:dict):
    if not isinstance(manifest,dict) or set(manifest)!=MANIFEST_KEYS:
        raise DmaError("missing/extra mandatory manifest fields")
    if manifest["format"]!=FORMAT:
        raise DmaError("not a PS1 GPU DMA2 linked-list RAM format")
    if manifest["source_class"] not in ("synthetic","user-supplied-unverified"):
        raise DmaError("untrusted or unsupported provenance status")
    if not data or len(data)>MAX_RAM or len(data)%4:
        raise DmaError("RAM image is empty, unaligned, or too large")
    if data[:4]==b"VHT1":
        raise DmaError("custom PC-port VHT1 file is NOT raw PS1 DMA RAM")
    base=manifest["base_address"]
    if type(base)!=int or base<0 or base>0xffffff or base%4 or base+len(data)>0x1000000:
        raise DmaError("misaligned/out-of-range RAM base")
    points=manifest["entry_points"]
    if not isinstance(points,list) or not 1<=len(points)<=MAX_FRAMES or any(
            type(p)!=int or p%4 or p<base or p+4>base+len(data) for p in points):
        raise DmaError("invalid entry point or frame count")
    digest=manifest["sha256"]
    if not isinstance(digest,str) or len(digest)!=64 or not all(c in "0123456789abcdef" for c in digest):
        raise DmaError("invalid lower-case SHA256")
    if hashlib.sha256(data).hexdigest()!=digest:
        raise DmaError("RAM bytes differ from declared source SHA256")

def walk_dma(data:bytes, base:int, entry:int):
    address=entry
    seen=set()
    words=[]
    nodes=[]
    while True:
        if address in seen:raise DmaError("DMA2 linked-list cycle / duplicate node")
        if len(seen)>=MAX_NODES:raise DmaError("too many OT nodes")
        seen.add(address)
        off=address-base
        if off<0 or off+4>len(data) or off%4:
            raise DmaError("out-of-bounds / misaligned linked-list address")
        (header,)=struct.unpack_from("<I",data,off)
        count=header>>24
        link=header&0xffffff
        end=off+4+count*4
        if end>len(data):raise DmaError("truncated DMA node payload")
        words.extend(struct.unpack_from("<"+str(count)+"I",data,off+4) if count else ())
        if len(words)>MAX_COMMANDS*9:raise DmaError("excessive DMA GP0 words")
        nodes.append({"address":address,"words":count,"next":link})
        if link==0xffffff:break
        if link%4:raise DmaError("misaligned next DMA2 linked-list pointer")
        address=link
    return words,nodes

# GP0 commands do not necessarily align to DMA linked-list node boundaries.
# Length is defined by *the actual GP0 opcode*, not occurrences of 0xE6 in
# unrelated payload data. Unsupported variable-length opcodes refuse closed.
def parse_gp0(words:list[int], initial_mask:tuple[int,int]=(0,0), return_state:bool=False):
    """Parse GP0 words; optionally carry persistent E6 state across DMA lists.

    GP0(E6) persists until another E6 or an external GPU reset. Separate
    captures MUST NOT be concatenated without evidence about GPU resets.
    """
    if not (isinstance(initial_mask,tuple) and len(initial_mask)==2
            and all(type(x)==int and x in (0,1) for x in initial_mask)):
        raise DmaError("invalid initial E6 state")
    events=[]
    pos=0
    mask_set,mask_check=initial_mask
    while pos<len(words):
        command=words[pos]
        opcode=command>>24
        if opcode in (0x00,0x01,0xe1,0xe2,0xe3,0xe4,0xe5,0xe6):
            count=1
        elif 0x20<=opcode<=0x23:count=4    # flat triangle
        elif 0x28<=opcode<=0x2b:count=5    # flat quad
        elif 0x24<=opcode<=0x27:count=7    # flat textured triangle
        elif 0x2c<=opcode<=0x2f:count=9    # flat textured quad
        elif 0x60<=opcode<=0x63:count=3    # solid rectangle (variable width/height)
        elif 0x64<=opcode<=0x67:count=4    # textured rectangle
        else:raise DmaError(f"unsupported GP0 opcode 0x{opcode:02x} at word {pos}; no fuzzy E6 scan")
        if pos+count>len(words):
            raise DmaError("GP0 command truncated across DMA stream")
        pack=words[pos:pos+count]
        if opcode==0xe6:
            if command&0xfffffc:
                raise DmaError("GP0(E6) reserved bits nonzero")
            mask_set=command&1
            mask_check=(command>>1)&1
            events.append({"type":"E6","word":command,"set":mask_set,
                           "check":mask_check})
        elif 0x2c<=opcode<=0x2f:
            x0=struct.unpack("<h",struct.pack("<H",pack[1]&0xffff))[0]
            y0=struct.unpack("<h",struct.pack("<H",(pack[1]>>16)&0xffff))[0]
            events.append({"type":"FT4","opcode":opcode,
                           "x0":x0,"y0":y0,"u0":pack[2]&255,
                           "v0":(pack[2]>>8)&255,
                           "tpage":(pack[4]>>16)&0xffff,
                           "semi":(opcode>>1)&1,
                           "mask_set":mask_set,"mask_check":mask_check})
        elif 0x20<=opcode<=0x2f or 0x60<=opcode<=0x67:
            events.append({"type":f"DRAW_{opcode:02X}","mask_set":mask_set,
                           "mask_check":mask_check})
        elif opcode in (0xe1,0xe2,0xe3,0xe4,0xe5):
            events.append({"type":f"E{opcode&15}","word":command})
        pos+=count
    return (events,(mask_set,mask_check)) if return_state else events

def decode(data:bytes, manifest:dict):
    manifest_check(data,manifest)
    frames=[]
    total_nodes=0
    mask_state=(0,0)
    for head in manifest["entry_points"]:
        words,nodes=walk_dma(data,manifest["base_address"],head)
        events,mask_state=parse_gp0(words,initial_mask=mask_state,return_state=True)
        if not events:raise DmaError("no GPU events in one frame")
        total_nodes+=len(nodes)
        frames.append({"head":head,"nodes":nodes,"events":events,
                       "gp0_words":len(words),"mask_state_at_end":mask_state})
    return {"source_class":manifest["source_class"],
            "sha256":manifest["sha256"],
            "frames":frames,"total_nodes":total_nodes,
            "mask_commands":sum(sum(e["type"]=="E6" for e in f["events"]) for f in frames),
            "gp0_ft4":sum(sum(e["type"]=="FT4" for e in f["events"]) for f in frames),
            "retail_gp0_provenance_verified":False,
            "HD_replacement_approved":False}

def vht1_semantic_frames(data:bytes):
    """Read synthetic v59 PC-port trace as DIFFERENT format; compare meaning only."""
    records=parse_vht(data)
    frames=[]
    current=[]
    for op,a,b in records:
        if op==b"P":
            if len(a)!=4:raise DmaError("invalid VHT1 primitive type header")
            typ=struct.unpack("<I",a)[0]
            if typ==6:
                if len(b)!=12:raise DmaError("invalid VHT1 mask primitive")
                current.append({"type":"E6","word":struct.unpack_from("<I",b,8)[0]})
            elif typ==2:
                if len(b)!=40:raise DmaError("invalid VHT1 FT4 primitive")
                x,y=struct.unpack_from("<hh",b,8)
                current.append({"type":"FT4","x0":x,"y0":y,"u0":b[12],"v0":b[13],
                                "tpage":struct.unpack_from("<H",b,22)[0],
                                "semi":1 if b[7]&0x80 else 0})
        elif op==b"Z":
            frames.append(current)
            current=[]
    if current:raise DmaError("missing terminal VHT1 Z")
    return frames

def compare_formats(decoded:dict, vht:bytes):
    older=vht1_semantic_frames(vht)
    if len(older)!=len(decoded["frames"]):raise DmaError("frame count differs across *different* formats")
    for i,(f,expected) in enumerate(zip(decoded["frames"],older)):
        actual=[]
        for e in f["events"]:
            if e["type"]=="E6":actual.append({"type":"E6","word":e["word"]})
            if e["type"]=="FT4":
                actual.append({k:e[k] for k in ("type","x0","y0","u0","v0","tpage","semi")})
        if actual!=expected:
            raise DmaError(f"frame {i}: raw PS1 GP0 semantic order differs from PC-port VHT1")
    return {
        "status":"synthetic_cross_format_semantic_order_verified",
        "frames":len(older),
        "retail_gp0_provenance_verified":False,
        "retail_MAP02_verified":False,
        "HD_replacement_approved":False
    }

def audit(data:bytes, manifest:dict, vht:bytes|None=None):
    decoded=decode(data,manifest)
    result={
        "status":"raw_ps1_dma_structure_only",
        "input_sha256":decoded["sha256"],
        "source_class":decoded["source_class"],
        "frames":len(decoded["frames"]),
        "dma_nodes":decoded["total_nodes"],
        "gp0_e6_words":decoded["mask_commands"],
        "gp0_ft4_commands":decoded["gp0_ft4"],
        "retail_gp0_provenance_verified":False,
        "retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }
    if vht is not None:
        result.update(compare_formats(decoded,vht))
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ram",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--vht1",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    try:
        manifest=json.loads(args.manifest.read_text())
        report=audit(args.ram.read_bytes(),manifest,
                     args.vht1.read_bytes() if args.vht1 else None)
    except (ValueError,DmaError,OSError,struct.error,TypeError) as e:
        report={"status":"refused","errors":[str(e)],
                "retail_gp0_provenance_verified":False,
                "HD_replacement_approved":False}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
    return 1 if report["status"]=="refused" else 0

if __name__=="__main__":
    raise SystemExit(main())
