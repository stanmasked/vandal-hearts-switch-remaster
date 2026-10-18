#!/usr/bin/env python3
"""v173: forbid guest GPU MMIO writes during interpreted MIPS VBlank waits.

The previous v172 already proved four genuine psxRcntUpdate VBlank
events, source-attested GP0/GP1 commands, and 2380 native Unai pixels.
This optional v173 mode adds a read-only true psxMemWrite32 sentinel
during each MIPS NOP/jump wait interval, disarming before GPUFreeze.
A single self-authored MIPS SW replacing a wait NOP must be refused.
No retail MAP02 executable/graphics or hardware frame proof.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v172_mips_real_vblank_vram import (
    apply as apply_v172,native_vblank_provenance_oracle
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v78_vblank_mips_exe import build as v78_build,MAGIC
from .make_map02_v70_synthetic_psx_exe import START,sw

MEM_DECL="void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE="    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG="\tint vh172_mips_vblank_vram_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh172-mips-real-vblank-vram"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"

def validated_guest_wait():
    image,stops,starts,wait_pc,program=v78_build()
    idx=(wait_pc-START)//4
    if (image[:8]!=b"PS-X EXE" or image[0x4c:0x54]!=MAGIC or
        MAGIC!=b"VH78SYN!" or len(stops)!=4 or len(starts)!=4 or
        len(image)!=10240 or
        tuple(program[idx:idx+512])!=(0,)*512 or
        program[idx+512]>>26!=2 or
        program[idx+513]!=0 or
        sw(9,0,8)!=0xad090000):
        raise ValueError("self-authored 512 MIPS NOP VBlank wait changed")
    return idx,wait_pc

def native_mmio_quiet_observer():
    validated_guest_wait()
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Read-only observer: never writes emulated CPU/GPU/VRAM/counters.
 * Real MIPS GPU MMIO during the VBlank wait is forbidden. */
static unsigned vh173_wait_active,vh173_wait_phase,vh173_wait_bad;
int vh173_arm_wait_quiet(unsigned phase) {
    if(vh173_wait_active || phase>=4u)return -1;
    vh173_wait_active=1u;vh173_wait_phase=phase;vh173_wait_bad=0u;
    return 0;
}
static void vh173_observe_wait_mmio(u32 address) {
    u32 physical=address&0x1fffffffu;
    if(!vh173_wait_active)return;
    /* Guest CPU RAM and reads are not GP0/GP1 writes. */
    if(physical==0x1f801810u || physical==0x1f801814u)
        vh173_wait_bad++;
}
unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}
int vh173_disarm_wait_quiet(unsigned phase) {
    if(!vh173_wait_active || vh173_wait_phase!=phase)return -1;
    vh173_wait_active=0u;
    return 0;
}
#endif

"""

def patch_memory(source:str):
    if "vh173_observe_wait_mmio" in source:
        raise ValueError("v173 VBlank-MMIO quiet sentinel already installed")
    s=once(source,MEM_DECL,native_mmio_quiet_observer()+MEM_DECL,
           "guest GP0/GP1 MMIO read-only wait sentinel")
    return once(s,MEM_OBSERVE,
           "    if(vh173_wait_active) vh173_observe_wait_mmio(mem);\n"+MEM_OBSERVE,
           "strict MMIO wait observation before pinned v138 path")

def protected_vblank_oracle():
    validated_guest_wait()
    s=native_vblank_provenance_oracle()
    s=once(s,"if(vh172_mips_vblank_vram_smoke) {",
           "if(vh173_mips_vblank_quiet_smoke) {",
           "v173 separate signed guest wait sentinel mode")
    arm="unsigned int entry_count=vh78_vblank_observed_count;"
    if s.count(arm)!=1:raise ValueError("native VBlank wait start changed")
    s=s.replace(arm,
        "if(vh173_arm_wait_quiet(phase)!=0){\n"
        '                SysPrintf("VH173_VBLANK_WAIT_ARM_REFUSED phase=%u\\n",phase);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 79;\n"
        "\t\t\t}\n"
        "\t\t\t"+arm)
    disarm="previous_vblank_frame=vh78_vblank_last_frame;"
    if s.count(disarm)!=1:raise ValueError("native VBlank wait end changed")
    s=s.replace(disarm,
        disarm+"\n"
        "\t\t\tunsigned int vh173_quiet_faults=vh173_wait_mmio_faults();\n"
        "\t\t\tint vh173_quiet_disarmed=vh173_disarm_wait_quiet(phase);\n"
        "\t\t\tif(vh173_quiet_disarmed!=0 || vh173_quiet_faults!=0u){\n"
        '                SysPrintf("VH173_VBLANK_WAIT_MMIO_REFUSED phase=%u forbidden=%u\\n",phase,vh173_quiet_faults);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 79;\n"
        "\t\t\t}\n"
        "\t\t\tvh173_quiet_windows++;")
    start="\t\tunsigned int vh172_total_gp0=0u,vh172_total_gp1=0u;"
    if s.count(start)!=1:raise ValueError("v172 four phase provenance aggregate moved")
    s=s.replace(start,start+"\n\t\tunsigned int vh173_quiet_windows=0u;")
    marker='SysPrintf("VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS'
    if s.count(marker)!=1:raise ValueError("inherited v172 positive marker moved")
    s=s.replace(marker,
        'if(vh173_quiet_windows!=4u){\n'
        '            SysPrintf("VH173_VBLANK_WAIT_WINDOWS_REFUSED windows=%u\\n",vh173_quiet_windows);\n'
        '\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 79;\n'
        '\t\t}\n'
        '\t\tSysPrintf("VH173_GUEST_MIPS_VBLANK_QUIET_PASS windows=4 forbidden_gp0_gp1=0 vblanks=4 gp0_words=72 gp1_writes=3 samples=2380 native_psxcounters=1 original_retail=0\\n");\n'
        '\t\t'+marker)
    return s

def patch_frontend(s:str):
    if "vh173_mips_vblank_quiet_smoke" in s:
        raise ValueError("duplicate guest MIPS VBlank quiet option")
    s=once(s,FRONT_FLAG,FRONT_FLAG+
        "\tint vh173_mips_vblank_quiet_smoke = 0;\n"
        "\textern int vh173_arm_wait_quiet(unsigned);\n"
        "\textern unsigned vh173_wait_mmio_faults(void);\n"
        "\textern int vh173_disarm_wait_quiet(unsigned);\n",
        "native GP0/GP1 wait quiet observer declarations")
    s=once(s,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh173-mips-vblank-quiet"))\n'
        '\t\t\tvh173_mips_vblank_quiet_smoke=1;\n'+FRONT_CLI,
        "separate actual MIPS NOP VBlank-window quiet option")
    return once(s,ORACLE_POSITION,protected_vblank_oracle()+"\n"+ORACLE_POSITION,
        "four source-attested VBlank waits with strict GPU MMIO silence")

def apply(root:Path):
    report=apply_v172(root)
    path=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    path.write_text(patch_memory(path.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v173_real_native_vblank_wait_windows=4,
        v173_observed_unexpected_gp0_gp1_during_wait=0,
        v173_true_psxcounters_vblank_events=4,
        v173_native_unai_pixel_samples=2380,
        v173_no_physical_console_frame_parity=True,
        v173_no_original_retail_map02=True)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
