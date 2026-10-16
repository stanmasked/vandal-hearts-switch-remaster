#!/usr/bin/env python3
"""v71 entirely synthetic PS-X EXE: CPU MIPS submits a VRAM pixel oracle scene.

Source registers and intended pixel values are independent of video
plugin code. No retail/SDK/BIOS/game bytes. Draw at (16,16) and (24,16):
red first, blue with GP0(E6) set-mask bit, then green overlapping with
GP0(E6) check-mask bit; masked blue must survive the third rectangle.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import struct
from .make_map02_v70_synthetic_psx_exe import lui,ori,addiu,sw,START,MARKER_ADDR,MARKER_VALUE

MAGIC=b"VH71SYN!"
HEADER_SIZE=2048
SECTION_SIZE=2048
RED=(16,16,4,4,0x001f)
MASKED_BLUE=(24,16,4,4,0xfc00)
CHECKED_GUARD=(32,16,4,4,0x0000)
GP0_SEQUENCE=(
    0xe3000000,       # E3 drawing top-left (0,0)
    0xe407ffff,       # E4 drawing lower-right (1023,511)
    0xe5000000,       # E5 drawing offset (0,0)
    0xe6000000,       # E6 mask disable
    0x600000ff,       # flat red tile 4x4 at (16,16)
    0x00100010,
    0x00040004,
    0xe6000001,       # E6 set pixel mask bit
    0x60ff0000,       # flat blue tile 4x4 at (24,16), MSB=1
    0x00100018,
    0x00040004,
    0xe6000002,       # E6 respect existing masked pixels
    0x6000ff00,       # flat green tile overlaps masked blue; must NOT overwrite
    0x00100018,
    0x00040004,
)
def emit_word_register(code,reg,val):
    code.append(lui(reg,(val>>16)&0xffff))
    code.append(ori(reg,reg,val&0xffff))

def build():
    code=[]
    # t0=GPU GP1; send GP1(01) reset FIFO BEFORE issuing draw commands.
    code.extend((lui(8,0x1f80),ori(8,8,0x1814)))
    emit_word_register(code,9,0x01000000)
    code.append(sw(9,0,8))
    code.append(addiu(8,8,-4))  # t0=GPU GP0 direct port
    for word in GP0_SEQUENCE:
        emit_word_register(code,9,word)
        code.append(sw(9,0,8))
    # CPU success marker in RAM after every GP0 MMIO store completed.
    code.extend((lui(10,0x8001),ori(10,10,0x1000)))
    emit_word_register(code,9,MARKER_VALUE)
    code.append(sw(9,0,10))
    loop_pc=START+len(code)*4
    code.append((0x02<<26)|((loop_pc>>2)&0x03ffffff))
    code.append(0) # branch delay slot
    payload=b"".join(struct.pack("<I",w) for w in code)
    assert len(payload)<=SECTION_SIZE
    header=bytearray(HEADER_SIZE)
    header[:8]=b"PS-X EXE"
    struct.pack_into("<I",header,0x10,START)
    struct.pack_into("<I",header,0x18,START)
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    struct.pack_into("<I",header,0x30,0x801fff00)
    header[0x4c:0x54]=MAGIC
    return bytes(header)+payload.ljust(SECTION_SIZE,b"\0"),loop_pc,code

def expected_color_at(x,y):
    if 16<=x<20 and 16<=y<20:return 0x001f
    if 24<=x<28 and 16<=y<20:return 0xfc00
    return 0

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    path=args.output
    if path.exists() or path.is_symlink():p.error("refusing overwrite of original or private file")
    raw,loop,code=build()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    print("SYNTHETIC_V71_PSX_EXE",len(raw),"mips_instructions",len(code),
          "gp0_words",len(GP0_SEQUENCE),"loop_pc",hex(loop),
          "sha256",hashlib.sha256(raw).hexdigest())
if __name__=="__main__":main()
