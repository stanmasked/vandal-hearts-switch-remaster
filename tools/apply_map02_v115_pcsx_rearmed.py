#!/usr/bin/env python3
"""v115 opt-in exact identity of 24 VRAM sample values in native Unai memory.

Extends v104 synthetic host smoke but never changes canonical private v82 JSONL.
Only the three aggregate identity classes and VBlank cross-split leave the
ephemeral native sample cache; no raw 16-bit pixel values or hash exposed.
"""
from pathlib import Path
import shutil

from .apply_map02_v104_pcsx_rearmed import apply as apply_v104
from .apply_map02_v69_pcsx_rearmed import once


def apply(root: Path):
    proof=apply_v104(root)
    base=root.resolve()
    gpu_file=base/"plugins/gpu_unai/gpulib_if.cpp"
    src_file=base/"libpcsxcore/vh80_native_timeline.c"
    make_file=base/"Makefile"
    frontend=base/"frontend/main.c"
    original={p:p.read_text() for p in (gpu_file,src_file,make_file,frontend)}

    gpu=once(original[gpu_file],
       '#include "../../libpcsxcore/vh80_native_timeline.h"\n',
       '#include "../../libpcsxcore/vh80_native_timeline.h"\n'
       '#include "../../libpcsxcore/vh115_sample_identity.h"\n',
       "Unai opt-in exact sample sidecar declaration")
    gpu=once(gpu,
       '        vh80_record(VH84_UNAI_SAMPLE_DELTA,changed,0,0);\n',
       '        vh80_record(VH84_UNAI_SAMPLE_DELTA,changed,0,0);\n'
       '        /* Compare actual 24 final values in native memory, never export. */\n'
       '        uint16_t vh115_post[24];\n'
       '        for(unsigned int yi=0;yi<4;yi++)\n'
       '          for(unsigned int xi=0;xi<6;xi++)\n'
       '            vh115_post[yi*6+xi]=(uint16_t)le16_to_u16(\n'
       '              gpu_unai.vram[(160+yi)*1024+40+16*xi]);\n'
       '        vh115_note(vh115_post,24u,changed);\n'
       '        volatile uint16_t *vh115_wipe=vh115_post;\n'
       '        for(unsigned int vi=0;vi<24;vi++)vh115_wipe[vi]=0;\n',
       "Unai exact 24-point final-value classification with ephemeral scrub")

    observer=once(original[src_file],
        '#include "vh80_native_timeline.h"\n',
        '#include "vh80_native_timeline.h"\n'
        '#include "vh115_sample_identity.h"\n',
        "sidecar C declaration")
    observer=once(observer,
        '  vh84_sampling=0;vh85_reset_command();vh86_reset();',
        '  vh84_sampling=0;vh85_reset_command();vh86_reset();\n'
        '  vh115_reset();',
        "reset must erase previous sample cache")
    observer=once(observer,
        '    e->cycle=cycle;e->frame=frame;',
        '    e->cycle=cycle;e->frame=frame;\n'
        '    if(kind==VH80_VBLANK)vh115_vblank();',
        "record VBlank epoch after successful original timeline append")
    make=once(original[make_file],
        'OBJS += libpcsxcore/vh80_native_timeline.o\n',
        'OBJS += libpcsxcore/vh80_native_timeline.o\n'
        'OBJS += libpcsxcore/vh115_sample_identity.o\n',
        "add observer native build only in pinned probe patch")

    main=once(original[frontend],
        '#include "../libpcsxcore/vh80_native_timeline.h"\n',
        '#include "../libpcsxcore/vh80_native_timeline.h"\n'
        '#include "../libpcsxcore/vh115_sample_identity.h"\n',
        "main native identity summary declaration")
    main=once(main,
        'if(vh84_sample_smoke)vh84_set_sampling(1);',
        'if(vh84_sample_smoke)vh84_set_sampling(1);\n'
        '\t\tif(vh104_content_smoke)vh115_enable(1);',
        "enable only after authenticated signed synthetic smoke setup")
    anchor=(
        '            if(vh83_renderer_smoke)\n'
        '                SysPrintf("VH83_UNAI_DISPATCH_PASS handled=%u\\n",observed_unai);'
    )
    verify=(
        '            if(vh104_content_smoke) {\n'
        '                vh115_metrics identity;\n'
        '                if(vh115_get_metrics(&identity)!=0 ||\n'
        '                   identity.handlers!=observed_unai ||\n'
        '                   identity.vblank_edges!=observed_edges ||\n'
        '                   identity.equal_delta_identical_24_values+\n'
        '                   identity.equal_delta_different_24_values+\n'
        '                   identity.different_delta_counts!=observed_unai-1){\n'
        '                    SysPrintf("VH115_IDENTITY_REFUSED\\n");\n'
        '                    ClosePlugins();SysClose();menu_finish();plat_finish();return 31;\n'
        '                }\n'
        '                SysPrintf("VH115_SAMPLE_IDENTITY_PASS handlers=%u vblanks=%u identical_count_equal_values=%u identical_count_different_values=%u different_count=%u cross_equal_values=%u cross_different_values=%u cross_different_count=%u\\n",\n'
        '                    identity.handlers,identity.vblank_edges,\n'
        '                    identity.equal_delta_identical_24_values,\n'
        '                    identity.equal_delta_different_24_values,\n'
        '                    identity.different_delta_counts,\n'
        '                    identity.cross_vblank_equal_delta_identical,\n'
        '                    identity.cross_vblank_equal_delta_different,\n'
        '                    identity.cross_vblank_different_delta);\n'
        '            }\n'
    )
    main=once(main,anchor,verify+anchor,
              "prove actual in-process 24-sample equality classifications")

    sources=Path(__file__).resolve().parent
    additions={
        base/"libpcsxcore/vh115_sample_identity.c":sources/"map02_v115_sample_identity.c",
        base/"libpcsxcore/vh115_sample_identity.h":sources/"map02_v115_sample_identity.h",
    }
    if any(t.exists() for t in additions):
        raise ValueError("refusing pre-existing v115 native observer source")
    if any(not s.is_file() for s in additions.values()):
        raise ValueError("missing v115 native sidecar")
    for p,body in ((gpu_file,gpu),(src_file,observer),
                   (make_file,make),(frontend,main)):
        p.write_text(body)
    for dst,src in additions.items():
        shutil.copyfile(src,dst)
    return dict(proof,
        actual_24_sample_values_compared_only_inside_native_memory=True,
        same_changed_sample_count_not_assumed_pixel_identity=True,
        canonical_v82_private_jsonl_unchanged=True,
        physical_PS1_verified=False,
        original_retail_MAP02_verified=False,
        HD_replacement_approved=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
