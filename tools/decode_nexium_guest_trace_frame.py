#!/usr/bin/env python3
"""Decode guest CRC-bound scene events from a real NeXium framebuffer PNG.

The source is a visual transport of post-join GUEST timestamps. It does
not establish DAC output timing or physical audio latency. No OCR and no
fallback to host PCM-file offset times.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
from audit_switch_guest_scene_trace import analyze_sd_csv, TraceError

COLS=112
ROWS=66
MODULE=7
PACKET_BYTES=924
CRC_OFFSET=909
MAGIC=b"VHFBTRC1"
EVENTS=("INPUT","POST","ACCEPT","SUBMIT_CALL","RELEASE_RETURN","SUBMIT_ERROR")
EXPECTED_SCENES=(2,1,2,1)

def encode_fixture(rows: list[tuple[int,int,int,int]], dropped=0) -> bytes:
    """Create host-only synthetic fixtures; NEVER substitute for guest evidence."""
    if len(rows)>64 or dropped<0 or dropped>0xffffffff:
        raise TraceError("invalid fixture row count/dropped")
    p=bytearray(PACKET_BYTES)
    p[:8]=MAGIC
    p[8]=len(rows)
    p[9:13]=dropped.to_bytes(4,"little")
    for i,(kind,scene,serial,ns) in enumerate(rows):
        if not 1<=kind<=6 or not 0<=scene<=2 or not 0<=serial<=0xffffffff or not 0<=ns<=0xffffffffffffffff:
            raise TraceError("invalid fixture event")
        off=13+i*14
        p[off]=kind
        p[off+1]=scene
        p[off+2:off+6]=serial.to_bytes(4,"little")
        p[off+6:off+14]=ns.to_bytes(8,"little")
    p[CRC_OFFSET:CRC_OFFSET+4]=(binascii.crc32(p[:CRC_OFFSET])&0xffffffff).to_bytes(4,"little")
    return bytes(p)

def decode_packet(p: bytes) -> dict:
    if len(p)!=PACKET_BYTES or p[:8]!=MAGIC:
        raise TraceError("optical payload length/magic invalid")
    count=p[8]
    dropped=int.from_bytes(p[9:13],"little")
    if not 1<=count<=64:
        raise TraceError("optical guest event count out of range")
    if any(p[13+count*14:CRC_OFFSET]) or any(p[CRC_OFFSET+4:]):
        raise TraceError("nonzero reserved/unused guest optical bytes")
    want=binascii.crc32(p[:CRC_OFFSET])&0xffffffff
    got=int.from_bytes(p[CRC_OFFSET:CRC_OFFSET+4],"little")
    if want!=got:
        raise TraceError("framebuffer packet CRC32 mismatch")
    lines=["index,event,serial,scene,monotonic_ns,dropped_total"]
    for idx in range(count):
        off=13+14*idx
        kind,scene=p[off],p[off+1]
        if not 1<=kind<=6 or scene>2:
            raise TraceError("invalid guest optical event kind or scene")
        serial=int.from_bytes(p[off+2:off+6],"little")
        ns=int.from_bytes(p[off+6:off+14],"little")
        lines.append(f"{idx},{EVENTS[kind-1]},{serial},{scene},{ns},{dropped}")
    csv_content="\n".join(lines)+"\n"
    audit=analyze_sd_csv(csv_content)
    # Reuse the strict canonical CSV parser without falsely claiming
    # the optical channel was read back from a guest SD file.
    # A separate CI comparison establishes SD provenance if available.
    audit["source"]="reconstructed from CRC-verified guest framebuffer pixels"
    audit["sd_readback_proven_by_optical_decode"]=False
    return {
        "schema":"vh-guest-optical-frame/v1",
        "transport":"post-join framebuffer pixel packet, not guest SD or stderr",
        "packet_sha256":hashlib.sha256(p).hexdigest(),
        "packet_crc32":f"{got:08x}",
        "event_rows":count,
        "dropped":dropped,
        "guest_trace_audit":audit,
        "canonical_guest_csv":csv_content,
        "hardware_status":"HARDWARE NOT TESTED",
        "actual_input_to_dac_latency_ms":None,
        "audible_music_confirmed":False
    }

def synthetic_image(packet: bytes) -> Image.Image:
    """Host-only fixture of the exact 1280x720 native render protocol."""
    if len(packet)!=PACKET_BYTES:
        raise TraceError("invalid synthetic image packet size")
    from PIL import ImageDraw
    im=Image.new("RGB",(1280,720),(0,0,0))
    dr=ImageDraw.Draw(im)
    left,top=250,160
    dr.rectangle((left,top,left+798-1,top+476-1),fill=(255,0,255))
    dr.rectangle((left+7,top+7,left+7+784-1,top+7+462-1),fill=(255,255,255))
    for i,value in enumerate(packet):
        for bit in range(8):
            if value & (0x80>>bit):
                offset=i*8+bit
                x,y=offset%COLS,offset//COLS
                px=left+7+x*MODULE
                py=top+7+y*MODULE
                dr.rectangle((px,py,px+MODULE-1,py+MODULE-1),
                             fill=(0,0,0))
    return im

def extract_packet(im: Image.Image) -> tuple[bytes,dict]:
    rgb=im.convert("RGB")
    width,height=rgb.size
    if width<680 or height<420 or width>8000 or height>8000:
        raise TraceError("invalid screenshot dimensions")
    pixels=rgb.load()
    bbox=[width,height,-1,-1]
    marker_pixels=0
    for y in range(height):
        for x in range(width):
            r,g,b=pixels[x,y]
            if r>=185 and b>=185 and g<=85:
                marker_pixels+=1
                bbox[0]=min(bbox[0],x)
                bbox[1]=min(bbox[1],y)
                bbox[2]=max(bbox[2],x)
                bbox[3]=max(bbox[3],y)
    if marker_pixels<700:
        raise TraceError("optical magenta calibration border absent")
    x0,y0,x1,y1=bbox
    w,h=x1-x0+1,y1-y0+1
    if w<500 or h<300 or abs(w/h-798/476)>0.11:
        raise TraceError("optical border dimensions/proportions invalid")
    # Four physical marker corners. The bbox is obtained from unique
    # magenta pixels, not a guessed emulator crop or a host timestamp.
    for xx,yy in ((x0+3,y0+3),(x1-3,y0+3),
                  (x0+3,y1-3),(x1-3,y1-3)):
        r,g,b=pixels[xx,yy]
        if not (r>=185 and b>=185 and g<=85):
            raise TraceError("optical corner fiducial damaged")
    data=bytearray(PACKET_BYTES)
    for bit_index in range(PACKET_BYTES*8):
        col=bit_index%COLS
        row=bit_index//COLS
        # 114x68 marker-inclusive optical modules. These centers
        # tolerate NeXium's nearest-neighbor scaling/letterboxing.
        px=x0+round((col+1.5)*w/(COLS+2))
        py=y0+round((row+1.5)*h/(ROWS+2))
        if not (0<=px<width and 0<=py<height):
            raise TraceError("sample outside screenshot")
        r,g,b=pixels[px,py]
        if min(r,g,b)>=177:
            value=0
        elif max(r,g,b)<=80:
            value=1
        else:
            raise TraceError(f"ambiguous optical bit at row={row}, col={col}")
        data[bit_index//8]|=value<<(7-bit_index%8)
    return bytes(data),{
        "image_width":width,"image_height":height,
        "border_bbox_xyxy":[x0,y0,x1,y1],
        "calibration_magenta_pixels":marker_pixels,
        "decoded_bits":PACKET_BYTES*8
    }

def analyze_image(im: Image.Image, *, require_four_scenes=False) -> dict:
    packet,calibration=extract_packet(im)
    report=decode_packet(packet)
    csv_content=report.pop("canonical_guest_csv")
    audit=report["guest_trace_audit"]
    report["calibration"]=calibration
    if require_four_scenes:
        serials=audit.get("complete_scene_serials",[])
        if (audit["result"]!="GUEST_INTERNAL_PHASES_OBSERVED"
            or audit["dropped"]!=0
            or audit["partial_scene_serials"]
            or len(serials)!=4
            or tuple(item["scene"] for item in serials)!=EXPECTED_SCENES):
            raise TraceError("not four complete guest-origin alternating scene transitions")
        report["result"]="FOUR_GUEST_SCENE_INTERNAL_PHASES_PIXELS_VERIFIED"
    else:
        report["result"]="OPTICAL_PACKET_DECODED"
    return report, csv_content

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--csv-output",type=Path)
    parser.add_argument("--require-four-scenes",action="store_true")
    args=parser.parse_args()
    try:
        if args.image.is_symlink():
            raise TraceError("refuse optical screenshot symlink")
        with Image.open(args.image) as im:
            report,csv_content=analyze_image(
                im,require_four_scenes=args.require_four_scenes)
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise TraceError("refuse to overwrite optical report")
        if args.csv_output:
            if args.csv_output.exists() or args.csv_output.is_symlink():
                raise TraceError("refuse to overwrite optical guest CSV")
        if args.csv_output:
            args.csv_output.write_text(csv_content,encoding="ascii")
        payload=json.dumps(report,indent=2)+"\n"
        if args.output:
            args.output.write_text(payload,encoding="utf-8")
        else:
            sys.stdout.write(payload)
    except (TraceError,OSError,UnicodeError,ValueError) as exc:
        print(json.dumps({"result":"OPTICAL_TRACE_NOT_VERIFIED",
                          "error":str(exc),
                          "hardware_status":"HARDWARE NOT TESTED"}),
              file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":
    raise SystemExit(main())
