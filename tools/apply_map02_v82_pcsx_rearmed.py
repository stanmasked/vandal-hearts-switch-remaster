#!/usr/bin/env python3
"""Opt-in pinned PCSX v82 native emitter after the v78 four-VBlank oracle.

Records from genuine instrumented emulator callbacks only. The emitted trace
does not prove GP0 execution, VRAM write causality, or original retail MAP02.
"""
from pathlib import Path
import shutil
from .apply_map02_v81_pcsx_rearmed import apply as apply_v81
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof=apply_v81(root)
    base=root.resolve()
    frontend=base/"frontend/main.c"
    make=base/"Makefile"
    fs=frontend.read_text()
    ms=make.read_text()
    fs=once(fs,
        '#include "../libpcsxcore/r3000a.h"\n',
        '#include "../libpcsxcore/r3000a.h"\n'
        '#include "../libpcsxcore/vh80_native_timeline.h"\n'
        '#include "../libpcsxcore/vh81_event_jsonl.h"\n'
        '#include "../libpcsxcore/vh82_private_publish.h"\n',
        "v82 native headers")
    fs=once(fs,
        '\tint vh78_vblank_smoke = 0;\n',
        '\tint vh78_vblank_smoke = 0;\n\tint vh82_export_smoke = 0;\n',
        "v82 opt-in flag")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh78-vblank-smoke"))\n'
        '\t\t\tvh78_vblank_smoke = 1;\n',
        '\t\telse if (!strcmp(argv[i], "--vh78-vblank-smoke"))\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh82-private-export-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t}\n',
        "v82 CLI flag")
    fs=once(fs,
        '\t\tunsigned int previous_vblank_frame=0;',
        '\t\tif(vh82_export_smoke)vh80_reset();\n'
        '\t\tunsigned int previous_vblank_frame=0;',
        "reset at authenticated v78 scene start")
    marker='\t\tSysPrintf("VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1\\n");'
    code=r'''
        if(vh82_export_smoke) {
            const char *dest=getenv("VH_MAP02_V82_PRIVATE_PATH");
            static char vh82_buffer[524288];
            unsigned int observed_edges=0,observed_gp1=0;
            for(unsigned int j=0;j<vh80_count();j++) {
                const vh80_event *e=&vh80_events()[j];
                if(e->kind==VH80_VBLANK)observed_edges++;
                if(e->kind==VH80_GP1_MMIO)observed_gp1++;
            }
            if(observed_edges!=4 || observed_gp1<2 || vh80_dropped()!=0 ||
               !dest || dest[0]!='/') {
                SysPrintf("VH82_CAPTURE_REFUSED
");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 10;
            }
            int trace_bytes=vh81_format_jsonl(vh82_buffer,sizeof(vh82_buffer));
            if(trace_bytes<=0 ||
               vh82_publish_private(dest,vh82_buffer,(size_t)trace_bytes)!=0) {
                SysPrintf("VH82_PRIVATE_PUBLISH_REFUSED
");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 11;
            }
            SysPrintf("VH82_PRIVATE_EXPORT_PASS vblanks=%u gp1_mmio=%u entries=%u bytes=%d drops=0
",
                observed_edges,observed_gp1,vh80_count(),trace_bytes);
        }
'''
    fs=once(fs,marker,code+marker,"publish only after native VRAM/state oracle")
    ms=once(ms,
        'OBJS += libpcsxcore/vh81_event_jsonl.o\n',
        'OBJS += libpcsxcore/vh81_event_jsonl.o\n'
        'OBJS += libpcsxcore/vh82_private_publish.o\n',
        "publisher native object")
    local=Path(__file__).resolve().parent
    additions={
        base/"libpcsxcore/vh82_private_publish.c": local/"map02_v82_private_publish.c",
        base/"libpcsxcore/vh82_private_publish.h": local/"map02_v82_private_publish.h",
    }
    if any(p.exists() for p in additions): raise ValueError("existing v82 files")
    if any(not src.is_file() for src in additions.values()): raise ValueError("missing v82 source")
    frontend.write_text(fs)
    make.write_text(ms)
    for target,src in additions.items(): shutil.copyfile(src,target)
    return dict(proof,native_private_export_code_installed=True,
       actual_emulator_runtime_export_proven=False,
       physical_ps1_vblank_verified=False,original_retail_MAP02_verified=False,
       HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
