#!/usr/bin/env python3
"""Apply opt-in GPU read-only observation hooks to PINNED notaz PCSX ReARMed.

One-shot strict exact-anchor patch of a disposable upstream checkout only.
No licensed emulator source is published or copied into our repository.
The checked upstream commit is a *source pin*, NOT an actual retail capture.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

PIN="8b6c163575e6ce9a0537553e0d4ed4225315955e"

def one(s:str,old:str,new:str,name:str)->str:
    if s.count(old)!=1:
        raise ValueError(f"{name}: expected exactly one pinned source anchor")
    return s.replace(old,new)

def patch(root:Path):
    repo=root.resolve()
    here=Path(__file__).resolve().parent
    result=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
                          capture_output=True,text=True,check=True)
    if result.stdout.strip()!=PIN:
        raise ValueError("refusing non-pinned PCSX ReARMed source revision")
    hw=repo/"libpcsxcore"/"psxhw.c"
    dma=repo/"libpcsxcore"/"psxdma.c"
    make=repo/"Makefile"
    orig={p:p.read_text() for p in (hw,dma,make)}
    h=one(orig[hw],
          '#include "psxhw.h"\n',
          '#include "psxhw.h"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n#include "vh66_gpu_probe_bridge.h"\n#endif\n',
          "GPU GP1 header")
    h=one(h,
          '\tcase 0x1814: psxHwWriteGpuSR(value); return;',
          '\tcase 0x1814:\n#ifdef VH_MAP02_V66_PCSX_PROBE\n\t\t(void)vh66_pcsx_gp1_observe(value);\n#endif\n\t\tpsxHwWriteGpuSR(value); return;',
          "GP1 MMIO 0x1f801814")
    d=one(orig[dma],
          '#include "psxdma.h"\n',
          '#include "psxdma.h"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n#include "vh66_gpu_probe_bridge.h"\n#endif\n',
          "GPU DMA header")
    target='\t\t\tcycles_sum = GPU_dmaChain((u32 *)psxRegs.ptrs.psxM, madr & 0x1fffff,'
    replacement=('\t\t\t#ifdef VH_MAP02_V66_PCSX_PROBE\n'
                 '\t\t\t(void)vh66_pcsx_dma2_observe((const unsigned char *)psxRegs.ptrs.psxM, madr & 0x1fffff);\n'
                 '\t\t\t#endif\n'+target)
    d=one(d,target,replacement,"GPU DMA2 before GPU_dmaChain")
    m=one(orig[make],
          'OBJS += libpcsxcore/gte.o libpcsxcore/gte_nf.o libpcsxcore/gte_divider.o\n',
          'OBJS += libpcsxcore/gte.o libpcsxcore/gte_nf.o libpcsxcore/gte_divider.o\n'
          'ifneq ($(VH_MAP02_V66_PCSX_PROBE),)\n'
          'CFLAGS += -DVH_MAP02_V66_PCSX_PROBE\n'
          'OBJS += libpcsxcore/vh66_gpu_probe_bridge.o\n'
          'endif\n',
          "opt-in Makefile object")
    replacements={
        hw:h,dma:d,make:m
    }
    filenames={
        repo/"libpcsxcore"/"vh66_gpu_probe_bridge.h":here/"map02_v66_pcsx_rearmed_bridge.h",
        repo/"libpcsxcore"/"vh66_gpu_probe_bridge.c":here/"map02_v66_pcsx_rearmed_bridge.c",
        repo/"libpcsxcore"/"vh65_gpu_probe.h":here/"map02_v65_gpu_probe.h",
    }
    for dest in filenames:
        if dest.exists():raise ValueError("refusing to overwrite existing emulator adapter")
    # Validate all the transformations before writing anything.
    for dest,src in filenames.items():
        if not src.is_file():raise ValueError("required v65/66 hook file is missing")
    for dest,body in replacements.items():dest.write_text(body)
    for dest,src in filenames.items():shutil.copyfile(src,dest)
    return {
        "upstream":"notaz/pcsx_rearmed",
        "pinned_revision":PIN,
        "read_only_hook_locations":[
            "libpcsxcore/psxhw.c: psxHwWrite32 GP1 0x1f801814",
            "libpcsxcore/psxdma.c: psxDma2 linked-list before GPU_dmaChain",
        ],
        "gp0_packet_consumption_or_hardware_observed":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    a=p.parse_args()
    print(patch(a.checkout))
    return 0

if __name__=="__main__":raise SystemExit(main())
