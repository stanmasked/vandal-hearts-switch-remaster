#!/usr/bin/env python3
"""Emit a fully ORIGINAL synthetic PS-X EXE with hand-encoded MIPS-I CPU opcodes.

No PsyQ or retail assets. The program:
  1. sends GP0(E6), flat rectangle (3 words) to 0x1f801810
  2. sends GP1(01) FIFO reset to 0x1f801814
  3. stores a CPU-authored success marker in regular PS1 RAM
  4. branches to itself for a bounded ExecuteBlock smoke.
Only the diagnostic emulator knows the expected PC and marker.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import struct

START=0x80010000
MARKER_ADDR=0x80011000
MARKER_VALUE=0x70000001
MAGIC=b"VH70SYN!"
HEADER_SIZE=2048
SECTION_SIZE=2048

def lui(rt,imm):return (0x0f<<26)|(rt<<16)|(imm&0xffff)
def ori(rt,rs,imm):return (0x0d<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)
def addiu(rt,rs,imm):return (0x09<<26)|(rs<<21)|(rt<<16)|(imm&0xffff)
def sw(rt,offset,rs):return (0x2b<<26)|(rs<<21)|(rt<<16)|(offset&0xffff)

def build():
    # MIPS: t0 GPU port; t1 data word; t2 RAM marker.
    code=[
        lui(8,0x1f80),ori(8,8,0x1810),
        lui(9,0xe600),sw(9,0,8),
        lui(9,0x6000),ori(9,9,0x00ff),sw(9,0,8),
        ori(9,0,0),sw(9,0,8),
        ori(9,0,0x0404),sw(9,0,8),
        addiu(8,8,4),lui(9,0x0100),sw(9,0,8),
        lui(10,0x8001),ori(10,10,0x1000),
        lui(9,0x7000),ori(9,9,1),sw(9,0,10),
    ]
    loop_pc=START+len(code)*4
    code.append((0x02<<26)|((loop_pc>>2)&0x3ffffff))  # MIPS J loop
    code.append(0)  # delay slot
    payload=b"".join(struct.pack("<I",x) for x in code).ljust(SECTION_SIZE,b"\0")
    header=bytearray(HEADER_SIZE)
    header[0:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x14,0)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x4c+len(MAGIC)]=MAGIC
    return bytes(header)+payload,loop_pc,code

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    image,loop,ops=build()
    if a.output.exists() or a.output.is_symlink():
        p.error("refusing to replace an existing PS-X EXE")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(image)
    print(f"SYNTHETIC_V70_PSX_EXE bytes={len(image)} mips_words={len(ops)} "+
          f"entry=0x{START:08x} loop=0x{loop:08x} "+
          f"marker_addr=0x{MARKER_ADDR:08x} marker_value=0x{MARKER_VALUE:08x} "+
          f"sha256={hashlib.sha256(image).hexdigest()}")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
