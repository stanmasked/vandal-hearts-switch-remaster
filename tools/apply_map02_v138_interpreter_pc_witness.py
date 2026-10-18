#!/usr/bin/env python3
"""Instrument the *actual pinned PCSX interpreter SW handler* for private PC proof.

The observed PC is regs_->pc - 4 at the actual interpreted SW, NOT a
host-inferred PC from a DMA callback, phase marker, or post-block stop.
Captures only synthetic v129 stages 1-3 (three DMA2 linked lists), compares
each runtime instruction PC, raw opcode and actual MMIO target class against
a distinct static source-authored v129 MIPS program, and exposes only counts.
"""
from __future__ import annotations

from pathlib import Path
import struct

from .apply_map02_v129_pcsx_rearmed import apply as apply_v129, oracle_source
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build
from .analyze_map02_v132_mips_delay_slots import analyze_delay_aware_text

KIND = {"dma2_madr":1,"dma2_bcr":2,"dma2_chcr":3}
EXPECTED_COUNT=12


def source_authored_expected_sw_sites():
    exe,stops,_ops,starts,wait_pc=build()
    payload=exe[2048:2048+struct.unpack_from("<I",exe,0x1c)[0]]
    sites=[]
    def record(offset,kind,linked):
        pc=starts[0]+offset
        if starts[1]<=pc<stops[-1] and kind in KIND:
            instruction=struct.unpack_from("<I",payload,offset)[0]
            sites.append((pc,KIND[kind],instruction,bool(linked)))
    counts,_metadata=analyze_delay_aware_text(payload,site_sink=record)
    if (len(sites)!=EXPECTED_COUNT or
            [kind for _,kind,_,_ in sites]!=[3,1,2,3]*3 or
            sum(linked for _,_,_,linked in sites)!=3 or
            counts["dma2_madr"]!=3 or counts["dma2_bcr"]!=3 or
            counts["dma2_chcr"]!=6):
        raise ValueError("synthetic stage SW MMIO static inventory changed")
    if len({pc for pc,_,_,_ in sites})!=len(sites):
        raise ValueError("duplicate synthetic MMIO instruction site")
    return tuple(sites)


def native_sw_observer_source(sites):
    if len(sites)!=EXPECTED_COUNT:
        raise ValueError("exactly twelve source-authored DMA2 MMIO stores expected")
    def arr(field):
        return "{"+",".join(f"0x{int(v[field]):08x}u" for v in sites)+"}"
    return r"""
#ifdef VH_MAP02_V66_PCSX_PROBE
/* Private synthetic-only CPU instruction-origin observer. All PCs and
 * raw opcodes stay in this process. Public logs contain aggregate counts. */
unsigned int vh138_enabled;
unsigned int vh138_seen;
unsigned int vh138_bad;
static const u32 vh138_expected_pc[12]=VH138_PCS;
static const u32 vh138_expected_opcode[12]=VH138_OPS;
static const u32 vh138_expected_kind[12]=VH138_KINDS;
static const u32 vh138_expected_linked[12]=VH138_LINKED;

static void vh138_observe_interpreted_sw(
    u32 current_pc, u32 instruction, u32 effective_address, u32 source_value)
{
    unsigned int kind=0;
    u32 physical;
    unsigned int slot;
    if(!vh138_enabled) return;
    physical=effective_address & 0x1fffffffu;
    if((effective_address & 0xe0000000u)!=0x00000000u &&
       (effective_address & 0xe0000000u)!=0x80000000u &&
       (effective_address & 0xe0000000u)!=0xa0000000u) return;
    switch(physical){
        case 0x1f8010a0u: kind=1u; break; /* DMA2 MADR */
        case 0x1f8010a4u: kind=2u; break; /* DMA2 BCR */
        case 0x1f8010a8u: kind=3u; break; /* DMA2 CHCR */
        case 0x1f8010f0u: kind=4u; break; /* DPCR, unexpected after setup */
        case 0x1f801810u: kind=5u; break; /* GP0, unexpected after setup */
        case 0x1f801814u: kind=6u; break; /* GP1, unexpected after setup */
        default: return;
    }
    slot=vh138_seen;
    if(slot>=12u || current_pc!=vh138_expected_pc[slot] ||
       instruction!=vh138_expected_opcode[slot] ||
       kind!=vh138_expected_kind[slot] ||
       (vh138_expected_linked[slot]!=0u &&
        (kind!=3u || source_value!=0x01000401u))){
        vh138_bad++;
        return;
    }
    vh138_seen++;
}
#endif

""".replace("VH138_PCS",arr(0)).replace("VH138_KINDS",arr(1)).replace(
       "VH138_OPS",arr(2)).replace(
       "VH138_LINKED","{"+",".join("1u" if x[3] else "0u" for x in sites)+"}")


def enriched_native_oracle(stops,wait_pc):
    original=oracle_source(stops,wait_pc)
    patched=once(original,
        "        vh125_dma_enabled=1;\n",
        "        vh125_dma_enabled=1;\n"
        "        /* Set by frontend only after setup GP0/DPCR has drained. */\n"
        "        extern unsigned int vh138_enabled;\n"
        "        extern unsigned int vh138_seen;\n"
        "        extern unsigned int vh138_bad;\n"
        "        vh138_seen=0u;vh138_bad=0u;vh138_enabled=1u;\n",
        "interpreter witness start after synthetic MIPS GPU setup")
    patched=once(patched,
        "        vh125_dma_enabled=0;\n",
        "        vh125_dma_enabled=0;\n"
        "        vh138_enabled=0u;\n",
        "stop interpreter witness after exactly three real DMA2 stages")
    marker="        vh115_reset();\n"
    extra=(
        "        if(vh138_seen!=12u || vh138_bad!=0u){\n"
        "            SysPrintf(\"VH138_CPU_SW_PC_REFUSED seen=%u bad=%u\\n\",\n"
        "                      vh138_seen,vh138_bad);\n"
        "            ClosePlugins();SysClose();menu_finish();plat_finish();return 52;\n"
        "        }\n"
        "        SysPrintf(\"VH138_CPU_SW_PC_PASS stores=12 dma2_madr=3 \"\n"
        "                  \"dma2_bcr=3 dma2_chcr=6 linked=3 \"\n"
        "                  \"interpreter_origin=1 retail_map02_verified=0\\n\");\n"
    )
    return once(patched,marker,extra+marker,
                "observe runtime CPU SW PC/opcode/MMIO and publish totals only")


def apply(root:Path):
    proof=apply_v129(root)
    base=root.resolve()
    interp=base/"libpcsxcore/psxinterpreter.c"
    frontend=base/"frontend/main.c"
    sites=source_authored_expected_sw_sites()
    src=interp.read_text()
    src=once(src,
        "OP(psxSW) { psxMemWrite32(regs_, _oB_, _rRt_); }",
        native_sw_observer_source(sites)+
        "OP(psxSW) {\n"
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    /* Both normal and branch-delay SW have regs_->pc == origin+4. */\n"
        "    vh138_observe_interpreted_sw(regs_->pc-4u,regs_->code,_oB_,_rRt_);\n"
        "#endif\n"
        "    psxMemWrite32(regs_, _oB_, _rRt_);\n"
        "}",
        "actual pinned R3000A interpreter SW instruction handler")
    src=once(src,
        "OP(psxSWe) { if (checkST(regs_, _oB_, 3)) psxMemWrite32(regs_, _oB_, _rRt_); }",
        "OP(psxSWe) { if (checkST(regs_, _oB_, 3)) {\n"
        "#ifdef VH_MAP02_V66_PCSX_PROBE\n"
        "    vh138_observe_interpreted_sw(regs_->pc-4u,regs_->code,_oB_,_rRt_);\n"
        "#endif\n"
        "    psxMemWrite32(regs_, _oB_, _rRt_); } }",
        "aligned MIPS SW exception-check interpreter path")
    interp.write_text(src)
    _,stops,_,_,wait_pc=build()
    base_oracle=oracle_source(stops,wait_pc)
    f=frontend.read_text()
    f=once(f,base_oracle,enriched_native_oracle(stops,wait_pc),
           "only v129 synthetic five-mode real-VBlank code path")
    frontend.write_text(f)
    return dict(proof,
        v138_actual_interpreted_sw_pc_observed=True,
        v138_source_authored_expected_instruction_sites=len(sites),
        v138_observed_gpudma_register_class_checked=True,
        v138_branch_delay_slot_origin_pc_formula_checked=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
