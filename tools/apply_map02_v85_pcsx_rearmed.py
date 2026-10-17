#!/usr/bin/env python3
"""Observe real native Unai C++ pixel stores, not just VRAM value snapshots.

Narrow opt-in in the pinned software GPU. Covers non-ASM 16-bit span, sprite,
tile, polygon stores and x86 Unai GP0(02) 32-bit clear stores. No GPU DMA
uploads, old Unai path, async tasks or physical PS1 hardware parity claims.
"""
import re
from pathlib import Path
from .apply_map02_v84_pcsx_rearmed import apply as apply_v84
from .apply_map02_v69_pcsx_rearmed import once

def apply(root: Path):
    proof=apply_v84(root)
    base=root.resolve()
    renderer=base/"plugins/gpu_unai/gpulib_if.cpp"
    inner=base/"plugins/gpu_unai/gpu_inner.h"
    image=base/"plugins/gpu_unai/gpu_raster_image.h"
    frontend=base/"frontend/main.c"
    originals={p:p.read_text() for p in (renderer,inner,image,frontend)}
    gpu=once(originals[renderer],
        '#include "gpu_inner.h"\n',
        '''#ifdef VH_MAP02_V66_PCSX_PROBE
#define VH85_STORE16(P,V) do { \\
  le16_t *const v85_dst=(P); le16_t v85_val=(V); \\
  if(vh84_sampling_enabled())vh85_note_store( \\
    le16_to_u16(*v85_dst),le16_to_u16(v85_val)); \\
  *v85_dst=v85_val; \\
} while(0)
#define VH85_STORE32(P,V) do { \\
  le32_t *const v85_dst=(P); le32_t v85_val=(V); \\
  if(vh84_sampling_enabled()) { \\
    u32 v85_old=le32_to_u32(*v85_dst),v85_new=le32_to_u32(v85_val); \\
    vh85_note_store(v85_old&65535u,v85_new&65535u); \\
    vh85_note_store(v85_old>>16,v85_new>>16); \\
  } \\
  *v85_dst=v85_val; \\
} while(0)
#else
#define VH85_STORE16(P,V) (*(P)=(V))
#define VH85_STORE32(P,V) (*(P)=(V))
#endif
#include "gpu_inner.h"
''',
        "install native destination-store wrappers before Unai inner templates")
    inner_src=originals[inner]
    pattern=r"\*pDst = u16_to_le16\(([^()\n]*)\);"
    inner_src,n=re.subn(pattern,r"VH85_STORE16(pDst,u16_to_le16(\1));",inner_src)
    if n!=22:raise ValueError(f"pinned Unai 16-bit store count drift: {n}")
    inner_src=once(inner_src,'do { *pDst++ = ldata; } while (--count);',
                        'do { VH85_STORE16(pDst,ldata); pDst++; } while (--count);',
                        "unmasked tile stores")
    inner_src=once(inner_src,'*pDst = ldata;','VH85_STORE16(pDst,ldata);',
                        "masked tile stores")
    if re.search(r"\*pDst(?:\+\+)?\s*=",inner_src):
        raise ValueError("unmonitored raw pDst pixel write remains in GPU inner templates")
    image_src=originals[image]
    for index in range(4):
        image_src=once(image_src,f'pixel[{index}] = rgb;',
                        f'VH85_STORE32(pixel+{index},rgb);',
                        f"native 2x16-bit GPU fill store {index}")
    gpu=once(gpu,
        '    switch (cmd)\n',
        '''#ifdef VH_MAP02_V66_PCSX_PROBE
    if(vh84_sampling_enabled())vh85_reset_command();
#endif
    switch (cmd)
''',
        "reset per-handler observed 16-bit store counts")
    gpu=once(gpu,
        '        vh80_record(VH84_UNAI_SAMPLE_DELTA,changed,0,0);\n'
        '      }\n'
        '    }\n',
        '        vh80_record(VH84_UNAI_SAMPLE_DELTA,changed,0,0);\n'
        '      }\n'
        '      if(vh84_sample) {\n'
        '        vh80_record(VH85_UNAI_STORE_COUNT,\n'
        '           vh85_write_overflow()?UINT32_MAX:vh85_store_count(),0,0);\n'
        '        vh80_record(VH85_UNAI_SAME_STORE_COUNT,vh85_same_store_count(),0,0);\n'
        '      }\n'
        '    }\n',
        "actual Unai native writes per handled opcode, after sampled value delta")
    fs=once(originals[frontend],
        '\tint vh84_sample_smoke = 0;\n',
        '\tint vh84_sample_smoke = 0;\n'
        '\tint vh85_native_store_smoke = 0;\n',
        "opt-in v85 native pixel store mode")
    fs=once(fs,
        '\t\telse if (!strcmp(argv[i], "--vh84-unai-vram-sample-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t}\n',
        '\t\telse if (!strcmp(argv[i], "--vh84-unai-vram-sample-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t}\n'
        '\t\telse if (!strcmp(argv[i], "--vh85-unai-pixel-store-smoke")) {\n'
        '\t\t\tvh78_vblank_smoke = 1;\n'
        '\t\t\tvh82_export_smoke = 1;\n'
        '\t\t\tvh83_renderer_smoke = 1;\n'
        '\t\t\tvh84_sample_smoke = 1;\n'
        '\t\t\tvh85_native_store_smoke = 1;\n'
        '\t\t}\n',
        "v85 signed synthetic scene CLI")
    fs=once(fs,
        'unsigned int observed_samples=0,observed_changed=0,observed_zero=0;',
        'unsigned int observed_samples=0,observed_changed=0,observed_zero=0;\n'
        '            unsigned int observed_stores=0,observed_same=0;\n'
        '            unsigned int observed_store_records=0,observed_same_records=0;\n'
        '            unsigned int observed_overflow=0;',
        "v85 store summation")
    fs=once(fs,
        'if(e->kind==VH84_UNAI_SAMPLE_DELTA) {',
        'if(e->kind==VH85_UNAI_STORE_COUNT) {\n'
        '                    observed_store_records++;\n'
        '                    if(e->value==UINT32_MAX)observed_overflow++;\n'
        '                    else observed_stores+=e->value;\n'
        '                }\n'
        '                if(e->kind==VH85_UNAI_SAME_STORE_COUNT) {\n'
        '                    observed_same_records++;\n'
        '                    observed_same+=e->value;\n'
        '                }\n'
        '                if(e->kind==VH84_UNAI_SAMPLE_DELTA) {',
        "v85 native store counters")
    fs=once(fs,
        '(vh84_sample_smoke && (observed_samples!=observed_unai ||',
        '(vh85_native_store_smoke && (observed_store_records!=observed_unai ||\n'
        '                 observed_same_records!=observed_unai || observed_overflow ||\n'
        '                 observed_stores<observed_same || observed_stores==0)) ||\n'
        '               (vh84_sample_smoke && (observed_samples!=observed_unai ||',
        "refuse missing, overflowed or inconsistent native store evidence")
    fs=once(fs,
        '                   observed_samples,observed_changed,observed_zero);',
        '                   observed_samples,observed_changed,observed_zero);\n'
        '            if(vh85_native_store_smoke)\n'
        '                SysPrintf("VH85_UNAI_STORES_PASS attempts=%u same_value=%u changed_value=%u handlers=%u\\n",\n'
        '                    observed_stores,observed_same,observed_stores-observed_same,\n'
        '                    observed_store_records);',
        "v85 observed actual 16-bit GPU stores")
    # Exact anchors and source coverage checked BEFORE any writes to checkout.
    for path,body in ((renderer,gpu),(inner,inner_src),(image,image_src),(frontend,fs)):
        path.write_text(body)
    return dict(proof,
        opt_in_unai_native_software_pixel_store_counters_installed=True,
        full_unai_dma_and_legacy_write_provenance_verified=False,
        actual_v85_emulator_runtime_proven=False,
        physical_ps1_vblank_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
