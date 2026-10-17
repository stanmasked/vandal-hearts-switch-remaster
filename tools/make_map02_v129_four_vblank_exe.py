#!/usr/bin/env python3
"""Preserve the exact v128 MIPS program: only the authentication tag changes."""
import argparse
from pathlib import Path
from .make_map02_v128_triple_vblank_exe import build as previous_build

MAGIC=b"VH129SY!"

def build():
    data,stops,ops,starts,wait_pc=previous_build()
    if len(data)!=10240 or data[:8]!=b"PS-X EXE" or data[0x4c:0x54]!=b"VH128SY!":
        raise ValueError("previous signed synthetic PS-X EXE changed")
    return data[:0x4c]+MAGIC+data[0x54:],stops,ops,starts,wait_pc

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        p.error("refusing to overwrite an existing file or symlink")
    data,stops,ops,_,wait_pc=build()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("VH129_FOUR_GENUINE_VBLANK_MIPS_DMA",len(data),
          "stages",len(stops),"instructions",len(ops),"wait_pc",hex(wait_pc))

if __name__=="__main__":
    main()
