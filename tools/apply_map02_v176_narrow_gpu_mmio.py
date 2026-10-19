#!/usr/bin/env python3
"""v176: observe 8/16-bit guest GPU MMIO reads AND writes across genuine VBlank.

Diagnostic only: complementary to v175 32-bit read and v173 32-bit write.
Native MIPS LB/LH/SB/SH mutations must be refused before pixel PASS.
No retail MAP02 data or physical console assertions.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v175_dual_gpu_read_ports import (
    apply as apply_v175, protected_dual_port_oracle as v175_oracle
)
from .apply_map02_v69_pcsx_rearmed import once

COUNTER_ANCHOR="unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}\n"
READ8="u8 psxMemRead8(psxRegisters *regs, u32 mem) {\n"
READ16="u16 psxMemRead16(psxRegisters *regs, u32 mem) {\n"
WRITE8="void psxMemWrite8(psxRegisters *regs, u32 mem, u32 value) {\n"
WRITE16="void psxMemWrite16(psxRegisters *regs, u32 mem, u32 value) {\n"
FLAG="\tint vh175_mips_vblank_dual_ports_smoke = 0;\n"
CLI='\t\telse if (!strcmp(argv[i], "--vh175-mips-vblank-dual-ports"))\n'
ORACLE="\tif (loadst_f) {\n"

def narrow_observer():
    return r"""
/* v176: read-only witness of guest narrow GPU MMIO, no GPU writes by observer.
 * index: [width 0=8bit,1=16bit][direction 0=read,1=write][port 0=GP0,1=GP1]
 */
static unsigned vh176_active,vh176_phase,vh176_hits[2][2][2];
int vh176_arm_narrow(unsigned phase) {
    unsigned w,d,p;
    if (phase>=4u || vh176_active ||
        !vh175_port_armed || vh175_port_phase!=phase ||
        !vh174_read_armed || !vh173_wait_active ||
        vh173_wait_phase!=phase) return -1;
    for(w=0;w<2u;w++) for(d=0;d<2u;d++)
        for(p=0;p<2u;p++) vh176_hits[w][d][p]=0u;
    vh176_active=1u;vh176_phase=phase;
    return 0;
}
static void vh176_observe_narrow(u32 address,unsigned width,unsigned writing) {
    u32 physical=address&0x1fffffffu;
    unsigned port;
    if(!vh176_active || !vh175_port_armed || !vh173_wait_active) return;
    if(width>1u || writing>1u || physical<0x1f801810u ||
       physical>0x1f801817u) return;
    port=(physical-0x1f801810u)>>2;
    vh176_hits[width][writing][port]++;
}
unsigned vh176_narrow_count(unsigned width,unsigned writing,unsigned port) {
    if(width>1u || writing>1u || port>1u)return 0xffffffffu;
    return vh176_hits[width][writing][port];
}
unsigned vh176_narrow_total(void) {
    unsigned w,d,p,sum=0u;
    for(w=0;w<2u;w++) for(d=0;d<2u;d++)
        for(p=0;p<2u;p++)sum+=vh176_hits[w][d][p];
    return sum;
}
int vh176_disarm_narrow(unsigned phase) {
    if(!vh176_active || vh176_phase!=phase ||
       !vh175_port_armed || vh175_port_phase!=phase ||
       !vh174_read_armed || !vh173_wait_active ||
       vh173_wait_phase!=phase)return -1;
    vh176_active=0u;
    return 0;
}
"""

def patch_memory(source:str):
    if "vh176_observe_narrow" in source:
        raise ValueError("v176 narrow GPU MMIO observer already installed")
    s=once(source,COUNTER_ANCHOR,narrow_observer()+COUNTER_ANCHOR,
           "native width-specific GPU MMIO counters")
    declaration=(
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "static void vh176_observe_narrow(u32,unsigned,unsigned);\n"
        "#endif\n"
    )
    s=once(s,READ8,declaration+READ8+
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh176_observe_narrow(mem,0u,0u);\n"
        "#endif\n","8-bit reads before original guest memory behavior")
    s=once(s,READ16,READ16+
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh176_observe_narrow(mem,1u,0u);\n"
        "#endif\n","16-bit reads before original guest memory behavior")
    s=once(s,WRITE8,WRITE8+
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh176_observe_narrow(mem,0u,1u);\n"
        "#endif\n","8-bit writes before original guest memory behavior")
    return once(s,WRITE16,WRITE16+
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh176_observe_narrow(mem,1u,1u);\n"
        "#endif\n","16-bit writes before original guest memory behavior")

def narrow_oracle():
    s=v175_oracle()
    s=once(s,"if(vh175_mips_vblank_dual_ports_smoke) {",
           "if(vh176_mips_vblank_narrow_mmio_smoke) {",
           "v176 independent CLI mode must execute native oracle")
    entry="unsigned int entry_count=vh78_vblank_observed_count;"
    s=once(s,entry,
       "if(vh176_arm_narrow(phase)!=0){\n"
       '                SysPrintf("VH176_NARROW_ARM_REFUSED phase=%u\\n",phase);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 82;\n"
       "\t\t\t}\n\t\t\t"+entry,
       "arm after inherited v175 and before real native MIPS wait")
    disarm="int vh175_ports_disarmed=vh175_disarm_read_ports(phase);"
    s=once(s,disarm,
       "unsigned int vh176_r8g0=vh176_narrow_count(0u,0u,0u);\n"
       "\t\t\tunsigned int vh176_r8g1=vh176_narrow_count(0u,0u,1u);\n"
       "\t\t\tunsigned int vh176_r16g0=vh176_narrow_count(1u,0u,0u);\n"
       "\t\t\tunsigned int vh176_r16g1=vh176_narrow_count(1u,0u,1u);\n"
       "\t\t\tunsigned int vh176_w8g0=vh176_narrow_count(0u,1u,0u);\n"
       "\t\t\tunsigned int vh176_w8g1=vh176_narrow_count(0u,1u,1u);\n"
       "\t\t\tunsigned int vh176_w16g0=vh176_narrow_count(1u,1u,0u);\n"
       "\t\t\tunsigned int vh176_w16g1=vh176_narrow_count(1u,1u,1u);\n"
       "\t\t\tunsigned int vh176_total=vh176_narrow_total();\n"
       "\t\t\tint vh176_disarmed=vh176_disarm_narrow(phase);\n"
       "\t\t\t"+disarm,
       "collect and disarm narrow MMIO before inherited v175 teardown")
    guard="if(vh175_ports_disarmed!=0 || vh175_gp0_bad!=0u || vh175_gp1_bad!=0u){"
    s=once(s,guard,
       "if(vh176_disarmed!=0 || vh176_total!=0u){\n"
       '                SysPrintf("VH176_NARROW_MMIO_REFUSED phase=%u r8g0=%u r8g1=%u r16g0=%u r16g1=%u w8g0=%u w8g1=%u w16g0=%u w16g1=%u\\n",phase,vh176_r8g0,vh176_r8g1,vh176_r16g0,vh176_r16g1,vh176_w8g0,vh176_w8g1,vh176_w16g0,vh176_w16g1);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 82;\n"
       "\t\t\t}\n\t\t\tvh176_narrow_windows++;\n"
       "\t\t\t"+guard,
       "reject real MIPS narrow GPU access before VRAM pixel oracle")
    count="unsigned int vh175_port_windows=0u;"
    s=once(s,count,count+"\n\t\tunsigned int vh176_narrow_windows=0u;",
           "count exactly four independently clean native VBlank windows")
    marker='SysPrintf("VH175_GUEST_MIPS_VBLANK_PORTS_PASS'
    return once(s,marker,
       "if(vh176_narrow_windows!=4u){\n"
       '            SysPrintf("VH176_NARROW_WINDOWS_REFUSED windows=%u\\n",vh176_narrow_windows);\n'
       "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 82;\n"
       "\t\t}\n"
       '\t\tSysPrintf("VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS windows=4 narrow_reads=0 narrow_writes=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0\\n");\n'
       "\t\t"+marker,
       "positive marker only after all inherited Unai samples and VBlanks")

def patch_frontend(source:str):
    if "vh176_mips_vblank_narrow_mmio_smoke" in source:
        raise ValueError("v176 diagnostic mode already installed")
    s=once(source,FLAG,FLAG+
       "\tint vh176_mips_vblank_narrow_mmio_smoke = 0;\n"
       "\textern int vh176_arm_narrow(unsigned);\n"
       "\textern unsigned vh176_narrow_count(unsigned,unsigned,unsigned);\n"
       "\textern unsigned vh176_narrow_total(void);\n"
       "\textern int vh176_disarm_narrow(unsigned);\n",
       "v176 narrow native VBlank observer frontend declarations")
    s=once(s,CLI,
       '\t\telse if (!strcmp(argv[i], "--vh176-mips-vblank-narrow-mmio"))\n'
       '\t\t\tvh176_mips_vblank_narrow_mmio_smoke=1;\n'+CLI,
       "v176 separate CLI flag")
    return once(s,ORACLE,narrow_oracle()+"\n"+ORACLE,
                "genuine MIPS narrow GPU memory oracle")

def apply(root:Path):
    report=apply_v175(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v176_native_vblank_events=4,
        v176_gpu_narrow_reads=0,
        v176_gpu_narrow_writes=0,
        v176_native_negative_expected_exit=82,
        v176_original_retail_executed=False,
        v176_physical_switch_output_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
