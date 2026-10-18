#!/usr/bin/env python3
"""v172: match exact guest-MIPS GP0/GP1 SW provenance to real PCSX VBlank edges.

Builds on verified v171 in-process 4-phase GPU command/raster provenance,
and original v78 psxRcntUpdate observation of four genuine native
GPU_vBlank(1,0) calls. The self-authored v78 executable extends v77 with
bounded MIPS NOP waits; no host-forged VBlank or GPU draw traffic.
This is NOT a physical console or retail MAP02 gameplay frame.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v171_mips_multiphase_vram import apply as apply_v171
from .apply_map02_v171_mips_multiphase_vram import expected_phase_source
from .apply_map02_v78_pcsx_rearmed import oracle_source as v78_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v78_vblank_mips_exe import build as v78_build,MAGIC

FRONT_FLAG="\tint vh171_mips_multiphase_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh171-mips-multiphase-vram"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"


def check_v78_extends_exact_v171_mips():
    source_pcs,source_gp1,lens,original_stops=expected_phase_source()
    image,stops,starts,wait_pc,program=v78_build()
    if (image[:8]!=b"PS-X EXE" or image[0x4c:0x54]!=MAGIC or
        MAGIC!=b"VH78SYN!" or len(image)!=2048+8192 or
        tuple(stops)!=tuple(original_stops) or len(source_pcs)!=4 or
        lens!=(49,7,7,9) or
        sum(lens)!=72 or sum(x!=0 for x in source_gp1)!=3 or
        len(program)<512):
        raise ValueError("v78 wait fixture no longer extends exact v171 GPU source")
    if any(program[-514+i]!=0 for i in range(512)):
        raise ValueError("real-VBlank wait region changed from 512 MIPS NOPs")
    if tuple(starts)!=tuple(v78_build()[2]):
        raise ValueError("source stage start PC changed")
    return stops,wait_pc


def native_vblank_provenance_oracle():
    stops,wait_pc=check_v78_extends_exact_v171_mips()
    src=v78_oracle(stops,wait_pc)
    src=once(src,
        "if(vh78_vblank_smoke) {",
        "if(vh172_mips_vblank_vram_smoke) {",
        "v172 separate four genuine native VBlank event gate")
    loop="\t\tfor(unsigned int phase=0;phase<4;phase++) {\n\t\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if src.count(loop)!=1:
        raise ValueError("v78 genuine guest MIPS execution block moved")
    src=src.replace(loop,
        "\t\tunsigned int vh172_total_gp0=0u,vh172_total_gp1=0u;\n"
        "\t\tfor(unsigned int phase=0;phase<4;phase++) {\n"
        "\t\t\tif(vh171_arm_guest_phase(phase)!=0){\n"
        '                SysPrintf("VH172_GPU_ORIGIN_ARM_REFUSED phase=%u\\n",phase);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 78;\n"
        "\t\t\t}\n"
        "\t\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n"
        "\t\t\tunsigned int vh172_gp0=vh171_guest_phase_gp0_words();\n"
        "\t\t\tunsigned int vh172_gp1=vh171_guest_phase_gp1_writes();\n"
        "\t\t\tunsigned int vh172_faults=vh171_guest_phase_faults();\n"
        "\t\t\tint vh172_disarmed=vh171_disarm_guest_phase();\n"
        "\t\t\tconst unsigned int vh172_expect_gp0[4]={49u,7u,7u,9u};\n"
        "\t\t\tconst unsigned int vh172_expect_gp1[4]={1u,0u,1u,1u};\n"
        "\t\t\tif(vh172_disarmed!=0 ||\n"
        "\t\t\t   vh172_gp0!=vh172_expect_gp0[phase] ||\n"
        "\t\t\t   vh172_gp1!=vh172_expect_gp1[phase] || vh172_faults){\n"
        '                SysPrintf("VH172_MIPS_GP1_VBLANK_ORIGIN_REFUSED phase=%u gp0=%u gp1=%u faults=%u\\n",phase,vh172_gp0,vh172_gp1,vh172_faults);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 78;\n"
        "\t\t\t}\n"
        "\t\t\tvh172_total_gp0+=vh172_gp0;\n"
        "\t\t\tvh172_total_gp1+=vh172_gp1;")
    marker='\t\tSysPrintf("VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1\\n");'
    if src.count(marker)!=1:
        raise ValueError("original VBlank observer or native pixel success moved")
    src=src.replace(marker,
        "\t\tif(vh172_total_gp0!=72u || vh172_total_gp1!=3u ||\n"
        "\t\t   vh78_vblank_observed_count!=initial_vblank_count+4u){\n"
        '            SysPrintf("VH172_MULTIPHASE_VBLANK_TOTALS_REFUSED gp0=%u gp1=%u\\n",vh172_total_gp0,vh172_total_gp1);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 78;\n"
        "\t\t}\n"
        '        SysPrintf("VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS'
        ' vblanks=4 phases=4 gp0_words=72 gp1_writes=3'
        ' samples=2380 source=psxRcntUpdate console_frame_asserted=0'
        ' original_retail=0\\n");\n'+marker)
    return src


def patch_frontend(source: str):
    if "vh172_mips_vblank_vram_smoke" in source:
        raise ValueError("duplicate v172 native MIPS/VBlank proof mode")
    source=once(source,FRONT_FLAG,
        FRONT_FLAG+"\tint vh172_mips_vblank_vram_smoke = 0;\n",
        "new source attested real-counter VBlank diagnostic flag")
    source=once(source,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh172-mips-real-vblank-vram"))\n'
        '\t\t\tvh172_mips_vblank_vram_smoke=1;\n'+FRONT_CLI,
        "separate self-authored signed v78 native MIPS VBlank CLI")
    return once(source,ORACLE_POSITION,native_vblank_provenance_oracle()+"\n"+ORACLE_POSITION,
        "independent four real native GPU_vBlank events + source MMIO + pixels")


def apply(root:Path):
    report=apply_v171(root)
    front=root.resolve()/"frontend/main.c"
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v172_native_psxcounters_vblank_events=4,
        v172_exact_interpreted_mips_gp0_words=72,
        v172_exact_interpreted_mips_gp1_writes=3,
        v172_native_unai_pixel_samples=2380,
        v172_hardware_console_display_parity_verified=False,
        v172_retail_map02_frame_verified=False,
        v172_nintendo_switch_renderer_verified=False)


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(ap.parse_args().pinned_pcsx_checkout))
