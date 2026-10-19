#!/usr/bin/env python3
"""v180: prove real interpreted non-GPU guest load/store memory operations.

A clean VBlank + rendered pixels alone cannot show that a v179 mutated
NOP was actually executed. v180 additionally observes real psxMemRead8/16/32
and psxMemWrite8/16 callbacks, with both interpreter regs->code and PC,
requiring the exact signed synthetic opcode and actual non-GPU address in
all four VBlank windows. No emulated memory, GPU or clock is modified.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v176_narrow_gpu_mmio import apply as apply_v176, narrow_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v179_nongpu_mips_exes import MUTANTS, mips_word, originals
from .make_map02_v78_vblank_mips_exe import build
from .make_map02_v70_synthetic_psx_exe import START

COUNTER="unsigned vh173_wait_mmio_faults(void) {return vh173_wait_bad;}\n"
READ8="u8 psxMemRead8(psxRegisters *regs, u32 mem) {\n"
READ16="    vh176_observe_narrow(mem,1u,0u);\n"
READ32="    vh175_observe_read_port(mem);\n"
WRITE8="    vh176_observe_narrow(mem,0u,1u);\n"
WRITE16="    vh176_observe_narrow(mem,1u,1u);\n"
FRONT_FLAG="\tint vh176_mips_vblank_narrow_mmio_smoke = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh176-mips-vblank-narrow-mmio"))\n'
ORACLE_POSITION="\tif (loadst_f) {\n"

# Width: 0=8, 1=16, 2=32. Direction: 0=read,1=write.
# Each expected address is a physical 29-bit PSX bus address.
CASES=(
    ("LB_BELOW_GP0", 0,0,0x1f80180f, -1,-1,0),
    ("LHU_ABOVE_GP1",1,0,0x1f801818,-1,-1,0),
    ("LWL_BELOW_GP0",2,0,0x1f80180c,-1,-1,0),
    ("LWR_ABOVE_GP1",2,0,0x1f801818,-1,-1,0),
    ("SB_RAM0",0,1,0x00000000,-1,-1,0),
    ("SH_RAM2",1,1,0x00000002,-1,-1,0),
    ("SWL_RAM2",1,1,0x00000000,0,1,0x00000002),
    ("SWR_RAM1",0,1,0x00000001,1,1,0x00000002),
)

def witness_source():
    data,index=originals()
    image,stops,starts,wait_pc,ops=build()
    if data!=image or wait_pc!=START+index*4 or len(CASES)!=8 or tuple(x[0] for x in CASES)!=tuple(MUTANTS):
        raise ValueError("v180 source must match exact v179 signed MIPS program")
    opcodes=[mips_word(*MUTANTS[c[0]]) for c in CASES]
    def arr(values):
        return ", ".join((f"0x{x:08x}u" if x>=0 else "0xffffffffu") for x in values)
    return r"""
/* v180: passive genuine interpreted MIPS memory-access witness, only
 * when previous v176/VBlank sentinel has explicitly armed this case.
 * Neither memory contents nor simulated clocks are changed here. */
static const u32 vh180_expected_word[8]={OPCODES};
static const u32 vh180_addr1[8]={ADDRESSES1};
static const u32 vh180_addr2[8]={ADDRESSES2};
static const unsigned vh180_width1[8]={WIDTH1};
static const unsigned vh180_width2[8]={WIDTH2};
static const unsigned vh180_writing1[8]={WRITING1};
static const unsigned vh180_writing2[8]={WRITING2};
static unsigned vh180_armed,vh180_kind,vh180_phase;
static unsigned vh180_seen1,vh180_seen2,vh180_bad;
int vh180_arm_nongpu(unsigned kind,unsigned phase) {
    if(kind>=8u || phase>=4u || vh180_armed || !vh176_active ||
       vh176_phase!=phase || !vh175_port_armed || !vh173_wait_active)
        return -1;
    vh180_kind=kind;vh180_phase=phase;vh180_armed=1u;
    vh180_seen1=0u;vh180_seen2=0u;vh180_bad=0u;
    return 0;
}
static void vh180_observe_nongpu(psxRegisters *regs,u32 addr,
                                 unsigned width,unsigned writing) {
    unsigned kind,physical;
    if(!vh180_armed || !vh176_active || !vh173_wait_active ||
       regs->pc!=WAIT_NEXT_PC) return;
    kind=vh180_kind;
    /* The real MIPS interpreter has advanced PC by four before dispatch.
     * Require both the exact live opcode and its source-authored site.
     * This cannot pass just because unrelated host reads occurred. */
    if(regs->code!=vh180_expected_word[kind])return;
    physical=addr&0x1fffffffu;
    if(vh180_width1[kind]==width &&
       vh180_writing1[kind]==writing &&
       vh180_addr1[kind]==physical) {
        vh180_seen1++;
    } else if(vh180_width2[kind]==width &&
              vh180_writing2[kind]==writing &&
              vh180_addr2[kind]==physical) {
        vh180_seen2++;
    } else vh180_bad++;
}
unsigned vh180_primary(void) {return vh180_seen1;}
unsigned vh180_secondary(void) {return vh180_seen2;}
unsigned vh180_faults(void) {return vh180_bad;}
int vh180_disarm_nongpu(unsigned kind,unsigned phase) {
    if(!vh180_armed || vh180_kind!=kind || vh180_phase!=phase ||
       !vh176_active || vh176_phase!=phase ||
       !vh175_port_armed || !vh173_wait_active) return -1;
    vh180_armed=0u;
    return 0;
}
""".replace("OPCODES",arr(opcodes))\
    .replace("ADDRESSES1",arr([c[3] for c in CASES]))\
    .replace("ADDRESSES2",arr([c[6] if c[4]>=0 else -1 for c in CASES]))\
    .replace("WIDTH1",arr([c[1] for c in CASES]))\
    .replace("WIDTH2",arr([c[4] for c in CASES]))\
    .replace("WRITING1",arr([c[2] for c in CASES]))\
    .replace("WRITING2",arr([c[5] for c in CASES]))\
    .replace("WAIT_NEXT_PC",f"0x{wait_pc+4:08x}u")

def patch_memory(source: str) -> str:
    if "vh180_observe_nongpu" in source:
        raise ValueError("v180 memory callback already installed")
    s=once(source,COUNTER,witness_source()+COUNTER,
           "true interpreted opcode and memory-address observer")
    s=once(s,READ8,
           "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
           "static void vh180_observe_nongpu(psxRegisters*,u32,unsigned,unsigned);\n"
           "#endif\n"+READ8,
           "declare observational v180 memory hook before actual psxMemRead8")
    s=once(s,"    vh176_observe_narrow(mem,0u,0u);\n",
           "    vh180_observe_nongpu(regs,mem,0u,0u);\n"
           "    vh176_observe_narrow(mem,0u,0u);\n",
           "observe true read8 before original memory read")
    for old,added,label in (
        (READ16,"    vh180_observe_nongpu(regs,mem,1u,0u);\n","read16"),
        (READ32,"    vh180_observe_nongpu(regs,mem,2u,0u);\n","read32"),
        (WRITE8,"    vh180_observe_nongpu(regs,mem,0u,1u);\n","write8"),
        (WRITE16,"    vh180_observe_nongpu(regs,mem,1u,1u);\n","write16"),
    ):
        s=once(s,old,added+old,"v180 actual "+label+" memory accessor")
    return s

def verified_oracle() -> str:
    s=narrow_oracle()
    s=once(s,"if(vh176_mips_vblank_narrow_mmio_smoke) {",
        "if(vh180_nongpu_verified_id>=0) {",
        "v180 private opt-in mode must not silently fall back to v176")
    arm="unsigned int entry_count=vh78_vblank_observed_count;"
    s=once(s,arm,
       "if(vh180_arm_nongpu((unsigned)vh180_nongpu_verified_id,phase)!=0){\n"
       '                SysPrintf("VH180_NONGPU_ARM_REFUSED phase=%u\\n",phase);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 83;\n"
       "\t\t\t}\n\t\t\t"+arm,
       "arm opcode observation only after native v176 observer")
    stop="int vh176_disarmed=vh176_disarm_narrow(phase);"
    s=once(s,stop,
       "unsigned int vh180_count1=vh180_primary();\n"
       "\t\t\tunsigned int vh180_count2=vh180_secondary();\n"
       "\t\t\tunsigned int vh180_mismatches=vh180_faults();\n"
       "\t\t\tint vh180_disarmed=vh180_disarm_nongpu((unsigned)vh180_nongpu_verified_id,phase);\n"
       "\t\t\t"+stop,
       "capture interpreted opcode provenance before disarming VBlank observer")
    gate="if(vh176_disarmed!=0 || vh176_total!=0u){"
    s=once(s,gate,
       "if(vh180_disarmed!=0 || vh180_count1==0u || vh180_mismatches!=0u ||\n"
       "   (vh180_nongpu_verified_id>=6 && vh180_count2!=vh180_count1) ||\n"
       "   (vh180_nongpu_verified_id<6 && vh180_count2!=0u)){\n"
       '                SysPrintf("VH180_GUEST_OPCODE_UNOBSERVED_REFUSED kind=%d phase=%u primary=%u secondary=%u faults=%u\\n",vh180_nongpu_verified_id,phase,vh180_count1,vh180_count2,vh180_mismatches);\n'
       "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 83;\n"
       "\t\t\t}\n\t\t\tvh180_seen_windows++;\n"
       "\t\t\tvh180_total_primary+=vh180_count1;\n"
       "\t\t\tvh180_total_secondary+=vh180_count2;\n"
       "\t\t\t"+gate,
       "refuse positive if a mutant wasn't actually executed as real guest MIPS")
    c="unsigned int vh176_narrow_windows=0u;"
    s=once(s,c,c+
       "\n\t\tunsigned int vh180_seen_windows=0u;\n"
       "\t\tunsigned int vh180_total_primary=0u,vh180_total_secondary=0u;",
       "accumulate live interpreter accesses in exactly four windows")
    marker='SysPrintf("VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS'
    s=once(s,marker,
       "if(vh180_seen_windows!=4u || vh180_total_primary<4u){\n"
       '            SysPrintf("VH180_PROVENANCE_WINDOWS_REFUSED windows=%u primary=%u\\n",vh180_seen_windows,vh180_total_primary);\n'
       "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 83;\n"
       "\t\t}\n"
       '        SysPrintf("VH180_NONGPU_GUEST_OPCODE_EXECUTED_PASS kind=%d windows=4 primary=%u secondary=%u opcode_pc_bound=1 vblanks=4 samples=2380 original_retail=0\\n",vh180_nongpu_verified_id,vh180_total_primary,vh180_total_secondary);\n'
       "\t\t"+marker,
       "v180 positive only after four actual interpreted opcode access witnesses")
    return s

def patch_frontend(source: str) -> str:
    if "vh180_nongpu_verified_id" in source:
        raise ValueError("duplicate v180 frontend witness")
    s=once(source,FRONT_FLAG,FRONT_FLAG+
       "\tint vh180_nongpu_verified_id=-1;\n"
       "\textern int vh180_arm_nongpu(unsigned,unsigned);\n"
       "\textern unsigned vh180_primary(void);\n"
       "\textern unsigned vh180_secondary(void);\n"
       "\textern unsigned vh180_faults(void);\n"
       "\textern int vh180_disarm_nongpu(unsigned,unsigned);\n",
       "separate nongpu real-opcode gate and strictly read-only counters")
    cli="".join(
        '\t\telse if (!strcmp(argv[i], "--vh180-nongpu-mips-'+str(i)+'"))\n'
        "\t\t\tvh180_nongpu_verified_id="+str(i)+";\n"
        for i in range(8)
    )
    s=once(s,FRONT_CLI,cli+FRONT_CLI,"eight opt-in case identifiers")
    return once(s,ORACLE_POSITION,verified_oracle()+"\n"+ORACLE_POSITION,
                "eight original interpreter opcode checks in real VBlank waits")

def apply(root: Path):
    report=apply_v176(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v180_retail_map02_verified=False,
        v180_nongpu_mutated_opcodes_witnessed=8,
        v180_native_vblank_events_per_case=4,
        v180_native_unai_pixel_samples_per_case=2380)

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
