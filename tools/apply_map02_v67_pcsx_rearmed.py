#!/usr/bin/env python3
"""Opt-in v67 RAM-version bridge atop *pinned* PCSX ReARMed v66 patch."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
from .apply_map02_v66_pcsx_rearmed import PIN,patch as patch_v66

def patch(root:Path):
    result=patch_v66(root)
    project=Path(__file__).resolve().parent
    destination=root.resolve()/"libpcsxcore/vh66_gpu_probe_bridge.c"
    source=project/"map02_v67_pcsx_rearmed_bridge.c"
    before=(project/"map02_v66_pcsx_rearmed_bridge.c").read_bytes()
    if destination.read_bytes()!=before:
        raise ValueError("v66 bridge copy differs from pinned local adapter")
    shutil.copyfile(source,destination)
    result["versioned_ram_snapshots_available"]=True
    result["actual_emulator_boot_verified"]=False
    result["full_gpu_fifo_consumption_verified"]=False
    result["original_retail_MAP02_verified"]=False
    result["HD_replacement_approved"]=False
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(patch(a.checkout))
    return 0

if __name__=="__main__":raise SystemExit(main())
