#!/usr/bin/env python3
"""Original PS-X EXE: four separately executed MIPS GPU phases in one PCSX process.

GPUfreeze readback is done between bounded ExecuteBlock calls, with no
emulator reload and no reinitialization. Phase C submits GP1(01) (FIFO
reset); D submits GP1(00) (full GPU reset). No copyrighted source data.
A phase boundary is NOT a physical PS1 VBlank/display frame.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START,lui,ori,sw,addiu
from .make_map02_v74_indexed_clut_exe import upload,xy

MAGIC=b"VH77SYN!"
HEADER_SIZE=2048
SECTION_SIZE=4096
Y=160
X=(40,56,72,88,104,120)
BLUE=0x7c00
MASKED_RED=0x801f
RED=0x001f
ADD_RED_BLUE=0xfc1f
AVG_GREEN_BLUE=0xbde0
PHASE_NAMES=("setup","persist","fifo_reset","full_reset")
MARKERS=(0x77010001,0x77010002,0x77010003,0x77010004)
# Packed 4bpp: U4..7 => CLUT2/STP green, U12..15 => CLUT1/STP red.
TEXELS=(0,0x2222,0,0x1111)*4
CLUT=tuple({1:0x801f,2:0x83e0}.get(i,0) for i in range(16))
E1_ABR1=0xe1000020
E2_MAP_TO_U12=0xe2000401
E6_FORCE_MASK=0xe6000001

def tile(x,color=0x600000ff):
    return (color,xy(x,Y),xy(4,4))

def sprite(x):
    # Raw semi-textured sprite reads persistent GP0(E1) texture page+ABR.
    # U=4 becomes U=12 only while GP0(E2) window state survives.
    return (0x67ffffff,xy(x,Y),(32<<16)|4,xy(4,4))

def phase_commands():
    a=[0xe3000000,0xe407ffff,0xe5000000,0xe6000000,
       0xe1000000,0xe2000000]
    a.extend(upload(0,0,4,4,TEXELS))
    a.extend(upload(512,0,16,1,CLUT))
    for x in X:a.extend(tile(x))
    # Changes deliberately AFTER the background draws: test state
    # remains in the GPU across the first readback and future CPU blocks.
    a.extend((E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK))
    b=(*sprite(X[0]),*tile(X[1]))
    c=(*sprite(X[2]),*tile(X[3]))
    # GP1(00) clears E1 E2 E6; only area bounds are restored here.
    d=(0xe3000000,0xe407ffff,*sprite(X[4]),*tile(X[5]))
    return tuple(map(tuple,(a,b,c,d)))

PHASE_GP0=phase_commands()
PHASE_GP1=(0x01000000,None,0x01000000,0x00000000)
EXPECTED_REGS=(
    (E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK),
    (E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK),
    (E1_ABR1,E2_MAP_TO_U12,E6_FORCE_MASK),
    (0xe1000000,0xe2000000,0xe6000000),
)

def expected_pixel(phase,x,y):
    if not(Y<=y<Y+4):return 0
    if x not in X and not any(left<=x<left+4 for left in X):return 0
    colors=[BLUE]*len(X)
    if phase>=1:colors[:2]=[ADD_RED_BLUE,MASKED_RED]
    if phase>=2:colors[2:4]=[ADD_RED_BLUE,MASKED_RED]
    if phase>=3:colors[4:6]=[AVG_GREEN_BLUE,RED]
    for i,left in enumerate(X):
        if left<=x<left+4:return colors[i]
    return 0

def gp0_mips(words):
    out=[]
    for w in words:out.extend((lui(9,w>>16),ori(9,9,w&65535),sw(9,0,8)))
    return out

def phase_body(index):
    # t0 initially points to GPU GP0, with optional GP1 control first.
    ins=[lui(8,0x1f80),ori(8,8,0x1810)]
    if PHASE_GP1[index] is not None:
        w=PHASE_GP1[index]
        ins.extend((addiu(8,8,4),lui(9,w>>16),
                    ori(9,9,w&65535),sw(9,0,8),addiu(8,8,-4)))
    ins.extend(gp0_mips(PHASE_GP0[index]))
    # Individual CPU completion markers; snapshots must read each one.
    w=MARKERS[index]
    ins.extend((lui(10,0x8001),ori(10,10,0x1000+4*index),
                lui(9,w>>16),ori(9,9,w&65535),sw(9,0,10)))
    return ins

def build():
    bodies=[phase_body(i) for i in range(4)]
    starts=[START]
    for body in bodies[:-1]:starts.append(starts[-1]+(len(body)+2)*4)
    stops=[]
    instructions=[]
    for i,body in enumerate(bodies):
        jump=starts[i+1] if i+1<len(bodies) else starts[i]+len(body)*4
        stops.append(jump)
        instructions.extend(body)
        instructions.extend(((2<<26)|((jump>>2)&0x03ffffff),0))
    payload=b"".join(struct.pack("<I",w) for w in instructions)
    if len(payload)>SECTION_SIZE:raise ValueError("synthetic phase sequence out of bounds")
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+payload.ljust(SECTION_SIZE,b"\0"),tuple(stops),tuple(instructions),tuple(starts)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    exe,stops,ops,starts=build()
    if args.output.is_symlink() or args.output.exists():
        parser.error("refuse replacing an existing or linked file")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(exe)
    print("VH77_SYNTHETIC_CPU_PHASES",len(exe),"mips_words",len(ops),
          "phase_pc",[hex(v) for v in stops],"sha256",hashlib.sha256(exe).hexdigest())
    return 0

if __name__=="__main__":raise SystemExit(main())
