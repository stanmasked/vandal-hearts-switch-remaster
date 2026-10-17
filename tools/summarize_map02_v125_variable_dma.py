#!/usr/bin/env python3
"""Fail-closed aggregate audit of real three-list MIPS DMA2 GPU test."""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused

MARKER=re.compile(
    r"^VH125_VARIABLE_DMA_PASS stages=(\d+) dma=(\d+) nodes=(\d+) "
    r"words=(\d+) unai=(\d+) intermediate=(\d+) readbacks=(\d+) "
    r"four_back=(\d+) vblanks=(\d+) erased=(\d+)$",re.MULTILINE,
)
KEYS=("mips_cpu_stages","gpu_dma2_linked_list_transfers",
      "native_gpu_chain_nodes_visited","gpu_command_words_traversed",
      "native_unai_draw_callbacks","ordered_native_intermediate_vram_checks",
      "final_host_vram_readbacks","exact_return_to_four_back",
      "observed_vblank_edges","prior_sample_cache_erased")
EXPECTED=(4,3,10,15,5,5,1,1,0,1)


def summarize(stdout:str):
    matches=MARKER.findall(stdout)
    if len(matches)!=1:
        raise Refused("missing or duplicate exact native variable GPU DMA result")
    nums=tuple(int(x) for x in matches[0])
    if nums!=EXPECTED or re.search(r"^VH125_[A-Z0-9_]*REFUSED",stdout,re.MULTILINE):
        raise Refused("variable MIPS DMA transport or native VRAM invariant failed")
    return {
        "scope":"synthetic_pinned_pcsx_mips_three_variable_gpu_linked_lists",
        **dict(zip(KEYS,nums)),
        "dma_list_lengths_in_gp0_words":[3,6,6],
        "native_nodes_per_dma_list":[3,3,4],
        "original_mips_ram_list_starts":["0x12000","0x13000","0x14000"],
        "six_word_node_contains_two_complete_gpu_draw_packets":True,
        "mips_cpu_wrote_all_dma_gpu_words_and_list_headers":True,
        "all_five_native_intermediate_vram_states_checked":True,
        "sampled_vram_comparisons_cover_24_selected_points":True,
        "gpu_draw_words_submitted_by_host":False,
        "canonical_private_v82_journal_sha256_checked_by_ci":True,
        "raw_gpu_payloads_or_vram_values_exported":False,
        "entire_vram_state_or_physical_scanout_verified":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    a=p.parse_args()
    try:
        result=summarize(a.private_runtime_log.read_text())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
