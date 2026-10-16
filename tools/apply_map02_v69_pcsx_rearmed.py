#!/usr/bin/env python3
"""Apply pinned v68 source hooks then add opt-in plugin callback dispatch audit.

No emulator source is copied into the remaster repository: patches target
only the disposable upstream revision pinned by prior v66-v68 stages.
The core smoke mode tests HLE/no-media initialization, not PS1 gameplay.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
from .apply_map02_v68_pcsx_rearmed import apply as apply_v68

def once(s:str,old:str,new:str,label:str):
    if s.count(old)!=1:
        raise ValueError("non-unique or absent pinned "+label+" source anchor")
    return s.replace(old,new)

def apply(root:Path):
    proof=apply_v68(root)
    base=root.resolve()
    plugin=base/"libpcsxcore/plugins.c"
    make=base/"Makefile"
    frontend=base/"frontend/main.c"
    old={p:p.read_text() for p in (plugin,make,frontend)}
    new_plugin=once(old[plugin],
        '#include "plugins.h"\n',
        '#include "plugins.h"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n#include "vh69_gpu_plugin_wrap.h"\n#endif\n',
        "plugin header")
    new_plugin=once(new_plugin,
        '\tLoadGpuSym0(getScreenInfo, "GPUgetScreenInfo");\n',
        '\tLoadGpuSym0(getScreenInfo, "GPUgetScreenInfo");\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '\tvh69_gpu_wrap_loaded_plugin();\n'
        '#endif\n',
        "resolved GPU plugin dispatch")
    new_make=once(old[make],
        'OBJS += libpcsxcore/vh66_gpu_probe_bridge.o\n',
        'OBJS += libpcsxcore/vh66_gpu_probe_bridge.o\n'
        'OBJS += libpcsxcore/vh69_gpu_plugin_wrap.o\n',
        "diagnostic plugin wrapper object")
    new_front=once(old[frontend],
        '\tint loadst = 0;\n',
        '\tint loadst = 0;\n#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '\tint vh69_core_smoke = 0;\n#endif\n',
        "core smoke storage")
    new_front=once(new_front,
        '\t\telse if (!strcmp(argv[i], "-nodrc"))\n\t\t\tnodrc = 1;\n',
        '\t\telse if (!strcmp(argv[i], "-nodrc"))\n\t\t\tnodrc = 1;\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '\t\telse if (!strcmp(argv[i], "--vh69-core-smoke"))\n'
        '\t\t\tvh69_core_smoke = 1;\n'
        '#endif\n',
        "core smoke option")
    new_front=once(new_front,
        '\tSysReset();\n\n\tif (file[0]',
        '\tSysReset();\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '\tif (vh69_core_smoke) {\n'
        '\t\t/* No game, no disc, no BIOS image: HLE, plugins and\n'
        '\t\t * emulated reset initialized without executing gameplay. */\n'
        '\t\tSysPrintf("VH69_CORE_INIT_SMOKE_PASS HLE_NO_MEDIA\\n");\n'
        '\t\tClosePlugins();\n'
        '\t\tSysClose();\n'
        '\t\tmenu_finish();\n'
        '\t\tplat_finish();\n'
        '\t\treturn 0;\n'
        '\t}\n'
        '#endif\n\n\tif (file[0]',
        "no-media core initialization hook")
    local=Path(__file__).resolve().parent
    replacements={
        base/"libpcsxcore/vh69_gpu_plugin_wrap.c":local/"map02_v69_pcsx_plugin_wrap.c",
        base/"libpcsxcore/vh69_gpu_plugin_wrap.h":local/"map02_v69_pcsx_plugin_wrap.h",
    }
    if any(p.exists() for p in replacements):
        raise ValueError("refusing existing emulator plugin wrapper files")
    for source in replacements.values():
        if not source.is_file():raise ValueError("missing local source shim")
    plugin.write_text(new_plugin)
    make.write_text(new_make)
    frontend.write_text(new_front)
    for dest,source in replacements.items():shutil.copyfile(source,dest)
    return dict(proof,plugin_callback_wrappers_source_installed=True,
                full_gpu_fifo_consumption_verified=False,
                real_game_boot_verified=False,
                retail_gp0_provenance_verified=False,
                HD_replacement_approved=False)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    opts=p.parse_args()
    print(apply(opts.checkout))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
