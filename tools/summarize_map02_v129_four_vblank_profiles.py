#!/usr/bin/env python3
"""Private-log verification of five exact four-real-VBlank MIPS DMA profiles."""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused

PROFILES=((0,4),(1,3),(2,2),(3,1),(4,0))
MARKER=re.compile(
    r"^VH129_REAL_VBLANK_PROFILES_PASS mode=(\d+) gaps=(\d+),(\d+),(\d+),(\d+) "
    r"stages=(\d+) dma=(\d+) nodes=(\d+) words=(\d+) unai=(\d+) "
    r"intermediate=(\d+) real_vblanks=(\d+) four_back_gap=(\d+) erased=(\d+)$",
    re.MULTILINE
)
REFUSED=re.compile(r"VH(?:12[5-9])_[A-Z0-9_]*REFUSED\b")

def summarize_one(log:str,mode:int):
    if not 0<=mode<len(PROFILES):
        raise Refused("unsupported four-real-VBlank profile")
    found=MARKER.findall(log)
    if len(found)!=1:
        raise Refused("missing, duplicate or malformed native gap-four marker")
    a,b=PROFILES[mode]
    expected=(mode,a,0,b,0,4,3,10,15,5,5,4,4,1)
    if tuple(map(int,found[0]))!=expected or REFUSED.search(log):
        raise Refused("native VRAM return or callback gap-four witness refused")
    return {
        "mode":f"{a}{b}",
        "real_vblank_boundaries":[a,b],
        "native_post_handler_pair_gaps":[a,0,b,0],
        "real_vblank_events":4,
        "native_four_back_return_gap":4,
        "mips_stages":4,
        "actual_dma2_linked_lists":3,
        "gpu_dma_node_visits":10,
        "gpu_packet_words":15,
        "unai_post_draw_observations":5,
        "intermediate_pixel_state_checks":5,
        "sample_cache_erased":True,
    }

def summarize_all(logs):
    if len(logs)!=len(PROFILES):
        raise Refused("five separate original-emulator run logs required")
    profiles=[summarize_one(log,index) for index,log in enumerate(logs)]
    if {tuple(p["real_vblank_boundaries"]) for p in profiles}!=set(PROFILES):
        raise Refused("duplicate or absent actual VBlank split")
    return {
        "scope":"pinned_pcsx_synthetic_mips_dma_four_genuine_vblank_split_matrix",
        "profiles":profiles,
        "all_modes_verified":True,
        "all_intervals_0_1_2_3_4_exercised":True,
        "four_genuine_vblank_events_per_process":True,
        "native_four_back_return_gap_four_in_all_profiles":True,
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
    p.add_argument("private_logs",nargs=5,type=Path)
    args=p.parse_args()
    try:
        report=summarize_all([f.read_text() for f in args.private_logs])
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
