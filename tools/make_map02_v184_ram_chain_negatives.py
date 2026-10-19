#!/usr/bin/env python3
"""MAP02 v184: fail closed if synthetic guest RAM computation is incomplete.

Extends v183 fully validated native PCSX interpreter RAM data-value oracle
without modifying emulator, GPU or VBlank behavior. Three negative signed
PS-X EXE variants each change exactly one word of the nine-word original
guest MIPS wait program: missing XORI, missing final SW, or LW from base+4
instead of base+0. All must be refused with native exit 85.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
from struct import pack_into

from .apply_map02_v183_native_ram_values import make_variants as v183_variants, lw, signed_sequence
from .make_map02_v78_vblank_mips_exe import build
from .make_map02_v70_synthetic_psx_exe import START

MUTATIONS=("MISSING_XORI","MISSING_FINAL_SW","WRONG_LW_ADDRESS")
PATCHES=((7,0),(8,0),(5,lw(23,4,22)))
MARKER=b"VH78SYN!"

def make_variants():
    signed=v183_variants()["CORRECT"]
    canonical,_,_,wait_pc,operations=build()
    index=(wait_pc-START)//4
    offset=2048+index*4
    if (len(signed)!=len(canonical) or
        signed[0x4c:0x54]!=MARKER or
        signed[:offset]!=canonical[:offset] or
        signed[offset+36:]!=canonical[offset+36:] or
        tuple(operations[index:index+512])!=(0,)*512):
        raise ValueError("v184 rejects changed v183 signed guest fixture")
    baseline=signed_sequence()
    result={}
    for label,(position,replacement) in zip(MUTATIONS,PATCHES):
        if baseline[position]==replacement:
            raise ValueError("v184 mutation must differ from original guest opcode")
        image=bytearray(signed)
        pack_into("<I",image,offset+position*4,replacement)
        modified=bytes(image)
        if (modified[:offset+position*4]!=signed[:offset+position*4] or
            modified[offset+(position+1)*4:]!=signed[offset+(position+1)*4:] or
            modified[0x4c:0x54]!=MARKER):
            raise ValueError("v184 mutated outside one explicitly signed MIPS word")
        result[label]=modified
    return result

def write_private(directory:Path):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("require existing private output directory")
    variants=make_variants()
    for label in MUTATIONS:
        p=directory/("V184_RAM_"+label+".EXE")
        if p.exists() or p.is_symlink():
            raise ValueError("no replacement of signed private v184 EXE")
    for label in MUTATIONS:
        p=directory/("V184_RAM_"+label+".EXE")
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"wb") as target:target.write(variants[label])
    return len(variants)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-private",required=True,type=Path)
    args=parser.parse_args()
    count=write_private(args.generate_private)
    print(f"VH184_SIGNED_RAM_CHAIN_NEGATIVES_PASS variants={count} single_mips_word_each=1 original_retail=0")
if __name__=="__main__":
    main()
