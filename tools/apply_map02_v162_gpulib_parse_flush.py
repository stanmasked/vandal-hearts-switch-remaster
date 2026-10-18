#!/usr/bin/env python3
"""v162: prove one genuine gpulib command-parser visit and completed flush.

v161 proves native GP0 buffering. This stage forces the existing GPU_readStatus
flush exclusively in the strict self-authored five-opcode synthetic test, and
counts that the exact E3 word reaches do_cmd_buffer and leaves no queue tail.
No pixels, original game source or renderer output are claimed.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v161_gpulib_queue import apply as apply_v161
from .apply_map02_v69_pcsx_rearmed import once

GPU_DECL="struct psx_gpu gpu;\n"
PARSE_ANCHOR="    cmd = LE32TOH(data[pos]) >> 24;"
FLUSH_ANCHOR=(
    "  left = do_cmd_buffer(gpu, gpu->cmd_buffer, gpu->cmd_len, "
    "&dummy, &cycles_last);")


def parser_witness_c() -> str:
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* No modification of renderer commands, queue contents or GPU status. */
static unsigned vh162_active, vh162_parsed, vh162_flushed, vh162_bad;
int vh162_arm_gpu_parser(void) {
    if(vh162_active || gpu.cmd_len!=0) return -1;
    vh162_active=1u; vh162_parsed=vh162_flushed=vh162_bad=0u;
    return 0;
}
static void vh162_note_gpu_parse(struct psx_gpu *state, uint32_t *words,
                                 int pos, int count, int cmd) {
    if(!vh162_active) return;
    if(state!=&gpu || words!=gpu.cmd_buffer ||
       gpu.cmd_len!=1 || pos!=0 || count!=1 ||
       cmd!=0xe3 || LE32TOH(words[pos])!=0xe3000000u ||
       vh162_parsed!=0u) {
        vh162_bad++;
        return;
    }
    vh162_parsed++;
}
static void vh162_note_gpu_flush(struct psx_gpu *state, int remaining) {
    if(!vh162_active) return;
    if(state!=&gpu || gpu.cmd_len!=1 || remaining!=0 ||
       vh162_parsed!=1u || vh162_flushed!=0u) {
        vh162_bad++;
        return;
    }
    vh162_flushed++;
}
unsigned vh162_gpu_parse_visits(void) {return vh162_parsed;}
unsigned vh162_gpu_flushes(void) {return vh162_flushed;}
unsigned vh162_gpu_parse_faults(void) {return vh162_bad;}
int vh162_disarm_gpu_parser(void) {
    if(!vh162_active) return -1;
    vh162_active=0u;
    return 0;
}
#endif

"""


def patch_gpu(source: str) -> str:
    if "vh162_note_gpu_parse" in source:
        raise ValueError("v162 parser observer already installed")
    source=once(source,GPU_DECL,GPU_DECL+parser_witness_c(),
                "one original gpulib global GPU state")
    source=once(source,PARSE_ANCHOR,
        PARSE_ANCHOR+"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh162_note_gpu_parse(gpu, data, pos, count, cmd);\n#endif",
        "one original gpulib command parser opcode decode")
    return once(source,FLUSH_ANCHOR,
        FLUSH_ANCHOR+"\n#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "  vh162_note_gpu_flush(gpu, left);\n#endif",
        "original gpulib buffered command consumption site")


def patch_frontend(source: str) -> str:
    source=once(source,"\textern int vh161_disarm_gpu_queue(void);\n",
        "\textern int vh161_disarm_gpu_queue(void);\n"
        "\textern int vh162_arm_gpu_parser(void);\n"
        "\textern unsigned vh162_gpu_parse_visits(void);\n"
        "\textern unsigned vh162_gpu_flushes(void);\n"
        "\textern unsigned vh162_gpu_parse_faults(void);\n"
        "\textern int vh162_disarm_gpu_parser(void);\n",
        "declare genuine gpulib parser and flush witness")
    arm=(
        "                    if(vh161_arm_gpu_queue()!=0){\n"
        '                        SysPrintf("VH161_QUEUE_ARM_REFUSED\\n");\n'
        "                        (void)vh160_disarm_plugin_callback();\n"
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 64;\n"
        "                    }\n")
    source=once(source,arm,arm+
        "                    if(vh162_arm_gpu_parser()!=0){\n"
        '                        SysPrintf("VH162_PARSER_ARM_REFUSED\\n");\n'
        "                        (void)vh161_disarm_gpu_queue();\n"
        "                        (void)vh160_disarm_plugin_callback();\n"
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 65;\n"
        "                    }\n",
        "enable native parser witness only for source-checked synthetic run")
    source=once(source,"                    unsigned queue=vh161_gpu_queue_stores();\n",
        "                    /* Synthetic test only: original GPU read-status\n"
        "                     * flushes the genuine gpulib command buffer. */\n"
        "                    if(!GPU_readStatus){\n"
        '                        SysPrintf("VH162_GPU_STATUS_CALLBACK_REFUSED\\n");\n'
        "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 66;\n"
        "                    }\n"
        "                    (void)GPU_readStatus();\n"
        "                    unsigned queue=vh161_gpu_queue_stores();\n",
        "explicit GPUreadStatus flush after synthetic fifth instruction")
    source=once(source,
        "                    int queue_disarmed=vh161_disarm_gpu_queue();\n",
        "                    int queue_disarmed=vh161_disarm_gpu_queue();\n"
        "                    unsigned parsed=vh162_gpu_parse_visits();\n"
        "                    unsigned flushed=vh162_gpu_flushes();\n"
        "                    unsigned parser_bad=vh162_gpu_parse_faults();\n"
        "                    int parser_disarmed=vh162_disarm_gpu_parser();\n",
        "take independent parse+flush counts after native read status")
    # First update the positive guard: the negative has a different suffix.
    source=once(source,
        "queue!=1u || queue_bad!=0u || queue_disarmed!=0 ||",
        "queue!=1u || queue_bad!=0u || queue_disarmed!=0 ||\n"
        "                       parsed!=1u || flushed!=1u ||\n"
        "                       parser_bad!=0u || parser_disarmed!=0 ||",
        "require one exact parse visit and successful gpulib flush")
    source=once(source,
        "queue!=0u || queue_bad!=0u || queue_disarmed!=0){",
        "queue!=0u || queue_bad!=0u || queue_disarmed!=0 ||\n"
        "                           parsed!=0u || flushed!=0u ||\n"
        "                           parser_bad!=0u || parser_disarmed!=0){",
        "damaged fifth opcode must not reach parser or cause flush")
    source=once(source,
        '                        SysPrintf("VH161_NATIVE_FIFTH_QUEUE_REFUSED"',
        '                        SysPrintf("VH162_NATIVE_FIFTH_PARSE_REFUSED"'
        '" parsed=0 flushed=0 original_retail=0\\n");\n'
        '                        SysPrintf("VH161_NATIVE_FIFTH_QUEUE_REFUSED"',
        "emit strict corrupted-fifth parser absence marker")
    source=once(source,
        '                    SysPrintf("VH161_NATIVE_GPULIB_QUEUE_PASS"',
        '                    SysPrintf("VH162_NATIVE_GPULIB_PARSE_FLUSH_PASS"'
        '" parsed=1 flushed=1 original_retail=0\\n");\n'
        '                    SysPrintf("VH161_NATIVE_GPULIB_QUEUE_PASS"',
        "emit native parse and buffer drain success marker")
    return source


def apply(root: Path):
    proof=apply_v161(root)
    base=root.resolve()
    gpu=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"
    gpu.write_text(patch_gpu(gpu.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(proof,
        v162_native_gpulib_parser_visit_and_flush=True,
        v162_mutated_fifth_parser_not_reached=True,
        v162_unai_pixel_rasterization_verified=False,
        v162_original_gameplay_executed=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
