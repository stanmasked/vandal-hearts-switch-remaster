#!/usr/bin/env python3
"""Original synthetic MIPS GP0 4bpp/8bpp CLUT STP/ABR, E2 vertical window.

All asset data are hand-constructed. No game, SDK, BIOS, retail GP0 or
retail textures. Actual raster verification happens in native PCSX.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,MARKER_VALUE,lui,ori,sw,addiu
from .make_map02_v74_indexed_clut_exe import upload,xy

MAGIC=b"VH75SYN!"
HEADER_SIZE=2048
SECTION_SIZE=4096
Y=104
PALETTE4=tuple({1:0x801f,2:0x03e0,3:0x03ff}.get(i,0) for i in range(16))
PALETTE8=tuple({17:0x801f}.get(i,0) for i in range(256))
# Each 16-bit 4bpp texel row carries four palette indices.
# U0..3 => 1 (STP red), U4..7 => 2 (opaque green).
# V8..11, U0..3 => 3 (opaque cyan) for E2 Y-window test.
TEXTURE4=tuple(value for v in range(12)
               for value in ((0x3333 if v>=8 else 0x1111),0x2222))
# 8bpp: U0..3 => STP red 17; U4..7 => transparent index 0.
TEXTURE8=tuple(value for v in range(4)
               for value in (0x1111,0x1111,0,0))
E2_VERTICAL=0xe2008020  # Y mask 1 (bit5), Y offset 1 (bit15)
REGIONS=(
    ("clut4_stp_abr0",40,0xbc0f),
    ("clut4_nonstp",56,0x03e0),
    ("clut8_stp_abr1",72,0xfc1f),
    ("clut8_transparent",88,0x7c00),
    ("e2_vertical_v8",104,0x03ff),
)
def ft4(x,clut,tpage,u,semi=True):
    cmd=0x2f000000 if semi else 0x2d000000
    return (cmd,xy(x,Y),(clut<<16)|u,
            xy(x+4,Y),(tpage<<16)|(u+4),
            xy(x,Y+4),(4<<8)|u,
            xy(x+4,Y+4),(4<<8)|(u+4))
def gp0_stream():
    words=[0xe3000000,0xe407ffff,0xe5000000,0xe6000000,
           0xe1000000,0xe2000000]
    words.extend(upload(0,0,2,12,TEXTURE4))
    words.extend(upload(64,0,4,4,TEXTURE8))
    words.extend(upload(512,0,16,1,PALETTE4))
    words.extend(upload(528,0,256,1,PALETTE8))
    # Five originally opaque blue 4x4 backdrops.
    for _,x,_ in REGIONS:
        words.extend((0x60ff0000,xy(x,Y),xy(4,4)))
    words.extend(ft4(40,32,0x000,0,True))       # 4bpp index1 STP -> average
    words.extend(ft4(56,32,0x000,4,True))       # same FT4 ABE, index2 STP=0
    words.extend(ft4(72,33,0x0a1,0,True))       # 8bpp STP red, ABR1 additive
    words.extend(ft4(88,33,0x081,4,True))       # 8bpp index0 transparent
    words.append(E2_VERTICAL)                   # source V0..3 becomes V8..11
    words.extend(ft4(104,32,0x000,0,False))    # 4bpp index3 -> cyan
    words.append(0xe2000000)                   # restore state
    return tuple(words)
GP0_SEQUENCE=gp0_stream()
def expected_pixel(x,y):
    if Y<=y<Y+4:
        for _,left,color in REGIONS:
            if left<=x<left+4:return color
    return 0
def build():
    ins=[lui(8,0x1f80),ori(8,8,0x1814),
         lui(9,0x0100),ori(9,9,0),sw(9,0,8),addiu(8,8,-4)]
    for word in GP0_SEQUENCE:
        ins.extend((lui(9,word>>16),ori(9,9,word&0xffff),sw(9,0,8)))
    ins.extend((lui(10,0x8001),ori(10,10,0x1000),
                lui(9,MARKER_VALUE>>16),ori(9,9,MARKER_VALUE&0xffff),
                sw(9,0,10)))
    end=START+4*len(ins)
    ins.extend(((2<<26)|((end>>2)&0x3ffffff),0))
    body=b"".join(struct.pack("<I",w) for w in ins)
    if len(body)>SECTION_SIZE:
        raise ValueError("synthetic MIPS fixture exceeds bounded load segment")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+body.ljust(SECTION_SIZE,b"\0"),end,tuple(ins)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    data,end,ins=build()
    if a.output.exists() or a.output.is_symlink():
        p.error("refuse overwriting existing or symlinked files")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(data)
    print("VH75_SYNTHETIC_PSX_EXE",len(data),"gpu_words",len(GP0_SEQUENCE),
          "mips_instructions",len(ins),"end_pc",hex(end),
          "sha256",hashlib.sha256(data).hexdigest())
    return 0
if __name__=="__main__":raise SystemExit(main())
