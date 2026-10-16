#!/usr/bin/env python3
"""v73 synthetic PS-X EXE: non-identity UV, tpage X base and textured FT3 seam.

Every GPU input word is authored from scratch, not retail game content.
Real PCSX MIPS/GPU pixel output is compared separately with a fixed oracle.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,MARKER_VALUE,lui,ori,sw,addiu
MAGIC=b"VH73SYN!"
HEADER_SIZE=2048
SECTION_SIZE=2048
Y=56
STRIPES=(0x001f,0x03e0,0x7c00,0x7fff,0x001f,0x03e0,0x7c00,0x7fff)
PAGE1=(0x03ff,0x7fe0,0x7c1f,0x4210)
STP_RED=0x801f
def xy(x,y):return (y<<16)|x
def packed(words):
    if len(words)%2:raise ValueError("odd texel count")
    return tuple(words[i] | (words[i+1]<<16) for i in range(0,len(words),2))
def upload(x,pixels):
    width=len(pixels)
    assert width in (4,8)
    return (0xa0000000,xy(x,0),xy(width,4),
            *packed(pixels*4))
def ft4(x,tpage,u0,u1):
    return (0x2d000000,xy(x,Y),u0,
            xy(x+4,Y),(tpage<<16)|u1,
            xy(x,Y+4),(4<<8)|u0,
            xy(x+4,Y+4),(4<<8)|u1)
def ft3(vertices,uv,tpage):
    assert len(vertices)==len(uv)==3
    return (0x27000000,
            xy(*vertices[0]),uv[0][0]|(uv[0][1]<<8),
            xy(*vertices[1]),(tpage<<16)|uv[1][0]|(uv[1][1]<<8),
            xy(*vertices[2]),uv[2][0]|(uv[2][1]<<8))
def stream():
    cmds=[0xe3000000,0xe407ffff,0xe5000000,0xe6000000,0xe1000100]
    cmds.extend(upload(0,STRIPES))
    cmds.extend(upload(64,PAGE1))
    cmds.extend(upload(128,(STP_RED,)*4))
    # Texture page 0 uses U 0..8 sampled on four destination pixels,
    # page1 uses the same UV 0..4 but a distinct VRAM x=64 page base.
    cmds.extend(ft4(40,0x100,0,8))
    cmds.extend(ft4(72,0x101,0,4))
    # The FT3 pair must rasterize a four-by-four region exactly ONCE.
    # Semi-transparent STP texels reveal both overdraw and cracks.
    cmds.extend((0x60ff0000,xy(88,Y),xy(4,4)))  # blue underlying fill
    cmds.extend(ft3(((88,Y),(92,Y),(88,Y+4)),((0,0),(4,0),(0,4)),0x102))
    cmds.extend(ft3(((92,Y),(92,Y+4),(88,Y+4)),((4,0),(4,4),(0,4)),0x102))
    return tuple(cmds)
GP0_SEQUENCE=stream()
def expected_pixel(x,y):
    if Y<=y<Y+4:
        if 40<=x<44:return STRIPES[(x-40)*2]
        if 72<=x<76:return PAGE1[x-72]
        if 88<=x<92:return 0xbc0f
    return 0
def build():
    ins=[lui(8,0x1f80),ori(8,8,0x1814),
         lui(9,0x0100),ori(9,9,0),sw(9,0,8),addiu(8,8,-4)]
    for w in GP0_SEQUENCE:
        ins.extend((lui(9,w>>16),ori(9,9,w&0xffff),sw(9,0,8)))
    ins.extend((lui(10,0x8001),ori(10,10,0x1000),
                lui(9,MARKER_VALUE>>16),ori(9,9,MARKER_VALUE&0xffff),
                sw(9,0,10)))
    end=START+4*len(ins)
    ins.extend(((2<<26)|((end>>2)&0x03ffffff),0))
    raw=b"".join(struct.pack("<I",w) for w in ins)
    if len(raw)>SECTION_SIZE:raise ValueError("bounded synthetic EXE overflow")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+raw.ljust(SECTION_SIZE,b"\0"),end,tuple(ins)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    binary,pc,ins=build()
    if a.output.is_symlink() or a.output.exists():
        p.error("refuse overwrite of private executable")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(binary)
    print("VH73_SYNTHETIC_EXE",len(binary),"MIPS",len(ins),"GP0",len(GP0_SEQUENCE),
          "end",hex(pc),"sha256",hashlib.sha256(binary).hexdigest())
    return 0
if __name__=="__main__":
    raise SystemExit(main())
