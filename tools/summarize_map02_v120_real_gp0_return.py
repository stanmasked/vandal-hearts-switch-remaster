#!/usr/bin/env python3
"""Verify a separate real pinned-Unai host-GP0 return from private stdout.

The v120 fixture executes *after* original v82 JSONL publication. The
original full native journal is independently revalidated against v119;
the new five rectangle callbacks are NOT attributed to that journal.
"""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v119_quintuplet_runtime import summarize as v119

MARKER=re.compile(
    r"^VH120_GP0_RETURN_PASS commands=(\d+) native_handlers=(\d+) "
    r"exact_four_back=(\d+) readbacks=(\d+) erased=(\d+) vblanks=(\d+)$",
    re.MULTILINE,
)


def summarize(log: str,raw: bytes):
    observed=MARKER.findall(log)
    if len(observed)!=1:
        raise Refused("missing, duplicate or incomplete actual host GPU return proof")
    fields=("commands","native_handlers","exact_four_back",
            "readbacks","erased","vblanks")
    counts=dict(zip(fields,map(int,observed[0])))
    if counts!=dict(commands=5,native_handlers=5,exact_four_back=1,
                    readbacks=5,erased=1,vblanks=0):
        raise Refused("native GPU fixture did not produce required actual A-B-C-D-A return")
    if re.search(r"VH120_[A-Z_]+REFUSED",log):
        raise Refused("native GPU fixture explicitly refused")
    previous=v119(log,raw)
    if previous["native_five_callback_windows"]!=1003 or (
        previous["observed_unai_handlers"]!=1007
    ):
        raise Refused("original canonical pinned synthetic Unai journal changed")
    return {
        "scope":"pinned_pcsx_unai_separate_host_gp0_sampled_vram_return_fixture",
        "native_gp0_commands_submitted_by_host":counts["commands"],
        "native_unai_post_handler_samples":counts["native_handlers"],
        "real_native_vram_freeze_readbacks":counts["readbacks"],
        "exact_four_back_returns_observed":counts["exact_four_back"],
        "native_previous_value_buffers_erased":bool(counts["erased"]),
        "vblank_events_during_separate_fixture":counts["vblanks"],
        "original_v119_canonical_journal_revalidated":True,
        "v120_commands_occur_after_canonical_private_journal_published":True,
        "the_commands_were_not_executed_by_interpreted_mips":True,
        "synthetic_fixture_uses_no_retail_game_content":True,
        "only_24_selected_16bit_vram_locations_compared":True,
        "complete_vram_return_or_physical_frame_verified":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_runtime_log",type=Path)
    parser.add_argument("original_private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        report=summarize(args.private_runtime_log.read_text(),
                         args.original_private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        parser.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
