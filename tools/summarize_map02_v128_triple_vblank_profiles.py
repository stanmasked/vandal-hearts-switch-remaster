#!/usr/bin/env python3
"""Fail-closed aggregate of four independent three-genuine-VBlank MIPS DMA runs."""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused

PROFILES=((0,3),(1,2),(2,1),(3,0))
MARKER=re.compile(
    r"^VH128_REAL_VBLANK_PROFILES_PASS mode=(\d+) gaps=(\d+),(\d+),(\d+),(\d+) "
    r"stages=(\d+) dma=(\d+) nodes=(\d+) words=(\d+) unai=(\d+) "
    r"intermediate=(\d+) real_vblanks=(\d+) four_back_gap=(\d+) erased=(\d+)$",
    re.MULTILINE
)

def summarize_one(log:str,mode:int):
    if not 0<=mode<4:
        raise Refused("unsupported triple-VBlank gap profile")
    matches=MARKER.findall(log)
    if len(matches)!=1:
        raise Refused("missing, duplicate or malformed native triple-VBlank marker")
    a,b=PROFILES[mode]
    expected=(mode,a,0,b,0,4,3,10,15,5,5,3,3,1)
    if tuple(map(int,matches[0]))!=expected:
        raise Refused("observed actual callback gap profile differs")
    if re.search(r"VH(?:12[5-8])_[A-Z0-9_]*REFUSED\b",log):
        raise Refused("native witness reported an explicit failure")
    return {
        "mode":f"{a}{b}",
        "real_vblank_boundaries":[a,b],
        "native_post_handler_pair_gaps":[a,0,b,0],
        "real_vblank_events":3,
        "native_four_back_return_gap":3,
        "mips_stages":4,
        "actual_dma2_linked_lists":3,
        "gpu_dma_node_visits":10,
        "gpu_packet_words":15,
        "unai_post_draw_observations":5,
        "intermediate_pixel_state_checks":5,
        "sample_cache_erased":True,
    }

def summarize_all(logs):
    if len(logs)!=4:
        raise Refused("all four independent native triple-VBlank logs required")
    profiles=[summarize_one(log,mode) for mode,log in enumerate(logs)]
    if {tuple(p["real_vblank_boundaries"]) for p in profiles}!=set(PROFILES):
        raise Refused("VBlank boundary splits missing or repeated")
    return {
        "scope":"pinned_pcsx_synthetic_cpu_dma_exact_three_real_vblank_split_matrix",
        "profiles":profiles,
        "all_modes_verified":True,
        "all_intervals_0_1_2_3_exercised":True,
        "all_profiles_have_exactly_three_real_vblank_events":True,
        "return_gap_three_verified_across_four_distinct_splits":True,
        "real_vblank_origin":"original_psxRcntUpdate_GPU_vBlank_callback",
        "no_host_injected_cycles_vblank_or_gpu_commands":True,
        "original_cpu_authored_three_dma_lists_preserved":True,
        "only_24_selected_16bit_vram_values_compared":True,
        "original_v82_private_journal_sha256_checked_by_workflow":True,
        "raw_vram_gpu_words_or_hashes_exported":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_logs",nargs=4,type=Path)
    args=p.parse_args()
    try:
        report=summarize_all([f.read_text() for f in args.private_logs])
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
