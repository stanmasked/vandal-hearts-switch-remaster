#!/usr/bin/env python3
"""v165: bind each native Unai 4x4 VRAM delta to an exact guest-MIPS GP0 triplet.

The source-authored v121 EXE sends color, XY and width/height via interpreted
MIPS SW to the PS1 GPU port. Observe actual gpulib GPUwriteData *after* its
original append, before GPU_freeze draws. Refuse wrong, missing or extra words.
No host GP0 submission, no retail MAP02 execution, no Nintendo Switch claim.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v164_guest_mips_halo import apply as apply_v164
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v121_mips_gp0_return_exe import (
    build, COLORS, RECT_XY, RECT_SIZE,
)

GPU_ENTRY = "void GPUwriteData(uint32_t data)\n{"
GPU_APPEND = "  vh161_observe_gpu_queue(data);\n"
PHASE = ("        vh115_enable(1);\n"
         "        unsigned int readbacks=0;\n"
         "        for(unsigned int phase=0;phase<5u;phase++){\n")
BEFORE_FREEZE = (
    "            if(psxRegs.pc!=vh121_stops[phase+1u] ||\n"
    "               marker!=vh121_marks[phase+1u]){\n"
    '                SysPrintf("VH121_MIPS_PHASE_REFUSED phase=%u\\n",phase);\n'
    "                ClosePlugins();SysClose();menu_finish();plat_finish();return 37;\n"
    "            }\n"
    "            GPUFreeze_t freeze_state={0};\n"
)
END = '        SysPrintf("VH121_MIPS_GP0_RETURN_PASS stages=6'


def native_gp0_probe_c() -> str:
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Diagnostic-only native gpulib witness: never alters the original GP0
 * buffer, renderer or CPU. Observe raw 32-bit words immediately AFTER
 * the real GPUwriteData store, while v121 ExecuteBlock is running. */
static unsigned vh165_active, vh165_words, vh165_faults;
static uint32_t vh165_expected[3];
int vh165_arm_guest_gp0(uint32_t color, uint32_t xy, uint32_t size) {
    if(vh165_active || (color & 0xfc000000u)!=0x60000000u ||
       xy!=0x00a00028u || size!=0x00040004u) return -1;
    vh165_expected[0]=color;
    vh165_expected[1]=xy;
    vh165_expected[2]=size;
    vh165_words=vh165_faults=0u;
    vh165_active=1u;
    return 0;
}
static void vh165_observe_guest_gp0(uint32_t word) {
    if(!vh165_active) return;
    if(vh165_words>=3u || gpu.cmd_len<=0 ||
       gpu.cmd_len>CMD_BUFFER_LEN ||
       gpu.cmd_buffer[gpu.cmd_len-1]!=HTOLE32(word) ||
       word!=vh165_expected[vh165_words]) {
        vh165_faults++;
        return;
    }
    vh165_words++;
}
unsigned vh165_guest_gp0_words(void) {return vh165_words;}
unsigned vh165_guest_gp0_faults(void) {return vh165_faults;}
int vh165_disarm_guest_gp0(void) {
    if(!vh165_active) return -1;
    vh165_active=0u;
    return 0;
}
#endif

"""


def patch_gpu(source: str) -> str:
    if "vh165_observe_guest_gp0" in source:
        raise ValueError("v165 gpulib observer already installed")
    source=once(source,GPU_ENTRY,native_gp0_probe_c()+GPU_ENTRY,
                "native gpulib exact guest-MIPS triplet observer")
    return once(source,GPU_APPEND,
        GPU_APPEND+"  vh165_observe_guest_gp0(data);\n",
        "require original GPUwriteData buffer store before source-bound observer")


def patch_frontend(source: str) -> str:
    if "vh165_mips_gp0_vram_bound" in source:
        raise ValueError("v165 guest+VRAM mode already installed")
    data, stops, operations, starts = build()
    if data[:8]!=b"PS-X EXE" or data[0x4c:0x54]!=b"VH121SY!" or \
       len(stops)!=6 or len(starts)!=6 or len(COLORS)!=5 or \
       RECT_XY!=0x00a00028 or RECT_SIZE!=0x00040004:
        raise ValueError("pinned self-authored guest MIPS executable mismatch")
    colors="{"+",".join(f"0x{x:08x}u" for x in COLORS)+"}"
    source=once(source,"\textern int vh161_disarm_gpu_queue(void);\n",
        "\textern int vh161_disarm_gpu_queue(void);\n"
        "\textern int vh165_arm_guest_gp0(uint32_t,uint32_t,uint32_t);\n"
        "\textern unsigned vh165_guest_gp0_words(void);\n"
        "\textern unsigned vh165_guest_gp0_faults(void);\n"
        "\textern int vh165_disarm_guest_gp0(void);\n",
        "declare read-only native gpulib packet observer API")
    source=once(source,"\tint vh164_mips_raster_bounds = 0;\n",
        "\tint vh164_mips_raster_bounds = 0;\n"
        "\tint vh165_mips_gp0_vram_bound = 0;\n",
        "opt-in mode cannot replace the earlier v164 source-bound mode")
    anchor='\t\telse if (!strcmp(argv[i], "--vh164-mips-vram-halo")) {\n'
    source=once(source,anchor,
        '\t\telse if (!strcmp(argv[i], "--vh165-mips-gp0-vram-bound")) {\n'
        '\t\t\tvh121_mips_return_smoke=1;\n'
        '\t\t\tvh164_mips_raster_bounds=1;\n'
        '\t\t\tvh165_mips_gp0_vram_bound=1;\n'
        '\t\t}\n'+anchor,
        "distinct guest-MIPS source+queue+pixel mode")
    source=once(source,PHASE,
        f"        static const uint32_t vh165_expected_colors[5]={colors};\n"
        "        unsigned vh165_total_words=0u;\n"
        +PHASE+
        "            if(vh165_mips_gp0_vram_bound &&\n"
        "               vh165_arm_guest_gp0(vh165_expected_colors[phase],\n"
        "                                     0x00a00028u,0x00040004u)!=0){\n"
        '                SysPrintf("VH165_GP0_ARM_REFUSED phase=%u\\n",phase);\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 69;\n"
        "            }\n",
        "arm exactly three expected GP0 words before each interpreter stage")
    source=once(source,BEFORE_FREEZE,
        BEFORE_FREEZE.replace("            GPUFreeze_t freeze_state={0};\n", "")+
        "            if(vh165_mips_gp0_vram_bound){\n"
        "                unsigned words=vh165_guest_gp0_words();\n"
        "                unsigned faults=vh165_guest_gp0_faults();\n"
        "                int disarmed=vh165_disarm_guest_gp0();\n"
        "                if(words!=3u || faults!=0u || disarmed!=0){\n"
        '                    SysPrintf("VH165_GP0_TRIPLET_REFUSED phase=%u words=%u faults=%u\\n",\n'
        "                              phase,words,faults);\n"
        "                    ClosePlugins();SysClose();menu_finish();plat_finish();return 69;\n"
        "                }\n"
        "                vh165_total_words+=words;\n"
        "            }\n"
        "            GPUFreeze_t freeze_state={0};\n",
        "strictly bind 3 exact native gpulib words before VRAM readback")
    source=once(source,END,
        "        if(vh165_mips_gp0_vram_bound){\n"
        "            if(vh165_total_words!=15u || readbacks!=5u ||\n"
        "               vh164_changes!=80u || vh164_neighbors!=100u){\n"
        '                SysPrintf("VH165_GUEST_PACKET_PIXEL_COUNT_REFUSED\\n");\n'
        "                ClosePlugins();SysClose();menu_finish();plat_finish();return 69;\n"
        "            }\n"
        '            SysPrintf("VH165_GUEST_MIPS_GP0_VRAM_BOUND_PASS"'
        '" phases=5 gp0_words=15 pixels_changed=80 border_unchanged=100"'
        '" host_draws=0 original_retail=0\\n");\n'
        "        }\n"+END,
        "only credit native source-authored GP0 triples after v164 exact halo")
    return source


def apply(root: Path):
    proof=apply_v164(root)
    base=root.resolve()
    gpu=base/"plugins/gpulib/gpu.c"
    frontend=base/"frontend/main.c"
    gpu.write_text(patch_gpu(gpu.read_text()))
    frontend.write_text(patch_frontend(frontend.read_text()))
    return dict(proof,
        v165_native_gpulib_guest_MIPS_gp0_triplets_verified=5,
        v165_expected_exact_gp0_words=15,
        v165_native_pixel_delta_per_stage=16,
        v165_host_gpu_packet_submission=False,
        v165_original_retail_MAP02_frame_verified=False,
        v165_switch_graphics_verified=False)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
