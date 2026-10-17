#!/usr/bin/env python3
"""Strict reconciliation: native 24-value exact equality by 0-4 VBlank gaps.

Raw pixels and private GPU journal are never written into public output.
"""
import argparse
import json
import re
from pathlib import Path
from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v114_vblank_readback_coverage import summarize as v114
from .summarize_map02_v115_identity_runtime import summarize as v115

FIELDS=("identical_24_values","different_24_values","different_delta_counts")
PATTERN=re.compile(
    r"^VH116_GAPS_PASS "+r" ".join(
        rf"g{i}=(\d+),(\d+),(\d+)" for i in range(5)
    )+r"$",re.MULTILINE,
)


def summarize(log: str,raw: bytes):
    records=PATTERN.findall(log)
    if len(records)!=1:
        raise Refused("expected exactly one complete native five-gap identity status")
    numbers=list(map(int,records[0]))
    if any(x>0xffffffff for x in numbers):
        raise Refused("v116 unsigned native bin out of bounds")
    rows=[dict(vblank_edges_between_handlers=i,
               **dict(zip(FIELDS,numbers[3*i:3*i+3]))) for i in range(5)]
    older=v115(log,raw)
    source=v114(raw)
    within=source["same_interval_readback_change_count_trends"]
    across=source["cross_vblank_readback_change_count_trends"]
    for i,row in enumerate(rows):
        equal=(sum(x["equal"] for x in within) if i==0 else
               sum(x["pairs"] for x in across
                   if x["vblank_edges_crossed"]==i and x["direction"]=="equal"))
        unequal=(sum(x["increasing"]+x["decreasing"] for x in within)
                 if i==0 else sum(x["pairs"] for x in across
                   if x["vblank_edges_crossed"]==i and x["direction"]!="equal"))
        if row["identical_24_values"]+row["different_24_values"]!=equal:
            raise Refused("native exact-value gap bin contradicts private equal-delta pairs")
        if row["different_delta_counts"]!=unequal:
            raise Refused("native changed-count gap bin contradicts private trend pairs")

    if (sum(r["identical_24_values"] for r in rows)!=
            older["equal_count_and_identical_sample_values"] or
        sum(r["different_24_values"] for r in rows)!=
            older["equal_count_but_different_sample_values"] or
        sum(r["different_delta_counts"] for r in rows)!=
            older["different_sample_change_count_pairs"] or
        sum(r["identical_24_values"] for r in rows[1:])!=
            older["cross_vblank_equal_count_and_identical_sample_values"] or
        sum(r["different_24_values"] for r in rows[1:])!=
            older["cross_vblank_equal_count_but_different_sample_values"] or
        sum(r["different_delta_counts"] for r in rows[1:])!=
            older["cross_vblank_different_sample_change_count_pairs"] or
        sum(sum(r[k] for k in FIELDS) for r in rows)!=
            older["adjacent_unai_pairs"]):
        raise Refused("native gap bins do not conserve verified v115 aggregates")
    return {
        "scope":"pinned_pcsx_synthetic_native_24_point_exact_value_gap_classes",
        "observed_unai_handlers":older["observed_unai_handlers"],
        "emulator_vblank_edges":4,
        "adjacent_observed_handler_pairs":older["adjacent_unai_pairs"],
        "native_exact_sample_value_bins_by_intervening_vblank_edges":rows,
        "bin_totals_checked_against_v114_and_v115":True,
        "actual_values_only_compared_inside_native_emulator":True,
        "pixel_values_or_hashes_exported":False,
        "host_callback_order_not_emulated_gpu_completion":True,
        "equal_24_selected_values_not_entire_vram":True,
        "cross_vblank_exact_sample_match_not_physical_frame_persistence":True,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_runtime_log",type=Path)
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        report=summarize(args.private_runtime_log.read_text(),
                         args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        parser.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
