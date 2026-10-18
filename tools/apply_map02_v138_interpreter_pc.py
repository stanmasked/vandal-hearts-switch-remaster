#!/usr/bin/env python3
"""Actual pinned PCSX *interpreter* MMIO SW-PC runtime witness, synthetic only.

Stack onto the proven v129 PCSX ReARMed observer without touching it. The
temporary pinned interpreter's psxMemWrite32 sees regs->pc one word beyond
the currently executed instruction. Capture (regs->pc-4, MMIO class) only
while running signed self-authored v129 MIPS code. Independently construct
the exact ordered expectation from the v132 *static* scanner.

The hook neither alters PS1 registers, GPU/DMA data, VBlank cycles nor Unai.
It never prints PCs or instruction words. An opt-in negative switch corrupts
the private in-process witness to prove the comparison can actually refuse.
"""
from __future__ import annotations
from pathlib import Path

from .apply_map02_v129_pcsx_rearmed import (
    apply as apply_v129,oracle_source as original_oracle,
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build
from .analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text
from .analyze_map02_v131_private_mips_mmio import NAME_ORDER

# Source-authored synthetic MIPS, never original retail code.
MIPS_START=0x80010000
MAX_EVENTS=128
CLASS_CODES={name:i+1 for i,name in enumerate(NAME_ORDER)}
REGISTER_MAP={
    0x1f8010a0:"dma2_madr",
    0x1f8010a4:"dma2_bcr",
    0x1f8010a8:"dma2_chcr",
    0x1f8010f0:"dma_dpcr",
    0x1f801810:"gpu_gp0",
    0x1f801814:"gpu_gp1",
}

def expected_pc_events():
    data,stops,ops,starts,wait_pc=build()
    if len(data)!=10240 or len(ops)<25 or starts[0]!=MIPS_START:
        raise ValueError("refusing unexpected v129 synthetic PS-X program")
    if data[2048:2048+len(ops)*4]!=b"".join(
        int(word).to_bytes(4,"little") for word in ops):
        raise ValueError("v129 executable and instruction tuples differ")
    events=[]
    counts,delays=analyze_delay_aware_text(
        data[2048:2048+len(ops)*4],
        site_sink=lambda offset,kind,linked: events.append(
            (MIPS_START+offset,CLASS_CODES[kind],kind,linked)),
    )
    if (not 10<len(events)<MAX_EVENTS or
            counts["dma2_madr"]!=3 or counts["dma2_bcr"]!=3 or
            counts["dma2_chcr"]!=6 or
            counts["dma2_linked_list_chcr_literal"]!=3 or
            counts["dma_dpcr"]!=1 or counts["gpu_gp0"]<1 or
            counts["gpu_gp1"]!=0 or
            delays["ambiguous_control_in_delay_slot"]!=0 or
            len({pc for pc,*_ in events})!=len(events)):
        raise ValueError("synthetic MIPS MMIO PC expectation refused")
    return tuple(events)


def native_probe_declarations(events):
    addresses=", ".join(f"0x{pc:08x}u" for pc,*_ in events)
    classes=", ".join(f"{kind}u" for _,kind,*_ in events)
    return """
#ifdef VH_MAP02_V66_PCSX_PROBE
/* All addresses below are generated from self-authored synthetic MIPS.
 * Do not log raw PCs or GPU words: the code table stays in this temporary
 * pinned emulator build and never represents user-owned retail source. */
static const unsigned vh138_expected_pc[] = { VH138_EXPECTED_PCS };
static const unsigned vh138_expected_kind[] = { VH138_EXPECTED_KINDS };
static unsigned vh138_seen, vh138_bad, vh138_active;
#define VH138_EXPECTED_COUNT \
    (sizeof(vh138_expected_pc)/sizeof(vh138_expected_pc[0]))
typedef char vh138_expected_shapes_match[
    (sizeof(vh138_expected_pc)/sizeof(vh138_expected_pc[0]) ==
     sizeof(vh138_expected_kind)/sizeof(vh138_expected_kind[0]))?1:-1];
void vh138_pc_enable(void) {
    vh138_seen=0u; vh138_bad=0u; vh138_active=1u;
}
void vh138_pc_inject_error(void) { vh138_bad++; }
unsigned vh138_pc_check(void) {
    vh138_active=0u;
    return (vh138_bad==0u && vh138_seen==VH138_EXPECTED_COUNT)?0u:1u;
}
unsigned vh138_pc_count(void) { return vh138_seen; }
static void vh138_pc_observe(psxRegisters *regs,u32 addr,u32 value) {
    unsigned cls=0u,physical=addr&0x1fffffffu;
    if(!vh138_active) return;
    switch(physical) {
      case 0x1f8010a0u: cls=1u; break; /* DMA2 MADR */
      case 0x1f8010a4u: cls=2u; break; /* DMA2 BCR */
      case 0x1f8010a8u: cls=3u; break; /* DMA2 CHCR */
      case 0x1f8010f0u: cls=4u; break; /* DMA DPCR */
      case 0x1f801810u: cls=5u; break; /* GPU GP0 */
      case 0x1f801814u: cls=6u; break; /* GPU GP1 */
      default: return;
    }
    /* The pinned psxinterpreter.c execI_ advances regs->pc by four
     * BEFORE decoding and executing the current regs->code. Any
     * unexpected opcode or wrong PC / class / event order refuses. */
    if((regs->code>>26)!=0x2bu || (regs->pc&3u) ||
       vh138_seen>=VH138_EXPECTED_COUNT ||
       vh138_expected_pc[vh138_seen]!=regs->pc-4u ||
       vh138_expected_kind[vh138_seen]!=cls ||
       (physical==0x1f8010a8u &&
        (value!=0u && value!=0x01000401u)))
        vh138_bad++;
    else
        vh138_seen++;
}
#endif

""".replace("VH138_EXPECTED_PCS",addresses).replace("VH138_EXPECTED_KINDS",classes)


def modified_native_oracle(stops,wait_pc,expected_count):
    src=original_oracle(stops,wait_pc)
    src=once(src,"    if(vh129_vblank_mode>=0) {",
        """    if(vh129_vblank_mode>=0) {
        extern void vh138_pc_enable(void);
        extern unsigned vh138_pc_check(void);
        extern void vh138_pc_inject_error(void);
        extern unsigned vh138_pc_count(void);
        if(vh138_pc_capture && vh129_vblank_mode!=0){
            SysPrintf("VH138_MODE_REFUSED\\n");
            ClosePlugins();SysClose();menu_finish();plat_finish();return 48;
        }""",
        "opt-in v129 first split only with unchanged other v129 cases")
    anchor="""        /* Execute GPU setup as an original interpreted MIPS stage. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"""
    replacement="""        /* Observe real MIPS interpreter MMIO writes including setup.
         * No host clock, VBlank, DMA or GPU write injection. */
        if(vh138_pc_capture) vh138_pc_enable();
        /* Execute GPU setup as an original interpreted MIPS stage. */
        psxCpu->ExecuteBlock(&psxRegs,EXEC_CALLER_OTHER);"""
    src=once(src,anchor,replacement,"enable interpreter PC capture before actual setup MIPS")
    status='        SysPrintf("VH129_REAL_VBLANK_PROFILES_PASS mode=%u gaps=%u,%u,%u,%u "'
    guard="""        if(vh138_pc_capture){
            if(vh138_pc_inject_bad) vh138_pc_inject_error();
            if(vh138_pc_check()!=0u || vh138_pc_count()!=VH138_COUNT){
                SysPrintf("VH138_NATIVE_MIPS_PC_REFUSED\\n");
                ClosePlugins();SysClose();menu_finish();plat_finish();return 48;
            }
            SysPrintf("VH138_NATIVE_INTERPRETER_PC_PASS"
                      " matched=VH138_COUNT"
                      " real_interpreter_sw=1 original_retail=0\\n");
        }
""".replace("VH138_COUNT",str(expected_count))
    src=once(src,status,guard+status,"private ordered native PC witness before old four-vblank PASS")
    return src


def apply(root:Path):
    prior=apply_v129(root)
    base=root.resolve()
    memfile=base/"libpcsxcore/psxmem.c"
    mainfile=base/"frontend/main.c"
    mem=memfile.read_text()
    front=mainfile.read_text()
    events=expected_pc_events()
    mem=once(mem,"void psxMemWrite32(psxRegisters *regs, u32 mem, u32 value) {",
        native_probe_declarations(events)+
        "void psxMemWrite32(psxRegisters *regs, u32 mem, u32 value) {",
        "native exact SW PC witness at pinned actual psxMemWrite32")
    mark="""void psxMemWrite32(psxRegisters *regs, u32 mem, u32 value) {
\tu8 *p;
\tu32 t;
"""
    mem=once(mem,mark,mark+"""
#ifdef VH_MAP02_V66_PCSX_PROBE
    vh138_pc_observe(regs,mem,value);
#endif
""","capture immediately inside actual MIPS write, before side effects")
    front=once(front,"\tint vh129_vblank_mode = -1;\n",
        "\tint vh129_vblank_mode = -1;\n"
        "\tint vh138_pc_capture = 0;\n"
        "\tint vh138_pc_inject_bad = 0;\n",
        "new v138 independent opt-in diagnostics variables")
    cli='\\t\\telse if (!strcmp(argv[i], "--vh129-vblank-04"))\\n'
    # Python source escapes must match literal tab from pinned patch.
    cli="\t\telse if (!strcmp(argv[i], \"--vh129-vblank-04\"))\n"
    front=once(front,cli,
        "\t\telse if (!strcmp(argv[i], \"--vh138-interpreter-pc\"))\n"
        "\t\t\tvh138_pc_capture=1;\n"
        "\t\telse if (!strcmp(argv[i], \"--vh138-corrupt-pc-witness\"))\n"
        "\t\t\tvh138_pc_inject_bad=1;\n"+cli,
        "separate opt-in native PC positive/negative flags")
    _,stops,_,_,wait_pc=build()
    front=once(front,original_oracle(stops,wait_pc),
        modified_native_oracle(stops,wait_pc,len(events)),
        "only v129 native oracle gets optional true CPU PC/MMIO witness")
    memfile.write_text(mem)
    mainfile.write_text(front)
    return dict(prior,
        actual_interpreted_mips_store_pc_observation=True,
        synthetic_expected_site_count=len(events),
        expected_site_orders_cross_checked=True,
        observation_in_psxMemWrite32_before_gpu_dma_side_effects=True,
        failed_witness_deliberate_corruption_refused=True,
        original_v129_modes_unmodified_without_optin=True,
        no_gpu_or_vblank_injection=True,
        retail_original_execution_verified=False,
        original_map02_gameplay_verified=False,
        nintendo_switch_parity_verified=False,
    )


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
