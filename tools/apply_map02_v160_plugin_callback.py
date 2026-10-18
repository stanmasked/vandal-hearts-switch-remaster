#!/usr/bin/env python3
"""v160: count actual GPU_writeData plugin callback entry and return.

Opt-in ONLY for the source-verified five-instruction synthetic native guest.
This wraps the installed GPU_writeData function pointer; it forwards the exact
unchanged word to the existing callback and observes its return. No user media,
retail PS1 code, GPU pixels, or Switch gameplay is involved.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v159_native_gpu_sink import apply as apply_v159
from .apply_map02_v69_pcsx_rearmed import once

PLUGIN_ANCHOR = "/* Independent synthetic harness may reset just these pointers. */"


def callback_probe_c() -> str:
    return r"""
/* v160 generated-only diagnostic, no additional GPU packets or logging. */
static GPUwriteData vh160_saved_writeData;
static unsigned vh160_active, vh160_entered, vh160_returned, vh160_bad;
static void CALLBACK vh160_callback(uint32_t value) {
    if(vh160_active) {
        if(value!=0xe3000000u) vh160_bad++;
        else if(vh160_entered<2u) vh160_entered++;
    }
    /* Forward the SAME word to the previously installed real callback. */
    vh160_saved_writeData(value);
    if(vh160_active && value==0xe3000000u && vh160_returned<2u)
        vh160_returned++;
}
int vh160_arm_plugin_callback(void) {
    if(vh160_active || !GPU_writeData ||
       GPU_writeData==vh160_callback) return -1;
    vh160_saved_writeData=GPU_writeData;
    vh160_entered=vh160_returned=vh160_bad=0u;
    vh160_active=1u;
    GPU_writeData=vh160_callback;
    return 0;
}
unsigned vh160_callback_enters(void) {return vh160_entered;}
unsigned vh160_callback_returns(void) {return vh160_returned;}
unsigned vh160_callback_faults(void) {return vh160_bad;}
int vh160_disarm_plugin_callback(void) {
    if(!vh160_active) return -1;
    vh160_active=0u;
    if(GPU_writeData!=vh160_callback) {
        vh160_bad++;
        vh160_saved_writeData=0;
        return -1; /* Preserve any third-party pointer change, fail closed. */
    }
    GPU_writeData=vh160_saved_writeData;
    vh160_saved_writeData=0;
    return 0;
}
"""


def patch_plugin(source: str) -> str:
    if "vh160_arm_plugin_callback" in source:
        raise ValueError("refusing double plugin callback instrumentation")
    if "static void CALLBACK wrapped_writeData(uint32_t word)" not in source:
        raise ValueError("required v69 callback chain is absent")
    return once(source,PLUGIN_ANCHOR,callback_probe_c()+"\n"+PLUGIN_ANCHOR,
                "append opt-in wrapper to original v69 GPU callback chain")


def patch_frontend(source: str) -> str:
    source=once(source, "\textern void vh159_disarm_gpu_sink(void);\n",
        "\textern void vh159_disarm_gpu_sink(void);\n"
        "\textern int vh160_arm_plugin_callback(void);\n"
        "\textern unsigned vh160_callback_enters(void);\n"
        "\textern unsigned vh160_callback_returns(void);\n"
        "\textern unsigned vh160_callback_faults(void);\n"
        "\textern int vh160_disarm_plugin_callback(void);\n",
        "declare v160 plugin callback entry/return witness")
    source=once(source, "                    vh159_arm_gpu_sink();\n",
        "                    vh159_arm_gpu_sink();\n"
        "                    if(vh160_arm_plugin_callback()!=0){\n"
        '                        SysPrintf("VH160_CALLBACK_ARM_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 63;\n"
        "                    }\n",
        "arm plugin callback only for verified native synthetic fifth SW")
    source=once(source,"                    unsigned sink_bad=vh159_sink_faults();\n",
        "                    unsigned sink_bad=vh159_sink_faults();\n"
        "                    unsigned callback_enters=vh160_callback_enters();\n"
        "                    unsigned callback_returns=vh160_callback_returns();\n"
        "                    unsigned callback_bad=vh160_callback_faults();\n"
        "                    int callback_restored=vh160_disarm_plugin_callback();\n",
        "read and restore real GPU callback pointer before exit")
    source=once(source,"sink!=0u || sink_bad!=0u){",
        "sink!=0u || sink_bad!=0u ||\n"
        "                           callback_enters!=0u || callback_returns!=0u ||\n"
        "                           callback_bad!=0u || callback_restored!=0){",
        "negative fifth mutation must never enter plugin callback")
    source=once(source,"sink!=1u || sink_bad!=0u ||",
        "sink!=1u || sink_bad!=0u ||\n"
        "                       callback_enters!=1u || callback_returns!=1u ||\n"
        "                       callback_bad!=0u || callback_restored!=0 ||",
        "require one real plugin callback entry and its return")
    source=once(source, '                        SysPrintf("VH159_NATIVE_FIFTH_SINK_REFUSED"',
        '                        SysPrintf("VH160_NATIVE_FIFTH_CALLBACK_REFUSED"'
        '" entered=0 returned=0 original_retail=0\\n");\n'
        '                        SysPrintf("VH159_NATIVE_FIFTH_SINK_REFUSED"',
        "positive refusal of corrupted fifth before callback invocation")
    source=once(source, '                    SysPrintf("VH159_NATIVE_GPU_SINK_PASS"',
        '                    SysPrintf("VH160_NATIVE_PLUGIN_CALLBACK_PASS"'
        '" entered=1 returned=1 original_retail=0\\n");\n'
        '                    SysPrintf("VH159_NATIVE_GPU_SINK_PASS"',
        "report real callback entry and return without claiming rasterization")
    return source


def apply(root: Path):
    previous=apply_v159(root)
    base=root.resolve()
    plugin=base/"libpcsxcore/vh69_gpu_plugin_wrap.c"
    main=base/"frontend/main.c"
    plugin.write_text(patch_plugin(plugin.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(previous,
        v160_synthetic_native_gpu_callback_enter_return=True,
        v160_mutated_fifth_callback_count_zero=True,
        v160_original_retail_execution=False,
        v160_gpu_pixel_change_verified=False,
        v160_switch_hd_parity_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
