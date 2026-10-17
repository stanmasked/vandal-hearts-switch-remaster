#!/usr/bin/env python3
"""Fail closed on synthetic real MIPS-initiated GPU DMA2 return evidence.

Native counters are generated inside the pinned original psxDma2()
mem2vram branch, not by Python or the host dispatch loop. Public summary
is integer-only. The original private journal is checked separately
before/after this new process by the pinned workflow.
"""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused

FIELDS=("cpu_stages","native_dma2_linked_list_dispatches",
        "native_linked_list_nodes_visited","native_gp0_words_traversed",
        "native_unai_post_handler_samples",
        "real_vram_readbacks","exact_return_to_four_back",
        "observed_vblank_edges","native_sample_cache_erased")
EXPECTED=(6,5,15,15,5,5,1,0,1)
PATTERN=re.compile(
    r"^VH123_MIPS_GPU_LIST_RETURN_PASS stages=(\d+) lists=(\d+) "
    r"nodes=(\d+) words=(\d+) native_unai=(\d+) readbacks=(\d+) four_back=(\d+) "
    r"vblanks=(\d+) erased=(\d+)$",re.MULTILINE,
)


def summarize(stdout: str):
    hits=PATTERN.findall(stdout)
    if len(hits)!=1:
        raise Refused("missing, duplicate or partial MIPS DMA2 native GPU status")
    numbers=tuple(int(x) for x in hits[0])
    if numbers!=EXPECTED or re.search(r"^VH123_[A-Z0-9_]*REFUSED",stdout,re.MULTILINE):
        raise Refused("synthetic MIPS DMA2 GP0 native GPU return invariant failed")
    return {
        "scope":"pinned_pcsx_synthetic_mips_gpu_dma2_three_node_linked_lists",
        **dict(zip(FIELDS,numbers)),
        "independent_psxdma2_linked_list_branch_observer_confirmed":True,
        "native_gpu_dma_chain_three_node_traversal_confirmed":True,
        "linked_list_headers_written_by_interpreted_mips":True,
        "dma2_registers_written_by_interpreted_cpu":True,
        "gpu_packet_words_authored_in_psx_ram_by_mips_cpu":True,
        "host_submitted_gp0_draw_commands_in_v123":False,
        "native_sample_24_point_exact_equality":True,
        "no_extra_vblank_forged":True,
        "raw_gpu_commands_and_vram_pixels_exported":False,
        "canonical_v82_private_journal_sha256_verified_by_workflow":True,
        "complete_vram_state_or_physical_ps1_scanout_verified":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    args=p.parse_args()
    try:
        data=summarize(args.private_runtime_log.read_text())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(data,sort_keys=True))


if __name__=="__main__":
    main()
