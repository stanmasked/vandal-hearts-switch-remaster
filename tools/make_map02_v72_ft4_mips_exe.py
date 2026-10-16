#!/usr/bin/env python3
"""Original synthetic MIPS PS-X EXE: GP0(A0) texture -> FT4 -> STP/ABR.

No game/BIOS/SDK input. Four rasterized 4x4 FT4 squares independently
verify opaque texture, bit15 selective semitransparency, and both ABR0
(average) and ABR1 (additive) at native PCSX GPU VRAM output.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,MARKER_VALUE,lui,ori,sw,addiu
HEADER_SIZE=2048
SECTION_SIZE=2048
MAGIC=b"VH72SYN!"
Y=32
TEX_RED=0x001f
TEX_STP_RED=0x801f
BACK_BLUE=0x7c00
# Note the upper left of the 4x4 rendered quads is x=64,80,96,112.
# Expected values are an independent PS1 BGR555 raster oracle, not
# inferred from plugin output.
SCENES=(
    ("opaque",64,0,False,0,0x001f),
    ("stp_abr0",80,4,True,0,0xbc0f),
    ("no_stp",96,0,True,0,0x001f),
    ("stp_abr1",112,4,True,1,0xfc1f),
)
def xy(x,y):return (y<<16)|x
def ft4(x,u,translucent,abr):
    # Raw 15bpp texture page 0 (bits 7..8 = 2), ABR in 5..6.
    tpage=0x100|(abr<<5)
    cmd=0x2f000000 if translucent else 0x2d000000
    return (
        cmd,xy(x,Y),u,
        xy(x+4,Y),(tpage<<16)|(u+4),
        xy(x,Y+4),(4<<8)|u,
        xy(x+4,Y+4),(4<<8)|(u+4),
    )
def texture_payload():
    # 8x4 texels: left four 0x001f, right four 0x801f.
    # A0 is 16-bit native VRAM upload, little-endian packed halfwords.
    row=(0x001f001f,0x001f001f,0x801f801f,0x801f801f)
    return row*4
def gp0_stream():
    commands=[
        0xe3000000,0xe407ffff,0xe5000000,0xe6000000,
        0xe1000100,           # 15bpp and ABR 0
        0xa0000000,0x00000000,xy(8,4),
        *texture_payload(),
    ]
    for name,x,u,semi,abr,expected in SCENES:
        commands.extend((0x60ff0000,xy(x,Y),xy(4,4))) # blue backdrop
    for name,x,u,semi,abr,expected in SCENES:
        commands.extend(ft4(x,u,semi,abr))
    return tuple(commands)
GP0_SEQUENCE=gp0_stream()
def expected_pixel(x,y):
    if Y<=y<Y+4:
        for _,left,_,_,_,color in SCENES:
            if left<=x<left+4:return color
    return 0
def build():
    words=[]
    # First GPU FIFO reset on GP1 as a real CPU store.
    words.extend((lui(8,0x1f80),ori(8,8,0x1814)))
    words.extend((lui(9,0x0100),ori(9,9,0),sw(9,0,8),addiu(8,8,-4)))
    for w in GP0_SEQUENCE:
        words.extend((lui(9,w>>16),ori(9,9,w&0xffff),sw(9,0,8)))
    words.extend((lui(10,0x8001),ori(10,10,0x1000),
                  lui(9,MARKER_VALUE>>16),ori(9,9,MARKER_VALUE&0xffff),
                  sw(9,0,10)))
    loop=START+4*len(words)
    words.extend(((2<<26)|((loop>>2)&0x03ffffff),0))
    body=b"".join(struct.pack("<I",x) for x in words)
    if len(body)>SECTION_SIZE:raise ValueError("synthetic MIPS program out of bounded PS-X EXE")
    head=bytearray(HEADER_SIZE)
    head[:8]=b"PS-X EXE"
    struct.pack_into("<I",head,0x10,START)
    struct.pack_into("<I",head,0x18,START)
    struct.pack_into("<I",head,0x1c,SECTION_SIZE)
    struct.pack_into("<I",head,0x30,0x801fff00)
    head[0x4c:0x54]=MAGIC
    return bytes(head)+body.ljust(SECTION_SIZE,b"\0"),loop,tuple(words)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    a=parser.parse_args()
    img,loop,code=build()
    if a.output.is_symlink() or a.output.exists():
        parser.error("refuse existing or symlinked output")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(img)
    print("V72_SYNTHETIC_PSX_EXE",len(img),"MIPS",len(code),
          "GP0",len(GP0_SEQUENCE),"loop",hex(loop),
          "sha256",hashlib.sha256(img).hexdigest())
    return 0
if __name__=="__main__":
    raise SystemExit(main())
