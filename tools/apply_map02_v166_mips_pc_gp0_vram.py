#!/usr/bin/env python3
"""v166: attest exact MIPS SW instruction PC per each guest GP0 word.

Extend verified v165 native GP0 queue+Unai VRAM proof, using the actual pinned
psxMemWrite32 entry where interpreter regs->pc points one word past the SW.
The observer is read-only, synthetic-only, bounded to 5 x 3 source-built
instruction PCs and original 32-bit GP0 values. No retail MAP02 assets.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v165_guest_gp0_pixel_binding import apply as apply_v165
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v121_mips_gp0_return_exe import build,stage_body,sw,COLORS,RECT_XY,RECT_SIZE

MEM_INSERT = "void vh140_mmio_enable(unsigned mutate_expected) {\n"
MEM_CAPTURE = "    vh138_pc_observe(regs,mem,value);\n"
FRONT_DECL="\textern int vh165_disarm_guest_gp0(void);\n"
FRONT_FLAG="\tint vh165_mips_gp0_vram_bound = 0;\n"
FRONT_CLI='\t\telse if (!strcmp(argv[i], "--vh165-mips-gp0-vram-bound")) {\n'
FRONT_PHASE="            if(vh165_mips_gp0_vram_bound &&\n               vh165_arm_guest_gp0(vh165_expected_colors[phase],\n"
FRONT_OBSERVE="                int disarmed=vh165_disarm_guest_gp0();\n"
FRONT_PASS='        SysPrintf("VH121_MIPS_GP0_RETURN_PASS stages=6'

def source_pc_triplets():
    image,stops,operations,starts=build()
    if image[:8]!=b"PS-X EXE" or image[0x4c:0x54]!=b"VH121SY!" or \
       len(stops)!=6 or len(starts)!=6 or len(COLORS)!=5:
        raise ValueError("v121 guest executable identity mismatch")
    pcs=[]
    for phase in range(5):
        stage=phase+1
        body=stage_body(stage)
        locs=(4,7,10)
        if any(body[i]!=sw(9,0,8) for i in locs):
            raise ValueError("synthetic GPU SW instruction source changed")
        start=starts[stage]
        if tuple(operations[(start-starts[0])//4+i] for i in locs) != \
           tuple(body[i] for i in locs):
            raise ValueError("MIPS source stage code offset mismatch")
        pcs.append(tuple(start+4*i for i in locs))
    if len({v for row in pcs for v in row})!=15:
        raise ValueError("duplicate source-authored GP0 instruction PC")
    return tuple(pcs)

def mmio_pc_witness_c():
    rows=source_pc_triplets()
    pc_src=",\n".join("    {"+",".join(f"0x{p:08x}u" for p in row)+"}" for row in rows)
    words=[[c,RECT_XY,RECT_SIZE] for c in COLORS]
    word_src=",\n".join("    {"+",".join(f"0x{p:08x}u" for p in row)+"}" for row in words)
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* All code PCs and words generated strictly from own synthetic PS-X EXE.
 * No modification of CPU, GPU registers, packet contents, VRAM or clocks. */
static const u32 vh166_expected_pc[5][3]={
VH166_PC_SOURCE
};
static const u32 vh166_expected_words[5][3]={
VH166_WORD_SOURCE
};
static unsigned vh166_active,vh166_stage,vh166_count,vh166_fault;
int vh166_arm_guest_sw_pc(unsigned stage) {
    if(vh166_active || stage>=5u) return -1;
    vh166_active=1u; vh166_stage=stage;
    vh166_count=vh166_fault=0u;
    return 0;
}
static void vh166_observe_guest_sw_pc(psxRegisters *regs,u32 address,u32 value) {
    if(!vh166_active) return;
    if(!regs || vh166_count>=3u ||
       (address&0x1fffffffu)!=0x1f801810u ||
       regs->code!=0xad090000u ||
       regs->pc!=vh166_expected_pc[vh166_stage][vh166_count]+4u ||
       value!=vh166_expected_words[vh166_stage][vh166_count]) {
        vh166_fault++;
        return;
    }
    vh166_count++;
}
unsigned vh166_guest_sw_pc_count(void) {return vh166_count;}
unsigned vh166_guest_sw_pc_faults(void) {return vh166_fault;}
int vh166_disarm_guest_sw_pc(void) {
    if(!vh166_active) return -1;
    vh166_active=0u;
    return 0;
}
#endif

""".replace("VH166_PC_SOURCE",pc_src).replace("VH166_WORD_SOURCE",word_src)

def patch_memory(source: str) -> str:
    if "vh166_observe_guest_sw_pc" in source:
        raise ValueError("refuse duplicate MMIO source-PC observer")
    source=once(source,MEM_INSERT,mmio_pc_witness_c()+MEM_INSERT,
                "pinned native psxMemWrite32 source-derived observer declarations")
    source=once(source,MEM_CAPTURE,
                "    if(vh166_active) vh166_observe_guest_sw_pc(regs,mem,value);\n"
                +MEM_CAPTURE,
                "observe real MIPS SW PC before original optional v138 observer")
    return source

def patch_frontend(source: str) -> str:
    if "vh166_mips_pc_gp0_vram_chain" in source:
        raise ValueError("v166 already installed")
    source=once(source,FRONT_DECL,FRONT_DECL+
                "\textern int vh166_arm_guest_sw_pc(unsigned);\n"
                "\textern unsigned vh166_guest_sw_pc_count(void);\n"
                "\textern unsigned vh166_guest_sw_pc_faults(void);\n"
                "\textern int vh166_disarm_guest_sw_pc(void);\n",
                "frontend MMIO instruction-PC observer declaration")
    source=once(source,FRONT_FLAG,FRONT_FLAG+
                "\tint vh166_mips_pc_gp0_vram_chain = 0;\n",
                "separate opt-in PC-to-GP0-to-VRAM full guest provenance")
    source=once(source,FRONT_CLI,
                '\t\telse if (!strcmp(argv[i], "--vh166-mips-pc-gp0-vram-chain")) {\n'
                '\t\t\tvh121_mips_return_smoke=1;\n'
                '\t\t\tvh164_mips_raster_bounds=1;\n'
                '\t\t\tvh165_mips_gp0_vram_bound=1;\n'
                '\t\t\tvh166_mips_pc_gp0_vram_chain=1;\n'
                '\t\t}\n'+FRONT_CLI,
                "new mode also forces all earlier synthetic guest raster checks")
    source=once(source,FRONT_PHASE,
                "            if(vh166_mips_pc_gp0_vram_chain &&\n"
                "               vh166_arm_guest_sw_pc(phase)!=0){\n"
                '                SysPrintf("VH166_GUEST_SW_PC_ARM_REFUSED phase=%u\\n",phase);\n'
                "                ClosePlugins();SysClose();menu_finish();plat_finish();return 70;\n"
                "            }\n"+FRONT_PHASE,
                "arm source-derived 3 instruction PCs before guest interpreter execute")
    source=once(source,FRONT_OBSERVE,
                FRONT_OBSERVE+
                "                if(vh166_mips_pc_gp0_vram_chain){\n"
                "                    unsigned pc_count=vh166_guest_sw_pc_count();\n"
                "                    unsigned pc_bad=vh166_guest_sw_pc_faults();\n"
                "                    int pc_disarmed=vh166_disarm_guest_sw_pc();\n"
                "                    if(pc_count!=3u || pc_bad!=0u || pc_disarmed!=0){\n"
                '                        SysPrintf("VH166_GUEST_SW_PC_REFUSED phase=%u count=%u bad=%u\\n",\n'
                "                                  phase,pc_count,pc_bad);\n"
                "                        ClosePlugins();SysClose();menu_finish();plat_finish();return 70;\n"
                "                    }\n"
                "                }\n",
                "enforce source-MIPS PC + SW value before Unai pixel readback")
    source=once(source,FRONT_PASS,
                "        if(vh166_mips_pc_gp0_vram_chain){\n"
                "            if(vh165_total_words!=15u || readbacks!=5u ||\n"
                "               vh164_changes!=80u || vh164_neighbors!=100u){\n"
                '                SysPrintf("VH166_GUEST_CHAIN_TOTALS_REFUSED\\n");\n'
                "                ClosePlugins();SysClose();menu_finish();plat_finish();return 70;\n"
                "            }\n"
                '            SysPrintf("VH166_GUEST_MIPS_PC_GP0_VRAM_PASS"'
                '" phases=5 sw_pcs=15 gp0_words=15 pixels_changed=80"'
                '" border_unchanged=100 original_retail=0\\n");\n'
                "        }\n"+FRONT_PASS,
                "credit complete 15 guest MIPS PCs + GP0 + VRAM chain")
    return source

def apply(root: Path):
    prior=apply_v165(root)
    base=root.resolve()
    mem=base/"libpcsxcore/psxmem.c"
    front=base/"frontend/main.c"
    mem.write_text(patch_memory(mem.read_text()))
    front.write_text(patch_frontend(front.read_text()))
    return dict(prior,
        v166_guest_MIPS_source_SW_PCs=15,
        v166_native_MMIO_exact_GP0_words=15,
        v166_unai_VRAM_pixel_changes=80,
        v166_unmodified_neighbor_samples=100,
        v166_original_retail_executed=False,
        v166_switch_renderer_verified=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_pcsx_checkout",type=Path)
    print(apply(p.parse_args().pinned_pcsx_checkout))
