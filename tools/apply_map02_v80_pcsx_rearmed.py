#!/usr/bin/env python3
"""Source-level bounded native PCSX VBlank / GP1 / GPU DMA2 submission observer.

The observer does not read GPU FIFO completion or individual VRAM writes.
Applies after the pinned v78 patch; source mutations are exact-anchor only.
"""
from pathlib import Path
import shutil
from .apply_map02_v78_pcsx_rearmed import apply as apply_v78
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof = apply_v78(root)
    base = root.resolve()
    hw = base / "libpcsxcore/psxhw.c"
    dma = base / "libpcsxcore/psxdma.c"
    counters = base / "libpcsxcore/psxcounters.c"
    make = base / "Makefile"
    originals = {p: p.read_text() for p in (hw, dma, counters, make)}
    h = once(originals[hw],
       '#include "vh66_gpu_probe_bridge.h"\n',
       '#include "vh66_gpu_probe_bridge.h"\n#include "vh80_native_timeline.h"\n',
       "GPU MMIO instrumentation header")
    h = once(h,
       '(void)vh66_pcsx_gp1_observe(value);',
       '(void)vh66_pcsx_gp1_observe(value);\n'
       '\t\tvh80_record(VH80_GP1_MMIO,value,psxRegs.cycle,0);',
       "GP1 observed input word")
    # frame_counter is exposed by psxcounters.h in the pinned core.
    d = once(originals[dma],
       '#include "vh66_gpu_probe_bridge.h"\n',
       '#include "vh66_gpu_probe_bridge.h"\n#include "vh80_native_timeline.h"\n',
       "DMA2 instrumentation header")
    d = once(d,
       '(void)vh66_pcsx_dma2_observe((const unsigned char *)psxRegs.ptrs.psxM, madr & 0x1fffff);',
       '(void)vh66_pcsx_dma2_observe((const unsigned char *)psxRegs.ptrs.psxM, madr & 0x1fffff);\n'
       '\t\t\tvh80_record(VH80_GPU_DMA2,madr & 0x1fffff,psxRegs.cycle,0);',
       "GPU DMA2 start address (not GP0 command)")
    c = once(originals[counters],
       '/* Increments ONLY in the pinned original psxRcntUpdate()',
       '#include "vh80_native_timeline.h"\n'
       '/* Increments ONLY in the pinned original psxRcntUpdate()',
       "VBlank hook include")
    c = once(c,
       'vh78_vblank_observed_count++;',
       'vh78_vblank_observed_count++;\n'
       '            vh80_record(VH80_VBLANK,0,psxRegs.cycle,frame_counter);',
       "original VBlank callback after GPU_vBlank")
    m = once(originals[make],
       'OBJS += libpcsxcore/vh69_gpu_plugin_wrap.o\n',
       'OBJS += libpcsxcore/vh69_gpu_plugin_wrap.o\n'
       'OBJS += libpcsxcore/vh80_native_timeline.o\n',
       "opt-in native event recorder build")
    sources = Path(__file__).resolve().parent
    additions = {
        base / "libpcsxcore/vh80_native_timeline.h": sources / "map02_v80_native_timeline.h",
        base / "libpcsxcore/vh80_native_timeline.c": sources / "map02_v80_native_timeline.c",
    }
    if any(p.exists() for p in additions):
        raise ValueError("refusing existing v80 upstream files")
    if any(not p.is_file() for p in additions.values()):
        raise ValueError("missing v80 observer source")
    for p, body in ((hw,h),(dma,d),(counters,c),(make,m)):
        p.write_text(body)
    for target, source in additions.items():
        shutil.copyfile(source,target)
    return dict(proof, native_vblank_gp1_dma2_source_observer_installed=True,
        native_gp0_consumption_verified=False,
        native_vram_write_trace_verified=False,
        live_v80_trace_verified=False,
        physical_ps1_vblank_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
