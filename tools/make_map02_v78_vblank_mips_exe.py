#!/usr/bin/env python3
"""Real-emulator VBlank-synchronized GPU VRAM scene, fully synthetic MIPS.

v77 four bounded CPU stages are preserved exactly. A fifth *program
location* is a 512-instruction MIPS NOP/jump spin executed between
snapshots; the original PCSX counter calls GPU_vBlank(1,0) when enough
genuine interpreted CPU cycles have elapsed. No host-forged cycles,
interrupts, timers or synthetic VBlank signal.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
from pathlib import Path
from .make_map02_v70_synthetic_psx_exe import START
from .make_map02_v77_gpu_multiphase_exe import build as v77_build,PHASE_GP0,PHASE_GP1,EXPECTED_REGS,expected_pixel
MAGIC=b"VH78SYN!"
HEADER=2048
SECTION_SIZE=8192
WAIT_NOPS=512

def build():
    old,stops,ops,starts=v77_build()
    wait_pc=START+4*len(ops)
    # Normal stage 3 self-jump is still present, but the host debugger
    # temporarily executes the separate wait pad at this precise PC.
    wait_block=(0,)*WAIT_NOPS+((2<<26)|((wait_pc>>2)&0x03ffffff),0)
    all_ops=ops+wait_block
    code=b"".join(struct.pack("<I",w) for w in all_ops)
    if len(code)>SECTION_SIZE:raise ValueError("synthetic bounded load exceeded")
    hdr=bytearray(old[:HEADER])
    hdr[0x4c:0x54]=MAGIC
    struct.pack_into("<I",hdr,0x1c,SECTION_SIZE)
    data=bytes(hdr)+code.ljust(SECTION_SIZE,b"\0")
    return data,stops,starts,wait_pc,tuple(all_ops)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    opt=p.parse_args()
    data,stops,starts,wait_pc,all_ops=build()
    if opt.output.is_symlink() or opt.output.exists():
        p.error("refuse existing or linked output")
    opt.output.parent.mkdir(parents=True,exist_ok=True)
    opt.output.write_bytes(data)
    print("VH78_SYNTHETIC_VBLANK_EXE",len(data),"cpu_ops",len(all_ops),
          "mips_wait_nops",WAIT_NOPS,"wait_pc",hex(wait_pc),
          "phase_pc",[hex(x) for x in stops],
          "sha256",hashlib.sha256(data).hexdigest())
    return 0
if __name__=="__main__":
    raise SystemExit(main())
