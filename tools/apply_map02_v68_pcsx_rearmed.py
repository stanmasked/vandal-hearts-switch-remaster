#!/usr/bin/env python3
"""Strict v68 PCSX ReARMed GPU GP0-MMIO hook, pinned on top of v67."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
from .apply_map02_v67_pcsx_rearmed import patch as v67_patch

def apply(root:Path):
    result=v67_patch(root)
    base=root.resolve()/"libpcsxcore"
    hw=base/"psxhw.c"
    text=hw.read_text()
    old="\tcase 0x1810: GPU_writeData(value); return;"
    new=("\tcase 0x1810:\n"
         "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
         "\t\t(void)vh68_pcsx_gp0_mmio_observe(value);\n"
         "#endif\n"
         "\t\tGPU_writeData(value); return;")
    if text.count(old)!=1 or text.count("vh68_pcsx_gp0_mmio_observe")!=0:
        raise ValueError("pinned PCSX GP0 MMIO call site mismatch")
    expected={
        "vh66_gpu_probe_bridge.c":"map02_v67_pcsx_rearmed_bridge.c",
        "vh66_gpu_probe_bridge.h":"map02_v66_pcsx_rearmed_bridge.h",
    }
    local=Path(__file__).resolve().parent
    for target,name in expected.items():
        if (base/target).read_bytes()!=(local/name).read_bytes():
            raise ValueError("bridge/header not in original v67 state")
    updated=text.replace(old,new)
    hw.write_text(updated)
    shutil.copyfile(local/"map02_v68_pcsx_rearmed_bridge.c",base/"vh66_gpu_probe_bridge.c")
    shutil.copyfile(local/"map02_v68_pcsx_rearmed_bridge.h",base/"vh66_gpu_probe_bridge.h")
    result.update({
        "gp0_mmio_hook_installed_in_source":True,
        "full_emulator_runtime_boot_verified":False,
        "gpu_plugin_gp0_fifo_consumption_verified":False,
        "retail_gp0_provenance_verified":False,
        "HD_replacement_approved":False,
    })
    return result

def main():
    a=argparse.ArgumentParser()
    a.add_argument("checkout",type=Path)
    opts=a.parse_args()
    print(apply(opts.checkout))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
