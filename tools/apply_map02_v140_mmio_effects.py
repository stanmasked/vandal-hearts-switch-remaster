#!/usr/bin/env python3
"""Exact effective MMIO address/value witness in a real MIPS interpreter.

The source program is entirely synthetic. Full MIPS codewords and CPU-stage
ordering are already bound by v139; v140 checks independently source-authored
GP0 setup and DMA2 register values. Never publish game words or MMIO payloads.
"""
from __future__ import annotations
from pathlib import Path
from .apply_map02_v139_mips_word_stages import (
    apply as apply_v139,codeword_expectations,modify_oracle as v139_oracle,
)
from .apply_map02_v138_interpreter_pc import modified_native_oracle
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build
from .make_map02_v125_variable_gpu_dma_exe import (
    BASES,DMA2_BCR,DMA2_CHCR,DMA2_DPCR,
)
from .make_map02_v121_mips_gp0_return_exe import SETUP


def expected_actual_mmio():
    """Return bounded self-authored PS1 effective address/value pairs."""
    sites,words,prefixes=codeword_expectations()
    observed=[(0x1f801810,word) for word in SETUP]
    observed.append((0x1f8010f0,DMA2_DPCR))
    for base in BASES:
        observed.extend(((0x1f8010a8,0),
                         (0x1f8010a0,base),
                         (0x1f8010a4,DMA2_BCR),
                         (0x1f8010a8,DMA2_CHCR)))
    kind_by_address={
        0x1f801810:"gpu_gp0",0x1f8010f0:"dma_dpcr",
        0x1f8010a8:"dma2_chcr",0x1f8010a0:"dma2_madr",
        0x1f8010a4:"dma2_bcr",
    }
    if (len(sites)!=19 or len(observed)!=19 or
            len(SETUP)!=6 or len(BASES)!=3 or
            prefixes!=(7,11,15,19) or
            DMA2_DPCR!=0x00000800 or
            DMA2_CHCR!=0x01000401 or DMA2_BCR!=0 or
            any(not 0<=value<=0xffffffff or kind_by_address[addr]!=site[2]
                for site,(addr,value) in zip(sites,observed))):
        raise ValueError("source-authored PS1 MIPS MMIO value profile refused")
    return tuple(observed)


def patch_native_value_observer(source):
    observed=expected_actual_mmio()
    addresses=", ".join("0x%08xu"%a for a,v in observed)
    values=", ".join("0x%08xu"%v for a,v in observed)
    extra="""
static const unsigned vh140_expected_addr[]={VH140_ADDRS};
static const unsigned vh140_expected_value[]={VH140_VALUES};
static unsigned vh140_active,vh140_bad,vh140_count,vh140_mutate;
static unsigned vh140_gp0,vh140_dma2_starts,vh140_dma2_resets;
typedef char vh140_addr_count_bound[
    (sizeof(vh140_expected_addr)/sizeof(vh140_expected_addr[0])==
     VH138_EXPECTED_COUNT)?1:-1];
typedef char vh140_value_count_bound[
    (sizeof(vh140_expected_value)/sizeof(vh140_expected_value[0])==
     VH138_EXPECTED_COUNT)?1:-1];
void vh140_mmio_enable(unsigned mutate_expected) {
    vh140_active=1u; vh140_bad=0u; vh140_count=0u;
    vh140_gp0=0u; vh140_dma2_starts=0u; vh140_dma2_resets=0u;
    vh140_mutate=mutate_expected?1u:0u;
}
unsigned vh140_mmio_verify(void) {
    vh140_active=0u;
    return vh140_bad==0u && vh140_count==VH138_EXPECTED_COUNT &&
           vh140_gp0==6u && vh140_dma2_starts==3u &&
           vh140_dma2_resets==3u ? 0u:1u;
}
static void vh140_mmio_observe(u32 addr,u32 value) {
    unsigned expected_value;
    if(!vh140_active) return;
    if(vh140_count>=VH138_EXPECTED_COUNT) {
        vh140_bad++; return;
    }
    expected_value=vh140_expected_value[vh140_count];
    /* Modify only an expected GP0 word, NEVER simulated CPU/GPU state. */
    if(vh140_mutate && vh140_count==2u)
        expected_value^=1u;
    if(addr!=vh140_expected_addr[vh140_count] ||
       value!=expected_value)
        vh140_bad++;
    if(addr==0x1f801810u) vh140_gp0++;
    if(addr==0x1f8010a8u && value==0x01000401u)
        vh140_dma2_starts++;
    if(addr==0x1f8010a8u && value==0u)
        vh140_dma2_resets++;
    vh140_count++;
}
""".replace("VH140_ADDRS",addresses).replace("VH140_VALUES",values)
    source=once(source,
        "void vh139_enable(unsigned corrupt) {\n",
        extra+"void vh139_enable(unsigned corrupt) {\n",
        "v140 exact address/value tables from synthetic CPU and GP0 source")
    hook="""    /* Observe the full effective address and value before existing
     * PC/opcode/MMIO classification, without editing emulated state. */
    if(vh140_active) vh140_mmio_observe(addr,value);
"""
    source=once(source,
        "    /* Check the whole fetched, executed MIPS instruction word, not only\n",
        hook+"    /* Check the whole fetched, executed MIPS instruction word, not only\n",
        "v140 actual interpreted MIPS MMIO tuple observer")
    return source


def patch_synthetic_oracle(source):
    source=once(source,
        "        extern void vh139_enable(unsigned corrupt);\n",
        "        extern void vh139_enable(unsigned corrupt);\n"
        "        extern void vh140_mmio_enable(unsigned mutate_expected);\n"
        "        extern unsigned vh140_mmio_verify(void);\n",
        "v140 native effective-address/value verification functions")
    source=once(source,
        "        if(vh139_word_capture && !vh138_pc_capture){\n",
        '        if(vh140_value_capture && !vh139_word_capture){\n'
        '            SysPrintf("VH140_MODE_REFUSED\\n");\n'
        '            ClosePlugins();SysClose();menu_finish();plat_finish();return 50;\n'
        '        }\n'
        "        if(vh139_word_capture && !vh138_pc_capture){\n",
        "v140 requires previously verified real SW PC and MIPS codeword")
    source=once(source,
        "        if(vh139_word_capture) vh139_enable(vh139_corrupt_word);\n",
        "        if(vh139_word_capture) vh139_enable(vh139_corrupt_word);\n"
        "        if(vh140_value_capture) vh140_mmio_enable(vh140_corrupt_value);\n",
        "v140 opt-in effect witness enabled before native MIPS setup")
    guard="""            if(vh140_value_capture){
                if(vh140_mmio_verify()!=0u){
                    SysPrintf("VH140_NATIVE_MMIO_VALUE_REFUSED\\n");
                    ClosePlugins();SysClose();menu_finish();plat_finish();return 50;
                }
                SysPrintf("VH140_NATIVE_MMIO_VALUES_PASS"
                          " matched=19 gp0=6 dma2_starts=3"
                          " stages=4 original_retail=0\\n");
            }
"""
    source=once(source,
        "            if(vh139_word_capture){\n",
        guard+"            if(vh139_word_capture){\n",
        "native v140 MMIO equality before v139/v138 PASS markers")
    return source


def apply(root:Path):
    previous=apply_v139(root)
    events,_,_=codeword_expectations()
    effect=expected_actual_mmio()
    folder=root.resolve()
    memory=folder/"libpcsxcore/psxmem.c"
    front=folder/"frontend/main.c"
    mem=patch_native_value_observer(memory.read_text())
    main=front.read_text()
    main=once(main,"\tint vh139_corrupt_word = 0;\n",
        "\tint vh139_corrupt_word = 0;\n"
        "\tint vh140_value_capture = 0;\n"
        "\tint vh140_corrupt_value = 0;\n",
        "v140 independent opt-in native MMIO data flags")
    main=once(main,
        '\t\telse if (!strcmp(argv[i], "--vh139-codewords"))\n',
        '\t\telse if (!strcmp(argv[i], "--vh140-mmio-values"))\n'
        '\t\t\tvh140_value_capture=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh140-corrupt-value-witness"))\n'
        '\t\t\tvh140_corrupt_value=1;\n'
        '\t\telse if (!strcmp(argv[i], "--vh139-codewords"))\n',
        "v140 opt-in real native address/value validation")
    _,stops,_,_,wait_pc=build()
    old=v139_oracle(modified_native_oracle(
        stops,wait_pc,len(events)),len(events))
    new=patch_synthetic_oracle(old)
    main=once(main,old,new,
        "unique unchanged v139 source-authored four-stage CPU oracle")
    memory.write_text(mem)
    front.write_text(main)
    return dict(previous,
        v140_native_synthetic_mmio_effects=len(effect),
        v140_exact_gp0_setup_values=6,
        v140_dma2_linked_list_starts=3,
        v140_interpreter_effect_data_bound=True,
        original_retail_MAP02_executed=False,
        physical_ps1_gpu_parity_proven=False,
        nintendo_switch_hd_parity_proven=False)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout",type=Path)
    print(apply(parser.parse_args().checkout))
