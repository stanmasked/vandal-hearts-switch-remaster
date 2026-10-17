#!/usr/bin/env python3
"""New four-way three-real-VBlank split witness, stacked on unchanged v127.

Every split has exactly three psxRcntUpdate -> GPU_vBlank callbacks:
03, 12, 21, 30. The original MIPS DMA program, GP0 packets and
512-NOP wait pad are identical to v127; only the EXE tag changes.
"""
from pathlib import Path
from .apply_map02_v127_pcsx_rearmed import (
    apply as apply_v127, oracle_source as v127_oracle
)
from .apply_map02_v69_pcsx_rearmed import once
from .make_map02_v128_triple_vblank_exe import build

SPLITS=("03","12","21","30")

def oracle_source(stops,wait_pc):
    src=v127_oracle(stops,wait_pc)
    src=src.replace("vh127_","vh128_").replace("VH127_","VH128_")
    src=once(src,'memcmp(tag,"VH127SY!",sizeof(tag))==0',
             'memcmp(tag,"VH128SY!",sizeof(tag))==0',
             "separate triple-edge synthetic CPU EXE authentication")
    src=once(src,"{0u,0u}, {1u,1u}, {0u,2u}, {2u,0u}",
             "{0u,3u}, {1u,2u}, {2u,1u}, {3u,0u}",
             "three VBlank edges distributed across two boundaries")
    old="""        static const unsigned vh128_adjacent_histograms[4][3]={
            {4u,0u,0u}, {2u,2u,0u},
            {3u,0u,1u}, {3u,0u,1u}
        };"""
    new="""        static const unsigned vh128_adjacent_histograms[4][4]={
            {3u,0u,0u,1u}, {2u,1u,1u,0u},
            {2u,1u,1u,0u}, {3u,0u,0u,1u}
        };"""
    src=once(src,old,new,"exact native adjacent gap bins for all modes")
    src=once(src,"expected_total_edges[4]={0u,2u,2u,2u}",
             "expected_total_edges[4]={3u,3u,3u,3u}",
             "three actual callback edges per emulator process")
    src=once(src,"return_gap[4]={0u,2u,2u,2u}",
             "return_gap[4]={3u,3u,3u,3u}",
             "native sampled return A classified at gap three")
    src=once(src,"gap<3u?","gap<4u?",
             "require third-edge adjacent histogram bin")
    if "VH127_" in src or "vh127_" in src or "VH127SY!" in src:
        raise ValueError("v128 oracle retained prior run identifiers")
    return src

def apply(root:Path):
    proof=apply_v127(root)
    frontend=root.resolve()/"frontend/main.c"
    src=frontend.read_text()
    src=once(src,"\tint vh127_vblank_mode = -1;\n",
             "\tint vh127_vblank_mode = -1;\n"
             "\tint vh128_vblank_mode = -1;\n",
             "independent opt-in variable three-edge mode")
    anchor='\t\telse if (!strcmp(argv[i], "--vh127-vblank-00"))\n'
    flags="".join(
        f'\t\telse if (!strcmp(argv[i], "--vh128-vblank-{pair}"))\n'
        f'\t\t\tvh128_vblank_mode={i};\n'
        for i,pair in enumerate(SPLITS)
    )
    src=once(src,anchor,flags+anchor,
             "independently run 03, 12, 21 or 30 genuine VBlank gaps")
    _,stops,_,_,wait_pc=build()
    src=once(src,"\tif (loadst_f) {\n",
             oracle_source(stops,wait_pc)+"\tif (loadst_f) {\n",
             "native Unai triple-real-VBlank source-authored witness")
    frontend.write_text(src)
    return dict(proof,
        original_v127_four_mode_witness_preserved=True,
        v128_genuine_vblank_boundary_splits=list(SPLITS),
        triple_real_psxRcntUpdate_gpu_vblank_per_process=True,
        synthetic_psx_exe_bytecode_unchanged=True,
        original_retail_MAP02_verified=False,
        physical_PS1_verified=False,
        HD_replacement_approved=False)

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("checkout",type=Path)
    print(apply(p.parse_args().checkout))
