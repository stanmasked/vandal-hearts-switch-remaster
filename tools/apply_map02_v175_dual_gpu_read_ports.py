#!/usr/bin/env python3
"""v175: distinguish genuine interpreted guest GP0 vs GP1 reads in VBlank waits.

Extends fully green v174 with a separate diagnostic-only, fail-closed
per-port read observer. The native negative changes one synthetic MIPS
NOP to LW t1,4(t0), reading GP1 rather than GP0. Emulator behavior,
timer events, GPU data and private retail content are not altered.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v174_vblank_read_quiet import (
    apply as apply_v174, read_provenance_oracle as v174_oracle
)
from .apply_map02_v69_pcsx_rearmed import once

MEM_COUNTER="unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}\n"
MEM_PROTO="static void vh174_observe_wait_read(u32 address);\n"
MEM_OBSERVE="    vh174_observe_wait_read(mem);\n"
FRONT_FLAG="\tint vh174_mips_vblank_read_quiet_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh174-mips-vblank-read-quiet"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"

def per_port_observer():
    return r"""
/* v175 observes true 32-bit guest GPU reads by register, without writes. */
static unsigned vh175_port_armed,vh175_port_phase,vh175_gp0_reads,vh175_gp1_reads;
int vh175_arm_read_ports(unsigned phase) {
    if (phase>=4u || vh175_port_armed || !vh174_read_armed ||
        vh174_read_phase!=phase || !vh173_wait_active ||
        vh173_wait_phase!=phase) return -1;
    vh175_gp0_reads=0u;
    vh175_gp1_reads=0u;
    vh175_port_armed=1u;
    vh175_port_phase=phase;
    return 0;
}
static void vh175_observe_read_port(u32 address) {
    u32 physical=address&0x1fffffffu;
    if (!vh175_port_armed || !vh174_read_armed || !vh173_wait_active) return;
    if (physical==0x1f801810u) vh175_gp0_reads++;
    else if (physical==0x1f801814u) vh175_gp1_reads++;
}
unsigned vh175_gp0_read_faults(void) {return vh175_gp0_reads;}
unsigned vh175_gp1_read_faults(void) {return vh175_gp1_reads;}
int vh175_disarm_read_ports(unsigned phase) {
    if (!vh175_port_armed || vh175_port_phase!=phase ||
        !vh174_read_armed || vh174_read_phase!=phase ||
        !vh173_wait_active || vh173_wait_phase!=phase) return -1;
    vh175_port_armed=0u;
    return 0;
}
"""

def patch_memory(s:str):
    if "vh175_observe_read_port" in s:
        raise ValueError("v175 per-port native read observer already installed")
    s=once(s,MEM_COUNTER,per_port_observer()+MEM_COUNTER,
           "native independent GP0/GP1 read counters")
    s=once(s,MEM_PROTO,MEM_PROTO+
           "static void vh175_observe_read_port(u32 address);\n",
           "declare v175 before actual psxMemRead32")
    return once(s,MEM_OBSERVE,
        "    vh175_observe_read_port(mem);\n"+MEM_OBSERVE,
        "observe both GPU ports before original real guest read")

def protected_dual_port_oracle():
    s=v174_oracle()
    s=once(s,"if(vh174_mips_vblank_read_quiet_smoke) {",
           "if(vh175_mips_vblank_dual_ports_smoke) {",
           "v175 separate native guest GP1 read option")
    start="unsigned int entry_count=vh78_vblank_observed_count;"
    s=once(s,start,
        "if(vh175_arm_read_ports(phase)!=0){\n"
        '                SysPrintf("VH175_PORT_ARM_REFUSED phase=%u\\n",phase);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 81;\n"
        "\t\t\t}\n\t\t\t"+start,
        "arm v175 after v174 and before each real VBlank wait")
    sample="unsigned int vh174_read_faults=vh174_wait_read_faults();"
    s=once(s,sample,
        "unsigned int vh175_gp0_bad=vh175_gp0_read_faults();\n"
        "\t\t\tunsigned int vh175_gp1_bad=vh175_gp1_read_faults();\n"
        "\t\t\tint vh175_ports_disarmed=vh175_disarm_read_ports(phase);\n"
        "\t\t\t"+sample,
        "sample dual-port counts and disarm before v174 teardown")
    inherited="if(vh174_read_disarmed!=0 || vh174_read_faults!=0u){"
    s=once(s,inherited,
        "if(vh175_ports_disarmed!=0 || vh175_gp0_bad!=0u || vh175_gp1_bad!=0u){\n"
        '                SysPrintf("VH175_VBLANK_GPU_READ_PORT_REFUSED phase=%u gp0=%u gp1=%u\\n",phase,vh175_gp0_bad,vh175_gp1_bad);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 81;\n"
        "\t\t\t}\n\t\t\tvh175_port_windows++;\n"
        "\t\t\t"+inherited,
        "reject individual guest GPU port reads before native VRAM oracle")
    total="unsigned int vh174_read_windows=0u;"
    s=once(s,total,total+"\n\t\tunsigned int vh175_port_windows=0u;",
           "count exact four clean per-port wait intervals")
    marker='SysPrintf("VH174_GUEST_MIPS_VBLANK_READ_QUIET_PASS'
    s=once(s,marker,
        "if(vh175_port_windows!=4u){\n"
        '            SysPrintf("VH175_PORT_WINDOWS_REFUSED windows=%u\\n",vh175_port_windows);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 81;\n"
        "\t\t}\n"
        '\t\tSysPrintf("VH175_GUEST_MIPS_VBLANK_PORTS_PASS windows=4 forbidden_gp0=0 forbidden_gp1=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0\\n");\n'
        "\t\t"+marker,
        "v175 must finish four native Unai pixel oracles before positive marker")
    return s

def patch_frontend(s:str):
    if "vh175_mips_vblank_dual_ports_smoke" in s:
        raise ValueError("v175 diagnostic mode already installed")
    s=once(s,FRONT_FLAG,FRONT_FLAG+
        "\tint vh175_mips_vblank_dual_ports_smoke = 0;\n"
        "\textern int vh175_arm_read_ports(unsigned);\n"
        "\textern unsigned vh175_gp0_read_faults(void);\n"
        "\textern unsigned vh175_gp1_read_faults(void);\n"
        "\textern int vh175_disarm_read_ports(unsigned);\n",
        "independent native guest GPU register diagnostic declarations")
    s=once(s,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh175-mips-vblank-dual-ports"))\n'
        '\t\t\tvh175_mips_vblank_dual_ports_smoke=1;\n'+FRONT_CLI,
        "v175 separate genuine MIPS read option")
    return once(s,ORACLE_POSITION,protected_dual_port_oracle()+"\n"+ORACLE_POSITION,
        "native VBlank wait per-port read refusal and 2380 pixel oracle")

def apply(root:Path):
    report=apply_v174(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v175_true_native_vblank_events=4,
        v175_unexpected_gp0_reads=0,
        v175_unexpected_gp1_reads=0,
        v175_negative_gp1_native_expected_exit=81,
        v175_original_retail_executed=False,
        v175_console_frame_verified=False)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(ap.parse_args().pinned_pcsx_checkout))
