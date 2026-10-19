#!/usr/bin/env python3
"""v174: reject interpreted guest GPU GP0/GP1 reads during genuine VBlank waits.

An additional read-only sentinel in the real PCSX psxMemRead32 complements
v173's write sentinel. The native negative changes one self-authored
wait-pad MIPS NOP to LW, not emulator counters or video production.
No original retail MAP02 or hardware frame is claimed.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v173_vblank_quiet_mmio import (
    apply as apply_v173, validated_guest_wait, protected_vblank_oracle
)
from .apply_map02_v69_pcsx_rearmed import once

READ_ANCHOR="u32 psxMemRead32(psxRegisters *regs, u32 mem) {\n"
V173_COUNTER="unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}\n"
FRONT_FLAG="\tint vh173_mips_vblank_quiet_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh173-mips-vblank-quiet"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"

def read_sentinel():
    validated_guest_wait()
    return r"""
/* v174 is observational: the memory read still reaches PCSX unmodified.
 * Count guest MIPS GPU-port reads only during the v173 armed wait. */
static unsigned vh174_wait_read_bad;
int vh174_arm_wait_read(unsigned phase) {
    if (!vh173_wait_active || vh173_wait_phase!=phase || phase>=4u) return -1;
    vh174_wait_read_bad=0u;
    return 0;
}
static void vh174_observe_wait_read(u32 address) {
    u32 physical=address&0x1fffffffu;
    if (vh173_wait_active &&
        (physical==0x1f801810u || physical==0x1f801814u))
        vh174_wait_read_bad++;
}
unsigned vh174_wait_read_faults(void) {return vh174_wait_read_bad;}
"""

def patch_memory(source:str):
    if "vh174_observe_wait_read" in source:
        raise ValueError("v174 read sentinel already installed")
    if source.count(V173_COUNTER)!=1:
        raise ValueError("requires exactly one v173 write sentinel")
    s=once(source,V173_COUNTER,read_sentinel()+V173_COUNTER,
           "v174 passive MIPS GPU register read observation")
    s=once(s,READ_ANCHOR,
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "static void vh174_observe_wait_read(u32 address);\n"
        "#endif\n"+READ_ANCHOR+
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh174_observe_wait_read(mem);\n"
        "#endif\n",
        "read observer before original psxMemRead32 execution")
    return s

def read_provenance_oracle():
    s=protected_vblank_oracle()
    s=once(s,"if(vh173_mips_vblank_quiet_smoke) {",
           "if(vh174_mips_vblank_read_quiet_smoke) {",
           "v174 must use its own CLI option, never v173 fallthrough")
    arm="unsigned int entry_count=vh78_vblank_observed_count;"
    s=once(s,arm,
        "if(vh174_arm_wait_read(phase)!=0){\n"
        '                SysPrintf("VH174_READ_ARM_REFUSED phase=%u\\n",phase);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 80;\n"
        "\t\t\t}\n\t\t\t"+arm,
        "strict post-v173-arming GPU read sentinel")
    disarm="int vh173_quiet_disarmed=vh173_disarm_wait_quiet(phase);"
    s=once(s,disarm,
        "unsigned int vh174_read_faults=vh174_wait_read_faults();\n"
        "\t\t\t"+disarm,
        "sample read count before wait disarms")
    window="vh173_quiet_windows++;"
    s=once(s,window,
        'if(vh174_read_faults!=0u){\n'
        '                SysPrintf("VH174_VBLANK_WAIT_READ_REFUSED phase=%u forbidden=%u\\n",phase,vh174_read_faults);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 80;\n"
        "\t\t\t}\n\t\t\tvh174_read_windows++;\n\t\t\t"+window,
        "reject native guest GPU reads before per-phase readback")
    total="unsigned int vh173_quiet_windows=0u;"
    s=once(s,total,total+"\n\t\tunsigned int vh174_read_windows=0u;",
           "count four clean GPU-read wait windows")
    marker='SysPrintf("VH173_GUEST_MIPS_VBLANK_QUIET_PASS'
    s=once(s,marker,
        "if(vh174_read_windows!=4u){\n"
        '            SysPrintf("VH174_READ_WINDOWS_REFUSED windows=%u\\n",vh174_read_windows);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 80;\n"
        "\t\t}\n"
        '\t\tSysPrintf("VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS windows=4 forbidden_gp0_gp1_reads=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0\\n");\n'
        "\t\t"+marker,
        "read-silent VBlank native positive claim")
    return s

def patch_frontend(source:str):
    if "vh174_mips_vblank_read_quiet_smoke" in source:
        raise ValueError("v174 option already installed")
    s=once(source,FRONT_FLAG,FRONT_FLAG+
        "\tint vh174_mips_vblank_read_quiet_smoke = 0;\n"
        "\textern int vh174_arm_wait_read(unsigned);\n"
        "\textern unsigned vh174_wait_read_faults(void);\n",
        "v174 no-write-side-effect GPU register read declarations")
    s=once(s,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh174-mips-vblank-read-quiet"))\n'
        '\t\t\tvh174_mips_vblank_read_quiet_smoke=1;\n'+FRONT_CLI,
        "native guest MIPS read-silent VBlank switch")
    return once(s,ORACLE_POSITION,read_provenance_oracle()+"\n"+ORACLE_POSITION,
        "four native VBlank MMIO read-silent checks + inherited pixel oracles")

def apply(root:Path):
    report=apply_v173(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v174_observed_guest_gpu_reads_during_four_waits=0,
        v174_native_vblank_events=4,
        v174_gcc_clang_negative_lw_expected_exit=80,
        v174_original_retail_executed=False,
        v174_console_frame_verified=False)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(ap.parse_args().pinned_pcsx_checkout))
