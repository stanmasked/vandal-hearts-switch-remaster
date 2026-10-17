#!/usr/bin/env python3
"""Original self-authored PS-X EXE: MIPS GP0 4x4 A-B-C-D-A return.

Stage 0 configures GPU draw-area/mask through interpreted MIPS GP0 stores.
Stages 1..5 each use MIPS SW to send exactly one GP0(60) rectangle, then
write distinct RAM markers and jump to the next bounded stage. Only
the authenticated pinned PCSX host oracle controls ExecuteBlock boundaries.
No retail game data, SDK, copied instructions or host GP0 submission.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw

MAGIC=b"VH121SY!"
HEADER_SIZE=2048
SECTION_SIZE=4096
MARKER_ADDR=0x80011100
COLORS=(0x600000ff,0x6000ff00,0x60ff0000,0x6000ffff,0x600000ff)
EXPECTED_PIXELS=(0x001f,0x03e0,0x7c00,0x03ff,0x001f)
MARKERS=tuple(0x12100000+i for i in range(6))
SETUP=(0xe3000000,0xe407ffff,0xe5000000,
       0xe6000000,0xe1000000,0xe2000000)
RECT_XY=(160<<16)|40
RECT_SIZE=(4<<16)|4


def gpu_writes(words):
    instructions=[]
    for word in words:
        instructions.extend((lui(9,word>>16),ori(9,9,word&0xffff),
                             sw(9,0,8)))
    return instructions


def stage_body(index):
    commands=(SETUP if index==0
              else (COLORS[index-1],RECT_XY,RECT_SIZE))
    body=[lui(8,0x1f80),ori(8,8,0x1810)]
    body.extend(gpu_writes(commands))
    # Marker is authored by the interpreted CPU, never a host-assigned
    # synthetic success bit or a RAM value supplied in advance.
    marker=MARKERS[index]
    body.extend((lui(10,0x8001),ori(10,10,0x1100+4*index),
                 lui(9,marker>>16),ori(9,9,marker&0xffff),sw(9,0,10)))
    return tuple(body)


def build():
    bodies=tuple(stage_body(i) for i in range(6))
    starts=[START]
    for body in bodies[:-1]:
        starts.append(starts[-1]+(len(body)+2)*4)
    stops=[]
    ops=[]
    for index,body in enumerate(bodies):
        dest=starts[index+1] if index<5 else starts[index]+len(body)*4
        stops.append(dest)
        ops.extend(body)
        # Jump to the next stage (last stage self-loops); one delay-slot NOP.
        ops.extend(((2<<26)|((dest>>2)&0x03ffffff),0))
    payload=b"".join(struct.pack("<I",word) for word in ops)
    if len(payload)>SECTION_SIZE:
        raise ValueError("MIPS stage program exceeds bounded PS-X load region")
    hdr=bytearray(HEADER_SIZE)
    hdr[:8]=b"PS-X EXE"
    struct.pack_into("<I",hdr,0x10,START)
    struct.pack_into("<I",hdr,0x18,START)
    struct.pack_into("<I",hdr,0x1c,SECTION_SIZE)
    struct.pack_into("<I",hdr,0x30,0x801fff00)
    hdr[0x4c:0x54]=MAGIC
    return (bytes(hdr)+payload.ljust(SECTION_SIZE,b"\0"),
            tuple(stops),tuple(ops),tuple(starts))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    data,stops,ops,_=build()
    if args.output.exists() or args.output.is_symlink():
        parser.error("refuse overwrite of any existing or linked EXE")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("VH121_SYNTHETIC_MIPS_GP0_EXE",
          "bytes",len(data),"ops",len(ops),
          "stop_pc",[hex(pc) for pc in stops],
          "sha256",hashlib.sha256(data).hexdigest())
    return 0


if __name__=="__main__":
    raise SystemExit(main())
