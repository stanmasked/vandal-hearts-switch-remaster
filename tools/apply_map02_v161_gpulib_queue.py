#!/usr/bin/env python3
"""v161: witness the fifth synthetic GP0 word stored by genuine gpulib GPUwriteData.

v160 proves callback entry and return; GPUwriteData itself merely enqueues
words until a later command-buffer flush. v161 checks the actual pinned gpulib
append, without claiming command interpretation, VRAM changes or pixels.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v160_plugin_callback import apply as apply_v160
from .apply_map02_v69_pcsx_rearmed import once

QUEUE_APPEND = "  gpu.cmd_buffer[gpu.cmd_len++] = HTOLE32(data);"
GPU_ENTRY = "void GPUwriteData(uint32_t data)\n{"


def queue_probe_c() -> str:
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* v161: only the armed, source-authored synthetic fifth GP0 SW. */
static unsigned vh161_queue_active, vh161_queue_count, vh161_queue_bad;
static int vh161_queue_start_len;
int vh161_arm_gpu_queue(void) {
    if(vh161_queue_active || gpu.cmd_len<0 ||
       gpu.cmd_len>=CMD_BUFFER_LEN) return -1;
    vh161_queue_active=1u;
    vh161_queue_count=vh161_queue_bad=0u;
    vh161_queue_start_len=gpu.cmd_len;
    return 0;
}
static void vh161_observe_gpu_queue(uint32_t value) {
    if(!vh161_queue_active) return;
    if(value!=0xe3000000u ||
       gpu.cmd_len<=0 || gpu.cmd_len>CMD_BUFFER_LEN ||
       gpu.cmd_len!=vh161_queue_start_len+(int)vh161_queue_count+1 ||
       gpu.cmd_buffer[gpu.cmd_len-1]!=HTOLE32(value)) {
        vh161_queue_bad++;
        return;
    }
    if(vh161_queue_count<2u) vh161_queue_count++;
    else vh161_queue_bad++;
}
unsigned vh161_gpu_queue_stores(void) {return vh161_queue_count;}
unsigned vh161_gpu_queue_faults(void) {return vh161_queue_bad;}
int vh161_disarm_gpu_queue(void) {
    if(!vh161_queue_active) return -1;
    vh161_queue_active=0u;
    return 0;
}
#endif

"""


def patch_gpu(source: str) -> str:
    if "vh161_observe_gpu_queue" in source:
        raise ValueError("v161 queue observer already installed")
    if source.count(QUEUE_APPEND)!=1 or source.count(GPU_ENTRY)!=1:
        raise ValueError("pinned GPUwriteData storage site absent or duplicated")
    source=once(source,GPU_ENTRY,queue_probe_c()+GPU_ENTRY,
                "native gpulib GPUwriteData queue observer")
    return once(source,QUEUE_APPEND,
        QUEUE_APPEND+"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "  vh161_observe_gpu_queue(data);\n#endif",
        "actual queue append, immediately following original gpulib store")


def patch_frontend(source: str) -> str:
    source=once(source, "\textern int vh160_disarm_plugin_callback(void);\n",
        "\textern int vh160_disarm_plugin_callback(void);\n"
        "\textern int vh161_arm_gpu_queue(void);\n"
        "\textern unsigned vh161_gpu_queue_stores(void);\n"
        "\textern unsigned vh161_gpu_queue_faults(void);\n"
        "\textern int vh161_disarm_gpu_queue(void);\n",
        "declare independent GPU command buffer observer")
    arm=(
        "                    if(vh160_arm_plugin_callback()!=0){\n"
        '                        SysPrintf("VH160_CALLBACK_ARM_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 63;\n"
        "                    }\n")
    source=once(source,arm,arm+
        "                    if(vh161_arm_gpu_queue()!=0){\n"
        '                        SysPrintf("VH161_QUEUE_ARM_REFUSED\\n");\n'
        "                        (void)vh160_disarm_plugin_callback();\n"
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 64;\n"
        "                    }\n",
        "arm gpulib witness only after existing source-bound GPU callback")
    source=once(source,
        "                    int callback_restored=vh160_disarm_plugin_callback();\n",
        "                    int callback_restored=vh160_disarm_plugin_callback();\n"
        "                    unsigned queue=vh161_gpu_queue_stores();\n"
        "                    unsigned queue_bad=vh161_gpu_queue_faults();\n"
        "                    int queue_disarmed=vh161_disarm_gpu_queue();\n",
        "read real gpulib enqueue counters and explicitly disarm")
    source=once(source,
        "callback_bad!=0u || callback_restored!=0){",
        "callback_bad!=0u || callback_restored!=0 ||\n"
        "                           queue!=0u || queue_bad!=0u || queue_disarmed!=0){",
        "mutated fifth may not append any GP0 word")
    source=once(source,
        "callback_bad!=0u || callback_restored!=0 ||",
        "callback_bad!=0u || callback_restored!=0 ||\n"
        "                       queue!=1u || queue_bad!=0u || queue_disarmed!=0 ||",
        "positive native GP0 command must enqueue exactly once")
    source=once(source,
        '                        SysPrintf("VH160_NATIVE_FIFTH_CALLBACK_REFUSED"',
        '                        SysPrintf("VH161_NATIVE_FIFTH_QUEUE_REFUSED"'
        '" stored=0 original_retail=0\\n");\n'
        '                        SysPrintf("VH160_NATIVE_FIFTH_CALLBACK_REFUSED"',
        "add negative source-observed GP0 queue marker")
    source=once(source,
        '                    SysPrintf("VH160_NATIVE_PLUGIN_CALLBACK_PASS"',
        '                    SysPrintf("VH161_NATIVE_GPULIB_QUEUE_PASS"'
        '" stored=1 original_retail=0\\n");\n'
        '                    SysPrintf("VH160_NATIVE_PLUGIN_CALLBACK_PASS"',
        "add positive real gpulib queue marker")
    return source


def apply(root: Path):
    proof=apply_v160(root)
    base=root.resolve()
    gpu=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"
    gpu.write_text(patch_gpu(gpu.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(proof,
        v161_native_gpulib_gp0_append_verified=True,
        v161_synthetic_fifth_mutation_queue_absent=True,
        v161_unai_command_interpretation_verified=False,
        v161_gpu_pixel_output_verified=False,
        v161_original_retail_map02_executed=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
