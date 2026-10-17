#!/usr/bin/env python3
"""Observe already-dispatched GP0 primitives in pinned Unai software renderer.

Records command HEADER after Unai's normal renderer switch; no pixel
causality, no VRAM-write claim. Old renderer / skipped commands not recorded.
"""
from pathlib import Path
from .apply_map02_v82_pcsx_rearmed import apply as apply_v82
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof=apply_v82(root)
    base=root.resolve()
    renderer=base/"plugins/gpu_unai/gpulib_if.cpp"
    frontend=base/"frontend/main.c"
    raw=renderer.read_text()
    raw=once(raw,
        '#include "old/if.h"\n',
        '#include "old/if.h"\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '#include "../../libpcsxcore/vh80_native_timeline.h"\n'
        '#endif\n',
        "Unai renderer observer header")
    raw=once(raw,
        '      } break;\n    }\n  }\n\nbreakloop:\n',
        '      } break;\n    }\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '    /* AFTER Unai dispatch, never before its command switch.\n'
        '     * Only recognized renderer-owned commands, never gpulib\n'
        '     * A0 uploads, C0 readbacks or skipped/incomplete commands.\n'
        '     * cycle/frame 0 mean unavailable at this plugin callsite. */\n'
        '    if (cmd == 0x02 || (cmd >= 0x20 && cmd <= 0x43) ||\n'
        '        (cmd >= 0x48 && cmd <= 0x53) ||\n'
        '        (cmd >= 0x58 && cmd <= 0x6b) ||\n'
        '        (cmd >= 0x70 && cmd <= 0x7f) ||\n'
        '        (cmd >= 0xe1 && cmd <= 0xe6))\n'
        '      vh80_record(VH83_GP0_UNAI_HANDLED,le32_to_u32(*list),0,0);\n'
        '#endif\n'
        '  }\n\nbreakloop:\n',
        "Unai handled-GP0 switch exit")
    fs=frontend.read_text()
    fs=once(fs,
        '\tint vh82_export_smoke = 0;\n',
        '\tint vh82_export_smoke = 0;\n'
        '\tint vh83_renderer_smoke = 0;\n',
        "v83 opt-in flag")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh82-private-export-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t}\n',
        '\t\telse if (!strcmp(argv[i], "--vh82-private-export-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t}\n'
        '\t\telse if (!strcmp(argv[i], "--vh83-unai-gp0-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t}\n',
        "v83 opt-in CLI")
    fs=once(fs,
        'unsigned int observed_edges=0,observed_gp1=0;',
        'unsigned int observed_edges=0,observed_gp1=0,observed_unai=0;',
        "renderer event counter")
    fs=once(fs,
        'if(e->kind==VH80_GP1_MMIO)observed_gp1++;',
        'if(e->kind==VH80_GP1_MMIO)observed_gp1++;\n'
        '                if(e->kind==VH83_GP0_UNAI_HANDLED)observed_unai++;',
        "count only dispatched renderer events")
    fs=once(fs,
        'if(observed_edges!=4 || observed_gp1<2 || vh80_dropped()!=0 ||',
        'if(observed_edges!=4 || observed_gp1<2 ||\n'
        '               (vh83_renderer_smoke && observed_unai==0) ||\n'
        '               vh80_dropped()!=0 ||',
        "require observed Unai dispatch")
    fs=once(fs,
        '            SysPrintf("VH82_PRIVATE_EXPORT_PASS vblanks=',
        '            if(vh83_renderer_smoke)\n'
        '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);\n'
        '            SysPrintf("VH82_PRIVATE_EXPORT_PASS vblanks=',
        "v83 status after successful private export")
    # Validate all anchors before mutating the disposable checkout.
    renderer.write_text(raw)
    frontend.write_text(fs)
    return dict(proof, native_unai_gp0_handler_observer_installed=True,
        native_gp0_opcode_handler_event_proven=False,
        native_gp0_raster_pixel_causality_verified=False,
        native_vram_write_trace_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
