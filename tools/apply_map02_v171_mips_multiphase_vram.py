#!/usr/bin/env python3
"""v171: four genuine interpreter MIPS blocks → GP0/GP1 → native VRAM.

Source-authored v77 MIPS phases in ONE pinned emulator process; each has
its own diagnostic-only native MMIO SW PC/word witness. The independent
old v77 GPUFreeze oracle checks 595 pixels and E1/E2/E6 register state
after EACH CPU block, 2380 pixels total. A block boundary is NOT VBlank.
No original retail Vandal Hearts code/data is used.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v170_mips_ft4_gpu_state import apply as apply_v170
from .apply_map02_v69_pcsx_rearmed import once
from .apply_map02_v77_pcsx_rearmed import oracle_source as v77_oracle
from .make_map02_v77_gpu_multiphase_exe import (
    build,phase_body,PHASE_GP0,PHASE_GP1,PHASE_NAMES,MAGIC,HEADER_SIZE,
    EXPECTED_REGS,MARKERS
)
from .make_map02_v70_synthetic_psx_exe import START,sw,lui,ori

MEM_DECL = "void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_OBSERVE = "    vh138_pc_observe(regs,mem,value);\n"
FRONT_FLAG = "\tint vh170_gpu_state_smoke = 0;\n"
FRONT_CLI = '\t\telse if (!strcmp(argv[i], "--vh170-mips-ft4-gpu-state"))\n'
ORACLE_POSITION = "\tif (loadst_f) {\n"


def expected_phase_source():
    image,stops,program,starts=build()
    if (image[:8]!=b"PS-X EXE" or len(image)!=HEADER_SIZE+4096 or
        image[0x4c:0x54]!=MAGIC or MAGIC!=b"VH77SYN!" or
        len(starts)!=4 or len(stops)!=4 or
        PHASE_NAMES!=("setup","persist","fifo_reset","full_reset") or
        len(MARKERS)!=4 or len(EXPECTED_REGS)!=4 or
        PHASE_GP1!=(0x01000000,None,0x01000000,0x00000000)):
        raise ValueError("source-authored v77 multi-phase synthetic image changed")
    PCs=[]
    GP1_PCs=[]
    for phase in range(4):
        stage=phase_body(phase)
        phase_start=starts[phase]
        b=(phase_start-START)//4
        if tuple(program[b:b+len(stage)])!=tuple(stage):
            raise ValueError("MIPS synthetic stage offset or opcode changed")
        if phase_start+(len(stage)+2)*4 != (starts[phase+1] if phase<3 else stops[phase]+8):
            raise ValueError("unexpected per-phase jump position")
        if stage[-1]!=sw(9,0,10):
            raise ValueError("stage guest RAM marker missing")
        has_gp1=PHASE_GP1[phase] is not None
        if has_gp1:
            g=PHASE_GP1[phase]
            if (stage[3]!=lui(9,g>>16) or
                stage[4]!=ori(9,9,g&0xffff) or
                stage[5]!=sw(9,0,8)):
                raise ValueError("source-authored GP1 SW PC/value changed")
        gp1_pc=phase_start+5*4 if has_gp1 else 0
        start_idx=7 if has_gp1 else 2
        p=[]
        for i,word in enumerate(PHASE_GP0[phase]):
            idx=start_idx+3*i
            if (stage[idx]!=lui(9,word>>16) or
                stage[idx+1]!=ori(9,9,word&0xffff) or
                stage[idx+2]!=sw(9,0,8)):
                raise ValueError("guest MIPS GP0 packet code source changed")
            p.append(phase_start+4*(idx+2))
        PCs.append(tuple(p))
        GP1_PCs.append(gp1_pc)
    lens=tuple(len(row) for row in PHASE_GP0)
    if lens!=(49,7,7,9) or sum(lens)!=72 or len(set(
            pc for phase in PCs for pc in phase))!=72:
        raise ValueError("unexpected guest MIPS four-phase packet layout")
    return tuple(PCs),tuple(GP1_PCs),lens,stops


def mmio_witness_source():
    phase_pcs,gp1_pcs,lens,stops=expected_phase_source()
    def fmt_rows(items):
        return ",\n".join("    {"+",".join(f"0x{v:08x}u" for v in row)+"}" for row in items)
    pc_data=fmt_rows(phase_pcs)
    gp0_data=fmt_rows(PHASE_GP0)
    reset_data=",".join(f"0x{(x or 0):08x}u" for x in PHASE_GP1)
    gp1_pc_data=",".join(f"0x{x:08x}u" for x in gp1_pcs)
    count_data=",".join(f"{x}u" for x in lens)
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Source-derived MIPS SW PC, GPU GP0/GP1 instruction data, stage bound.
 * Strictly observational: never changes CPU, GPU, clocks or VRAM. */
static const u32 vh171_gp0_pc[4][49]={
VH171_GP0_PCS
};
static const u32 vh171_gp0_words[4][49]={
VH171_GP0_WORDS
};
static const u32 vh171_gp1_pc[4]={VH171_GP1_PCS};
static const u32 vh171_gp1_words[4]={VH171_GP1_WORDS};
static const unsigned vh171_gp0_lengths[4]={VH171_LENGTHS};
static unsigned vh171_active,vh171_stage,vh171_seen,vh171_gp1_seen,vh171_faults;
int vh171_arm_guest_phase(unsigned stage) {
    if(vh171_active || stage>=4u)return -1;
    vh171_active=1u;vh171_stage=stage;
    vh171_seen=vh171_gp1_seen=vh171_faults=0u;
    return 0;
}
static void vh171_note_phase_mips_mmio(psxRegisters *regs,u32 address,u32 value) {
    u32 physical=address&0x1fffffffu;
    if(!vh171_active)return;
    if(physical!=0x1f801810u && physical!=0x1f801814u)return;
    if(!regs || regs->code!=0xad090000u){vh171_faults++;return;}
    if(physical==0x1f801814u){
        if(vh171_gp1_pc[vh171_stage]==0u || vh171_gp1_seen ||
           vh171_seen || regs->pc!=vh171_gp1_pc[vh171_stage]+4u ||
           value!=vh171_gp1_words[vh171_stage])
            vh171_faults++;
        else vh171_gp1_seen=1u;
        return;
    }
    if((vh171_gp1_pc[vh171_stage]!=0u && vh171_gp1_seen!=1u) ||
       vh171_seen>=vh171_gp0_lengths[vh171_stage] ||
       regs->pc!=vh171_gp0_pc[vh171_stage][vh171_seen]+4u ||
       value!=vh171_gp0_words[vh171_stage][vh171_seen]){
        vh171_faults++;
        return;
    }
    vh171_seen++;
}
unsigned vh171_guest_phase_gp0_words(void){return vh171_seen;}
unsigned vh171_guest_phase_gp1_writes(void){return vh171_gp1_seen;}
unsigned vh171_guest_phase_faults(void){return vh171_faults;}
int vh171_disarm_guest_phase(void){
    if(!vh171_active)return -1;
    vh171_active=0u;
    return 0;
}
#endif

""".replace("VH171_GP0_PCS",pc_data).replace(
    "VH171_GP0_WORDS",gp0_data).replace(
    "VH171_GP1_PCS",gp1_pc_data).replace(
    "VH171_GP1_WORDS",reset_data).replace(
    "VH171_LENGTHS",count_data)


def patch_memory(source:str):
    if "vh171_note_phase_mips_mmio" in source:
        raise ValueError("refuse duplicate v171 native phase observer")
    source=once(source,MEM_DECL,mmio_witness_source()+MEM_DECL,
                "source-authored 4x phase GPU MMIO native observer")
    return once(source,MEM_OBSERVE,
                "    if(vh171_active) vh171_note_phase_mips_mmio(regs,mem,value);\n"
                +MEM_OBSERVE,"native MMIO insertion before original v138 observer")


def multiphase_oracle():
    pcs, gp1, lens, stops=expected_phase_source()
    src=v77_oracle(stops).replace("vh77_multiphase_smoke","vh171_mips_multiphase_smoke")
    loop="\t\tfor(unsigned int phase=0;phase<4;phase++) {\n\t\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"
    if src.count(loop)!=1:
        raise ValueError("original v77 loop and real interpreter call changed")
    src=src.replace(loop,
        "\t\tunsigned int vh171_total_gp0=0u,vh171_total_gp1=0u;\n"
        "\t\tfor(unsigned int phase=0;phase<4;phase++) {\n"
        "\t\t\tif(vh171_arm_guest_phase(phase)!=0){\n"
        '                SysPrintf("VH171_PHASE_ARM_REFUSED phase=%u\\n",phase);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 77;\n"
        "\t\t\t}\n"
        "\t\t\tpsxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);\n"
        "\t\t\tunsigned int vh171_gp0=vh171_guest_phase_gp0_words();\n"
        "\t\t\tunsigned int vh171_gp1=vh171_guest_phase_gp1_writes();\n"
        "\t\t\tunsigned int vh171_bad=vh171_guest_phase_faults();\n"
        "\t\t\tint vh171_disarm=vh171_disarm_guest_phase();\n"
        "\t\t\tconst unsigned int vh171_expected_gp0[4]={49u,7u,7u,9u};\n"
        "\t\t\tconst unsigned int vh171_expected_gp1[4]={1u,0u,1u,1u};\n"
        "\t\t\tif(vh171_disarm!=0 || vh171_gp0!=vh171_expected_gp0[phase] ||\n"
        "\t\t\t   vh171_gp1!=vh171_expected_gp1[phase] || vh171_bad){\n"
        '                SysPrintf("VH171_PHASE_GPU_ORIGIN_REFUSED phase=%u gp0=%u gp1=%u faults=%u\\n",phase,vh171_gp0,vh171_gp1,vh171_bad);\n'
        "\t\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 77;\n"
        "\t\t\t}\n"
        "\t\t\tvh171_total_gp0+=vh171_gp0;\n"
        "\t\t\tvh171_total_gp1+=vh171_gp1;")
    marker='\t\tSysPrintf("VH77_MULTIPHASE_PASS phases=4 samples=2380 gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1\\n");'
    if src.count(marker)!=1:
        raise ValueError("independent v77 2380 pixel + GPU state pass changed")
    src=src.replace(marker,
        "\t\tif(vh171_total_gp0!=72u || vh171_total_gp1!=3u){\n"
        '            SysPrintf("VH171_PHASE_AGGREGATE_REFUSED gp0=%u gp1=%u\\n",vh171_total_gp0,vh171_total_gp1);\n'
        "\t\t\tClosePlugins();SysClose();menu_finish();plat_finish();return 77;\n"
        "\t\t}\n"
        '        SysPrintf("VH171_GUEST_MIPS_MULTIPHASE_VRAM_PASS phases=4 gp0_words=72 gp1_writes=3 samples=2380' +
        ' pixel_regions=6 fifo_reset_kept=1 full_reset_cleared=1 vblank_asserted=0 original_retail=0\\n");\n'
        +marker)
    return src


def patch_frontend(source:str):
    if "vh171_mips_multiphase_smoke" in source:
        raise ValueError("v171 multi-phase mode already installed")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
        "\tint vh171_mips_multiphase_smoke = 0;\n"
        "\textern int vh171_arm_guest_phase(unsigned);\n"
        "\textern unsigned vh171_guest_phase_gp0_words(void);\n"
        "\textern unsigned vh171_guest_phase_gp1_writes(void);\n"
        "\textern unsigned vh171_guest_phase_faults(void);\n"
        "\textern int vh171_disarm_guest_phase(void);\n",
        "v171 separate guest MIPS phase diagnostics declarations")
    source=once(source,FRONT_CLI,
        '\t\telse if (!strcmp(argv[i], "--vh171-mips-multiphase-vram"))\n'
        '\t\t\tvh171_mips_multiphase_smoke=1;\n'+FRONT_CLI,
        "v171 four-phase synthetic MIPS mode")
    return once(source,ORACLE_POSITION,multiphase_oracle()+"\n"+ORACLE_POSITION,
        "unchanged v77 multi-phase real CPU/GP1/VRAM oracle")


def apply(root:Path):
    report=apply_v170(root)
    mem=root.resolve()/"libpcsxcore/psxmem.c"
    front=root.resolve()/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(report,
        v171_guest_mips_four_execution_phases=4,
        v171_guest_gp0_source_words=72,
        v171_guest_gp1_source_writes=3,
        v171_gpu_vram_samples_across_phases=2380,
        v171_actual_hardware_vblank_boundaries_verified=False,
        v171_retail_map02_executed=False,
        v171_nintendo_switch_graphics_verified=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(parser.parse_args().pinned_pcsx_checkout))
