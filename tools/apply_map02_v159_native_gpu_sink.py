#!/usr/bin/env python3
"""v159: witness the fifth synthetic MIPS GP0 SW at native GPU_writeData dispatch.

The v158 memory-write witness proves one psxMemWrite32 event. This independent
observer is inserted at the pinned psxHwWrite32 GP0 dispatch, immediately before
GPU_writeData. It does NOT prove GPU plugin consumption, raster output, or
original retail gameplay. Fail closed on extra, altered or missing events.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v158_native_gp0_fifth import apply as apply_v158
from .apply_map02_v69_pcsx_rearmed import once

GPU_DISPATCH = "case 0x1810: GPU_writeData(value); return;"


def sink_observer_c() -> str:
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Source-authored synthetic fifth SW only. Never emit source/private values. */
static unsigned vh159_sink_active, vh159_sink_count, vh159_sink_bad;
void vh159_arm_gpu_sink(void) {
    vh159_sink_active=1u; vh159_sink_count=0u; vh159_sink_bad=0u;
}
static void vh159_capture_sink(psxRegisters *regs, u32 addr, u32 value) {
    if(!vh159_sink_active) return;
    if((addr&0x1fffffffu)!=0x1f801810u ||
       value!=0xe3000000u ||
       regs->pc!=0x80010014u ||
       regs->code!=0xad090000u) {
        vh159_sink_bad++;
        return;
    }
    vh159_sink_count++;
}
unsigned vh159_sink_writes(void) { return vh159_sink_count; }
unsigned vh159_sink_faults(void) { return vh159_sink_bad; }
void vh159_disarm_gpu_sink(void) { vh159_sink_active=0u; }
#endif

"""


def patch_hardware(source: str) -> str:
    if "vh159_capture_sink" in source:
        raise ValueError("GPU sink observer already installed")
    source=once(
        source, "void psxHwWrite32(psxRegisters *regs, u32 add, u32 value) {",
        sink_observer_c()+"void psxHwWrite32(psxRegisters *regs, u32 add, u32 value) {",
        "add GPU dispatch observer on original native psxHwWrite32",
    )
    return once(source, GPU_DISPATCH,
        """case 0x1810:
#ifdef VH_MAP02_V66_PCSX_PROBE
        if(vh159_sink_active) vh159_capture_sink(regs,add,value);
#endif
        GPU_writeData(value); return;""",
        "observe real GP0 case immediately before actual GPU_writeData call")


def patch_frontend(source: str) -> str:
    source=once(source, "\textern void vh158_disarm_gp0(void);\n",
        "\textern void vh158_disarm_gp0(void);\n"
        "\textern void vh159_arm_gpu_sink(void);\n"
        "\textern unsigned vh159_sink_writes(void);\n"
        "\textern unsigned vh159_sink_faults(void);\n"
        "\textern void vh159_disarm_gpu_sink(void);\n",
        "front end bound to dedicated GPU dispatch sink")
    source=once(source, "                    vh158_arm_gp0();\n",
        "                    vh158_arm_gp0();\n"
        "                    vh159_arm_gpu_sink();\n",
        "arm native dispatch witness only after source-verified RAM")
    source=once(source, "                    unsigned gp0_bad=vh158_gp0_faults();\n",
        "                    unsigned gp0_bad=vh158_gp0_faults();\n"
        "                    unsigned sink=vh159_sink_writes();\n"
        "                    unsigned sink_bad=vh159_sink_faults();\n",
        "obtain independently counted native hardware GP0 sink")
    source=once(source, "                    vh158_disarm_gp0();\n",
        "                    vh158_disarm_gp0();\n"
        "                    vh159_disarm_gpu_sink();\n",
        "disarm both pre-dispatch and GPU sinks before result classification")
    source=once(source, "gp0!=0u || gp0_bad!=0u){",
        "gp0!=0u || gp0_bad!=0u ||\n"
        "                           sink!=0u || sink_bad!=0u){",
        "negative fifth mutation must not reach GPU sink")
    source=once(source, "gp0!=1u || gp0_bad!=0u ||",
        "gp0!=1u || gp0_bad!=0u ||\n"
        "                       sink!=1u || sink_bad!=0u ||",
        "native GPU sink must receive exactly one matching fifth SW")
    source=once(source, '                        SysPrintf("VH158_NATIVE_FIFTH_OPCODE_REFUSED"',
        '                        SysPrintf("VH159_NATIVE_FIFTH_SINK_REFUSED"'
        '" sink_writes=0 original_retail=0\\n");\n'
        '                        SysPrintf("VH158_NATIVE_FIFTH_OPCODE_REFUSED"',
        "publish bounded negative native dispatch witness")
    source=once(source, '                    SysPrintf("VH158_NATIVE_GP0_FIFTH_PASS"',
        '                    SysPrintf("VH159_NATIVE_GPU_SINK_PASS"'
        '" sink_writes=1 original_retail=0\\n");\n'
        '                    SysPrintf("VH158_NATIVE_GP0_FIFTH_PASS"',
        "publish verified native GP0-to-GPU dispatch marker")
    return source


def apply(root: Path):
    previous=apply_v158(root)
    base=root.resolve()
    hw=base/"libpcsxcore/psxhw.c"
    main=base/"frontend/main.c"
    hw.write_text(patch_hardware(hw.read_text()))
    main.write_text(patch_frontend(main.read_text()))
    return dict(previous,
        v159_synthetic_gp0_hardware_dispatch_exact_once=True,
        v159_mutated_fifth_no_gpu_sink=True,
        v159_original_retail_gpu_plugin_consumption_verified=False,
        v159_original_map02_frame_verified=False,
        v159_switch_hd_parity_verified=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
