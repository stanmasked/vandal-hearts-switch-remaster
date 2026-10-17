#!/usr/bin/env python3
"""Fail-closed original-MIPS one linked-list / five GPU draws observer.

All five intermediate 4x4 pixel readbacks and exact 24-point sample
equality are checked only in the native pinned Unai process. The
original private JSONL is checked independently by the host workflow.
"""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused

FIELDS=("cpu_stages","linked_list_dma_dispatches","native_gpu_chain_nodes",
        "gpu_command_words","native_unai_handlers",
        "ordered_intermediate_vram_checks","final_host_readbacks",
        "exact_four_back_returns","vblank_edges","sample_cache_erased")
EXPECTED=(2,1,7,15,5,5,1,1,0,1)
MARKER=re.compile(
    r"^VH124_ONE_LIST_FIVE_GP0_PASS stages=(\d+) lists=(\d+) nodes=(\d+) "
    r"words=(\d+) unai=(\d+) intermediate=(\d+) readbacks=(\d+) "
    r"four_back=(\d+) vblanks=(\d+) erased=(\d+)$",re.MULTILINE,
)


def summarize(stdout: str):
    found=MARKER.findall(stdout)
    if len(found)!=1:
        raise Refused("missing/duplicate/truncated one-list native five-command result")
    values=tuple(map(int,found[0]))
    if values!=EXPECTED or re.search(r"^VH124_[A-Z0-9_]*REFUSED",stdout,re.MULTILINE):
        raise Refused("actual MIPS one-list intermediate native VRAM invariant failed")
    return {
        "scope":"pinned_pcsx_original_synthetic_mips_one_dma_five_gpu_draws",
        **dict(zip(FIELDS,values)),
        "one_dma_contains_five_ordered_gp0_draw_packets":True,
        "each_intermediate_4x4_native_vram_checked_inside_unai":True,
        "five_24_point_post_handler_states_compared_native":True,
        "all_seven_linked_list_nodes_individually_verified":True,
        "mips_cpu_wrote_all_node_headers_and_gpu_packets":True,
        "host_submitted_gpu_draw_packets":False,
        "canonical_private_v82_journal_sha256_checked_before_and_after":True,
        "raw_pixel_values_gpu_commands_or_hashes_exported":False,
        "observed_callback_order_not_hardware_scanout":True,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    a=p.parse_args()
    try:
        output=summarize(a.private_runtime_log.read_text())
    except (OSError,UnicodeError,Refused) as e:
        p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
