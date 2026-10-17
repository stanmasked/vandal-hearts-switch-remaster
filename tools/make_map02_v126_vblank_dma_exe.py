#!/usr/bin/env python3
"""v126: genuine emulated VBlank edges between MIPS-originated GPU DMA2 lists.

Retains the exact 3 different DMA chains of v125, appends an isolated
512-NOP MIPS spin pad for the CPU to advance genuine psxRcntUpdate
VBlank time. No host writes to cycle counters or VBlank state.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START
from .make_map02_v125_variable_gpu_dma_exe import build as v125_build

MAGIC=b"VH126SY!"
HEADER_SIZE=2048
SECTION_SIZE=8192
WAIT_NOPS=512

def build():
    previous,stops,ops,starts=v125_build()
    wait_pc=START+4*len(ops)
    wait_jump=(2<<26)|((wait_pc>>2)&0x03ffffff)
    wait_ops=(0,)*WAIT_NOPS+(wait_jump,0)
    all_ops=ops+wait_ops
    body=b"".join(struct.pack("<I",word) for word in all_ops)
    if len(body)>SECTION_SIZE:
        raise ValueError("bounded wait pad exceeds original synthetic EXE section")
    header=bytearray(previous[:HEADER_SIZE])
    header[0x4c:0x54]=MAGIC
    struct.pack_into("<I",header,0x1c,SECTION_SIZE)
    return (bytes(header)+body.ljust(SECTION_SIZE,b"\0"),
            stops,all_ops,starts,wait_pc)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    data,stops,ops,_,wait_pc=build()
    if args.output.exists() or args.output.is_symlink():
        p.error("refusing to overwrite any file or symlink")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("VH126_MIPS_REAL_VBLANK_GPU_DMA",len(data),"ops",len(ops),
          "wait_pc",hex(wait_pc),"stage_stops",[hex(v) for v in stops],
          "sha256",hashlib.sha256(data).hexdigest())

if __name__=="__main__":
    main()
