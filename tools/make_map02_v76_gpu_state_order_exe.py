#!/usr/bin/env python3
"""Entirely synthetic PS-X EXE: layered FT4, CLUT switching, E1/E2/E6 state.

Hardware raster correctness is assessed independently from real PCSX
GPUfreeze native VRAM, not from this generator or callback counts.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,MARKER_VALUE,lui,ori,sw,addiu
from .make_map02_v74_indexed_clut_exe import upload,xy
MAGIC=b"VH76SYN!"
HEADER_SIZE=2048
SECTION_SIZE=4096
Y=128
CLUT_A=32
CLUT_B=33
PALETTE_A=tuple({1:0x801f,2:0x83e0,3:0x001f,4:0x03e0}.get(i,0)
                for i in range(16))
PALETTE_B=tuple({1:0x801f,2:0x83e0,3:0x03ff,4:0x7fe0}.get(i,0)
                for i in range(16))
SOURCE_4BPP=(0x1111,0x2222,0x3333,0x4444)*4
# Two blended layers in different submission order, both with STP set.
# Expected each pixel comes from BGR555 integer average and source bit15.
def avg(bg,fg):
    channels=lambda c: (c&31,(c>>5)&31,(c>>10)&31)
    dst=channels(bg);src=channels(fg)
    rgb=tuple((d+s)//2 for d,s in zip(dst,src))
    return 0x8000|rgb[0]|(rgb[1]<<5)|(rgb[2]<<10)
BLEND_RED_THEN_GREEN=avg(avg(0x7c00,0x801f),0x83e0)
BLEND_GREEN_THEN_RED=avg(avg(0x7c00,0x83e0),0x801f)
# Ten 4x4 areas, x aligned to avoid any overlap between cases.
REGIONS=(
    ("red_green_order",40,BLEND_RED_THEN_GREEN),
    ("green_red_order",56,BLEND_GREEN_THEN_RED),
    ("clut_A",72,0x001f),
    ("clut_B",88,0x03ff),
    ("e2_window_enabled",104,0x03e0),
    ("e2_window_restored",120,0x001f),
    ("e6_mask_protection",136,0x801f),
    ("e6_mask_restored",152,0x03e0),
    ("e1_abr0_sprite",168,0xbc0f),
    ("e1_abr1_sprite",184,0xfc1f),
)
def ft4(x,clut,u,semi=False,tpage=0):
    return ((0x2f000000 if semi else 0x2d000000),
            xy(x,Y),(clut<<16)|u,
            xy(x+4,Y),(tpage<<16)|(u+4),
            xy(x,Y+4),(4<<8)|u,
            xy(x+4,Y+4),(4<<8)|(u+4))
def sprite(x,clut,u):
    # GP0(67h): variable-sized, RAW textured, semi-transparent rectangle.
    # Sprite tpage comes from persistent E1 draw mode, not an FT4 UV.
    return (0x67ffffff,xy(x,Y),(clut<<16)|u,xy(4,4))
def tile(x):
    return (0x60ff0000,xy(x,Y),xy(4,4)) # opaque blue base
def gp0_stream():
    cmds=[0xe3000000,0xe407ffff,0xe5000000,0xe6000000,
          0xe1000000,0xe2000000]
    cmds.extend(upload(0,0,4,4,SOURCE_4BPP))
    cmds.extend(upload(512,0,16,1,PALETTE_A))
    cmds.extend(upload(528,0,16,1,PALETTE_B))
    for _,left,_ in REGIONS:cmds.extend(tile(left))
    # Submit two semi textures in both orders on independent blue tiles.
    cmds.extend(ft4(40,CLUT_A,0,True))
    cmds.extend(ft4(40,CLUT_A,4,True))
    cmds.extend(ft4(56,CLUT_A,4,True))
    cmds.extend(ft4(56,CLUT_A,0,True))
    # Same U8 index3, two different palettes, strictly sequential.
    cmds.extend(ft4(72,CLUT_A,8))
    cmds.extend(ft4(88,CLUT_B,8))
    # GP0(E2) horizontal window selects U12 instead of U4.
    cmds.append(0xe2000401)
    cmds.extend(ft4(104,CLUT_A,4))
    cmds.append(0xe2000000)
    cmds.extend(ft4(120,CLUT_A,8))
    # Force framebuffer bit15, then mask-check rejects later redraw.
    cmds.append(0xe6000001)
    cmds.extend(ft4(136,CLUT_A,8))
    cmds.append(0xe6000002)
    cmds.extend(ft4(136,CLUT_A,12))
    cmds.append(0xe6000000)
    cmds.extend(ft4(152,CLUT_A,8))
    cmds.extend(ft4(152,CLUT_A,12))
    # Unlike FT4, textured sprites obtain their tpage/ABR from E1.
    cmds.append(0xe1000000)
    cmds.extend(sprite(168,CLUT_A,0))
    cmds.append(0xe1000020)
    cmds.extend(sprite(184,CLUT_A,0))
    cmds.extend((0xe1000000,0xe2000000,0xe6000000))
    return tuple(cmds)
GP0_SEQUENCE=gp0_stream()
def expected_pixel(x,y):
    if Y<=y<Y+4:
        for _,start,color in REGIONS:
            if start<=x<start+4:return color
    return 0
def build():
    instructions=[lui(8,0x1f80),ori(8,8,0x1814),
                  lui(9,0x0100),ori(9,9,0),sw(9,0,8),addiu(8,8,-4)]
    for word in GP0_SEQUENCE:
        instructions.extend((lui(9,word>>16),ori(9,9,word&0xffff),sw(9,0,8)))
    instructions.extend((lui(10,0x8001),ori(10,10,0x1000),
                         lui(9,MARKER_VALUE>>16),ori(9,9,MARKER_VALUE&0xffff),
                         sw(9,0,10)))
    end=START+len(instructions)*4
    instructions.extend(((2<<26)|((end>>2)&0x03ffffff),0))
    body=b"".join(struct.pack("<I",w) for w in instructions)
    if len(body)>SECTION_SIZE:raise ValueError("bounded synthetic CPU program too large")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+body.ljust(SECTION_SIZE,b"\0"),end,tuple(instructions)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    image,end,ops=build()
    if a.output.is_symlink() or a.output.exists():
        p.error("refusing to replace an existing/linked file")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(image)
    print("VH76_SYNTHETIC_GPU_STATES",len(image),"gp0",len(GP0_SEQUENCE),
          "mips",len(ops),"pc",hex(end),"sha256",hashlib.sha256(image).hexdigest())
    return 0
if __name__=="__main__":raise SystemExit(main())
