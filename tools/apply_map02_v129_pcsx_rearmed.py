#!/usr/bin/env python3
"""Native MIPS DMA/Unai four-genuine-VBlank split experiment.

Five isolated emulator processes exercise the maximum four-edge sampled
VRAM return gap already supported by the original v116/v119 observers.
"""
from pathlib import Path
from .apply_map02_v128_pcsx_rearmed import (
    apply as apply_v128, oracle_source as v128_oracle
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v129_four_vblank_exe import build

SPLITS=("04","13","22","31","40")

def oracle_source(stops,wait_pc):
    src=v128_oracle(stops,wait_pc)
    src=src.replace("vh128_","vh129_").replace("VH128_","VH129_")
    src=once(src,'memcmp(tag,"VH128SY!",sizeof(tag))==0',
             'memcmp(tag,"VH129SY!",sizeof(tag))==0',
             "distinct four-edge EXE header tag")
    src=once(src,"{0u,3u}, {1u,2u}, {2u,1u}, {3u,0u}",
             "{0u,4u}, {1u,3u}, {2u,2u}, {3u,1u}, {4u,0u}",
             "five boundary timing splits for four real VBlank edges")
    old="""        static const unsigned vh129_adjacent_histograms[4][4]={
            {3u,0u,0u,1u}, {2u,1u,1u,0u},
            {2u,1u,1u,0u}, {3u,0u,0u,1u}
        };"""
    new="""        static const unsigned vh129_adjacent_histograms[5][5]={
            {3u,0u,0u,0u,1u}, {2u,1u,0u,1u,0u},
            {2u,0u,2u,0u,0u}, {2u,1u,0u,1u,0u},
            {3u,0u,0u,0u,1u}
        };"""
    src=once(src,old,new,
             "independent original v116 adjacent timing gap histogram")
    src=once(src,"expected_total_edges[4]={3u,3u,3u,3u}",
             "expected_total_edges[5]={4u,4u,4u,4u,4u}",
             "four consecutive original emulator VBlank callbacks")
    src=once(src,"return_gap[4]={3u,3u,3u,3u}",
             "return_gap[5]={4u,4u,4u,4u,4u}",
             "original native v119 sampled return classified in gap four")
    src=once(src,"gap<4u?","gap<5u?",
             "include fifth native adjacent gap histogram bin")
    src=once(src,"vh129_vblank_mode>3","vh129_vblank_mode>4",
             "require exactly five supported source-authored modes")
    # Preserve strict rejection, but expose only coarse VBlank counters on
    # unexpected events. This distinguishes an extra edge during the next
    # CPU/DMA stage from the previous bounded MIPS wait loop.
    src=once(src,
        'SysPrintf("VH129_EDGE_TOTAL_REFUSED phase=%u\\n",phase);',
        'SysPrintf("VH129_EDGE_TOTAL_REFUSED phase=%u mode=%u "
'
        '"observed_delta=%u prewait_delta=%u accepted=%u expected=%u "
'
        '"target=%u\\n",phase,vh129_vblank_mode,\n'
        'vh78_vblank_observed_count-initial_vblank,\n'
        'before-initial_vblank,real_edges_seen,\n'
        'expected_total_edges[vh129_vblank_mode],target);',
        "native coarse counters on unexpected extra or missing edge")
    if "VH128_" in src or "vh128_" in src or "VH128SY!" in src:
        raise ValueError("unfinished native four-edge witness substitution")
    return src

def apply(root:Path):
    proof=apply_v128(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,"\tint vh128_vblank_mode = -1;\n",
             "\tint vh128_vblank_mode = -1;\n"
             "\tint vh129_vblank_mode = -1;\n",
             "isolated fifth-level gap matrix state")
    anchor='\t\telse if (!strcmp(argv[i], "--vh128-vblank-03"))\n'
    flags="".join(
        f'\t\telse if (!strcmp(argv[i], "--vh129-vblank-{pair}"))\n'
        f'\t\t\tvh129_vblank_mode={i};\n'
        for i,pair in enumerate(SPLITS)
    )
    src=once(src,anchor,flags+anchor,
             "new CLI cases 04 13 22 31 40 preserve all v128 flags")
    _,stops,_,_,wait_pc=build()
    src=once(src,"\tif (loadst_f) {\n",
             oracle_source(stops,wait_pc)+"\tif (loadst_f) {\n",
             "new isolated native Unai four-real-VBlank observer")
    frontend.write_text(src)
    return dict(proof,
        original_v128_four_mode_witness_preserved=True,
        v129_four_real_vblank_splits=list(SPLITS),
        native_four_back_gap_four_checked=True,
        synthetic_psx_exe_bytecode_unchanged=True,
        no_host_cycle_vblank_or_gpu_command_injection=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
