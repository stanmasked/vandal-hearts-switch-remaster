#!/usr/bin/env python3
"""Same native MIPS DMA bytecode as v127; new isolated three-VBlank tag."""
import argparse
from pathlib import Path
from .make_map02_v127_variable_vblank_exe import (
    build as v127_build, HEADER_SIZE, SECTION_SIZE, WAIT_NOPS, START
)

MAGIC=b"VH128SY!"

def build():
    data,stops,ops,starts,wait_pc=v127_build()
    if data[:8]!=b"PS-X EXE" or data[0x4c:0x54]!=b"VH127SY!":
        raise ValueError("v127 signed synthetic EXE changed")
    return data[:0x4c]+MAGIC+data[0x54:],stops,ops,starts,wait_pc

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        p.error("refusing to overwrite existing file or symlink")
    data,stops,ops,_,wait_pc=build()
    if len(data)!=HEADER_SIZE+SECTION_SIZE or len(ops)<WAIT_NOPS:
        raise ValueError("v128 synthetic EXE bounds changed")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes(data)
    print("VH128_THREE_REAL_VBLANK_MIPS_DMA",len(data),
          "stages",len(stops),"wait_pad",WAIT_NOPS,"wait_pc",hex(wait_pc))

if __name__=="__main__":
    main()
