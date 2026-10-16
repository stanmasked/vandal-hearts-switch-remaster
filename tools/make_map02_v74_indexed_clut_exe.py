#!/usr/bin/env python3
"""Entirely original MIPS PS-X EXE: 4bpp/8bpp CLUT, E2 window, palette transparency.

Four 4x4 textured FT4 regions are checked against hand-authored BGR555
colors in the actual pinned PCSX GPU VRAM. No game/SDK/BIOS assets.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,MARKER_VALUE,lui,ori,sw,addiu

MAGIC=b"VH74SYN!"
HEADER_SIZE=2048
SECTION_SIZE=4096
DEST_Y=80
CLUT4_X=512
CLUT8_X=528
PALETTE4=(0x0000,0x001f,0x03e0,0x7c00,0x7fff,0x03ff,
          0x7fe0,0x7c1f,0x4210,0x001f,0x03e0,0x7c00,0x7fff,0,0,0)
PALETTE8=tuple({17:0x4210,34:0x7c1f,51:0x7fe0,68:0x03ff}.get(i,0)
               for i in range(256))
# Texture 4bpp row U 0..15: 1,2,3,4, 0,0,0,0, 5,6,7,8, 0,1,2,3
INDEX4=(1,2,3,4,0,0,0,0,5,6,7,8,0,1,2,3)
# Texture 8bpp row U 0..7: 17,34,51,68, 0,0,0,0
INDEX8=(17,34,51,68,0,0,0,0)
def xy(x,y):return (y<<16)|x
def halfwords_to_words(pixels):
    if len(pixels)%2:raise ValueError("odd VRAM halfword upload length")
    return tuple(pixels[i]|(pixels[i+1]<<16) for i in range(0,len(pixels),2))
def nibble_halfwords(indices):
    assert len(indices)%4==0
    return tuple(sum(indices[i+j]<<(4*j) for j in range(4))
                 for i in range(0,len(indices),4))
def byte_halfwords(indices):
    assert len(indices)%2==0
    return tuple(indices[i]|(indices[i+1]<<8) for i in range(0,len(indices),2))
def upload(x,y,width,height,pixels):
    if width*height!=len(pixels):raise ValueError("invalid native VRAM upload dimensions")
    return (0xa0000000,xy(x,y),xy(width,height),
            *halfwords_to_words(pixels))
def ft4(x,tpage,clut,u):
    return (0x2d000000,xy(x,DEST_Y),(clut<<16)|u,
            xy(x+4,DEST_Y),(tpage<<16)|(u+4),
            xy(x,DEST_Y+4),(4<<8)|u,
            xy(x+4,DEST_Y+4),(4<<8)|(u+4))
def gp0_stream():
    p4=nibble_halfwords(INDEX4)*4
    p8=byte_halfwords(INDEX8)*4
    commands=[0xe3000000,0xe407ffff,0xe5000000,0xe6000000,
              0xe1000000,0xe2000000]
    commands.extend(upload(0,0,4,4,p4))
    commands.extend(upload(64,0,4,4,p8))
    commands.extend(upload(CLUT4_X,0,16,1,PALETTE4))
    commands.extend(upload(CLUT8_X,0,256,1,PALETTE8))
    commands.extend(ft4(40,0x000,32,0))   # 4bpp CLUT x=512, U 0..4
    commands.extend(ft4(56,0x081,33,0))   # 8bpp CLUT x=528, U 0..4
    commands.append(0xe2000401)            # E2 x mask1/offset1 -> U 8..11
    commands.extend(ft4(72,0x000,32,0))   # 4bpp with E2 window
    commands.append(0xe2000000)            # reset E2 before transparent quad
    commands.extend((0x60ff0000,xy(88,DEST_Y),xy(4,4)))
    commands.extend(ft4(88,0x000,32,12))  # index0 transparent over blue
    return tuple(commands)
GP0_SEQUENCE=gp0_stream()
EXPECTED4=(PALETTE4[1],PALETTE4[2],PALETTE4[3],PALETTE4[4])
EXPECTED8=tuple(PALETTE8[n] for n in INDEX8[:4])
EXPECTED_WINDOW=tuple(PALETTE4[n] for n in INDEX4[8:12])
EXPECTED_TRANSPARENT=(0x7c00,PALETTE4[1],PALETTE4[2],PALETTE4[3])
def expected_pixel(x,y):
    if DEST_Y<=y<DEST_Y+4:
        for start,colors in ((40,EXPECTED4),(56,EXPECTED8),
                             (72,EXPECTED_WINDOW),(88,EXPECTED_TRANSPARENT)):
            if start<=x<start+4:return colors[x-start]
    return 0
def build():
    instr=[lui(8,0x1f80),ori(8,8,0x1814),lui(9,0x0100),
           ori(9,9,0),sw(9,0,8),addiu(8,8,-4)]
    for w in GP0_SEQUENCE:
        instr.extend((lui(9,w>>16),ori(9,9,w&0xffff),sw(9,0,8)))
    instr.extend((lui(10,0x8001),ori(10,10,0x1000),
                  lui(9,MARKER_VALUE>>16),ori(9,9,MARKER_VALUE&0xffff),
                  sw(9,0,10)))
    end_pc=START+4*len(instr)
    instr.extend(((2<<26)|((end_pc>>2)&0x03ffffff),0))
    body=b"".join(struct.pack("<I",w) for w in instr)
    if len(body)>SECTION_SIZE:raise ValueError("synthetic MIPS payload too large")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+body.ljust(SECTION_SIZE,b"\0"),end_pc,tuple(instr)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    data,end,instructions=build()
    if a.output.exists() or a.output.is_symlink():
        p.error("refuse overwrite of existing private file")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(data)
    print("VH74_SYNTHETIC_MIPS_EXE bytes",len(data),"gp0",len(GP0_SEQUENCE),
          "mips",len(instructions),"end",hex(end),
          "sha256",hashlib.sha256(data).hexdigest())
    return 0
if __name__=="__main__":raise SystemExit(main())
