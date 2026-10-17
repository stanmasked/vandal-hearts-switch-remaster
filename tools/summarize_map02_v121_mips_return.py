#!/usr/bin/env python3
"""Validate a separate MIPS-authored native Unai return smoke output.

The pinned PCSX run executes an original synthetic PS-X EXE with five
interpreted CPU GP0 stores (3 words each), not the host-submitted v120
control. The canonical v82 journal is independently preserved by a
byte-exact SHA-256 check in the workflow and never reinterpreted here.
"""
import argparse
import json
import re
from pathlib import Path

from .verify_map02_v82_native_trace import Refused

MARKER=re.compile(
    r"^VH121_MIPS_GP0_RETURN_PASS stages=(\d+) mips_rectangles=(\d+) "
    r"native_unai=(\d+) readbacks=(\d+) four_back=(\d+) "
    r"vblanks=(\d+) erased=(\d+)$",re.MULTILINE,
)
FIELDS=("cpu_stages","mips_gp0_rectangles","native_unai_handlers",
        "native_vram_readbacks","exact_four_back_returns",
        "observed_vblank_edges","native_previous_values_erased")
EXPECTED=(6,5,5,5,1,0,1)


def summarize(stdout: str):
    results=MARKER.findall(stdout)
    if len(results)!=1:
        raise Refused("missing, duplicate or malformed MIPS-authored Unai return result")
    got=tuple(map(int,results[0]))
    if got!=EXPECTED or re.search(r"^VH121_[A-Z0-9_]*REFUSED",stdout,re.MULTILINE):
        raise Refused("MIPS CPU/GPU diagnostic failed invariant")
    return {
        "scope":"pinned_pcsx_interpreted_original_synthetic_mips_cpu_gp0",
        **dict(zip(FIELDS,got)),
        "mips_store_to_gp0_executed_in_emulator":True,
        "host_submitted_gpu_draw_commands_in_this_run":False,
        "original_v120_host_draw_fixture_separate":True,
        "original_v82_private_journal_byte_exact_preserved_by_workflow":True,
        "exact_return_only_24_selected_16bit_vram_values":True,
        "raw_pixel_values_and_hashes_exported":False,
        "hardware_ps1_scanout_or_gpu_cycle_verified":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    args=p.parse_args()
    try:
        result=summarize(args.private_runtime_log.read_text())
    except (UnicodeError,OSError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
