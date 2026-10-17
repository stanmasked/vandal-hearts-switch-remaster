#!/usr/bin/env python3
"""Opt-in pinned Unai pre/post readback at 24 known synthetic pixels.

Observes final values immediately before/after renderer handler switch.
A zero delta does NOT distinguish no write from a same-value write.
"""
from pathlib import Path
from .apply_map02_v83_pcsx_rearmed import apply as apply_v83
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof=apply_v83(root)
    base=root.resolve()
    renderer=base/"plugins/gpu_unai/gpulib_if.cpp"
    frontend=base/"frontend/main.c"
    raw=renderer.read_text()
    fs=frontend.read_text()
    raw=once(raw,
        '    PtrUnion packet = { .ptr = (void*)&gpu_unai.PacketBuffer };\n\n    switch (cmd)\n',
        '    PtrUnion packet = { .ptr = (void*)&gpu_unai.PacketBuffer };\n'
        '#ifdef VH_MAP02_V66_PCSX_PROBE\n'
        '    /* Only sampled source VRAM 40/56/.../120 x 160..163, no writes. */\n'
        '    unsigned int vh84_before[24];\n'
        '    const int vh84_sample=vh84_sampling_enabled() && gpu_unai.vram!=NULL;\n'
        '    if(vh84_sample) {\n'
        '      for(unsigned int yi=0;yi<4;yi++)\n'
        '        for(unsigned int xi=0;xi<6;xi++)\n'
        '          vh84_before[yi*6+xi]=le16_to_u16(\n'
        '             gpu_unai.vram[(160+yi)*1024+40+16*xi]);\n'
        '    }\n'
        '#endif\n'
        '\n    switch (cmd)\n',
        "sample original Unai VRAM before handler")
    raw=once(raw,
        '      vh80_record(VH83_GP0_UNAI_HANDLED,le32_to_u32(*list),0,0);\n',
        '    {\n'
        '      vh80_record(VH83_GP0_UNAI_HANDLED,le32_to_u32(*list),0,0);\n'
        '      if(vh84_sample) {\n'
        '        unsigned int changed=0;\n'
        '        for(unsigned int yi=0;yi<4;yi++)\n'
        '          for(unsigned int xi=0;xi<6;xi++)\n'
        '            changed+=(vh84_before[yi*6+xi]!=le16_to_u16(\n'
        '              gpu_unai.vram[(160+yi)*1024+40+16*xi]));\n'
        '        vh80_record(VH84_UNAI_SAMPLE_DELTA,changed,0,0);\n'
        '      }\n'
        '    }\n',
        "compare exactly 24 post-handler Unai source VRAM samples")
    fs=once(fs,
        '\tint vh83_renderer_smoke = 0;\n',
        '\tint vh83_renderer_smoke = 0;\n'
        '\tint vh84_sample_smoke = 0;\n',
        "v84 opt-in flag")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh83-unai-gp0-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t}\n',
        '\t\telse if (!strcmp(argv[i], "--vh83-unai-gp0-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t}\n'
        '\t\telse if (!strcmp(argv[i], "--vh84-unai-vram-sample-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t}\n',
        "v84 CLI flag")
    fs=once(fs,
        'if(vh82_export_smoke)vh80_reset();',
        'if(vh82_export_smoke)vh80_reset();\n'
        '\t\tif(vh84_sample_smoke)vh84_set_sampling(1);',
        "enable read-only comparison only after signed synthetic EXE accepted")
    fs=once(fs,
        'unsigned int observed_edges=0,observed_gp1=0,observed_unai=0;',
        'unsigned int observed_edges=0,observed_gp1=0,observed_unai=0;\n'
        '            unsigned int observed_samples=0,observed_changed=0,observed_zero=0;',
        "v84 sample summary state")
    fs=once(fs,
        'if(e->kind==VH83_GP0_UNAI_HANDLED)observed_unai++;',
        'if(e->kind==VH83_GP0_UNAI_HANDLED)observed_unai++;\n'
        '                if(e->kind==VH84_UNAI_SAMPLE_DELTA) {\n'
        '                    observed_samples++;\n'
        '                    if(e->value>0)observed_changed++;\n'
        '                    else observed_zero++;\n'
        '                }',
        "count post-handler sample change categories")
    fs=once(fs,
        '(vh83_renderer_smoke && observed_unai==0) ||',
        '(vh83_renderer_smoke && observed_unai==0) ||\n'
        '               (vh84_sample_smoke && (observed_samples!=observed_unai ||\n'
        '                                      observed_changed==0 || observed_zero==0)) ||',
        "require paired changed and unchanged samples")
    fs=once(fs,
        '            if(vh83_renderer_smoke)\n'
        '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);',
        '            if(vh83_renderer_smoke)\n'
        '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);\n'
        '            if(vh84_sample_smoke)\n'
        '                SysPrintf("VH84_UNAI_SAMPLES_PASS comparisons=%u changed_handlers=%u unchanged_handlers=%u\\n",\n'
        '                   observed_samples,observed_changed,observed_zero);',
        "v84 status after verified private report")
    renderer.write_text(raw)
    frontend.write_text(fs)
    return dict(proof, native_unai_24_vram_samples_before_after_handler_installed=True,
       observed_vram_sample_deltas_proven=False,
       individual_PutPixel_or_same_value_write_proven=False,
       physical_ps1_vblank_verified=False,
       original_retail_MAP02_verified=False,
       HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
