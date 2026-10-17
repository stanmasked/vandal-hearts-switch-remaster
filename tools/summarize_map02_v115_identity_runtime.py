#!/usr/bin/env python3
"""Bind private native exact-24-value observer counters to v114 JSONL event counts.

Never receive actual sampled pixel values or a snapshot hash. Only the native
process compares those 24 exact 16-bit values. Host stdout has counters only.
"""
import argparse
import json
import re
from pathlib import Path

from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v114_vblank_readback_coverage import summarize as v114

PATTERN=re.compile(
    r"^VH115_SAMPLE_IDENTITY_PASS handlers=(\d+) vblanks=(\d+) "
    r"identical_count_equal_values=(\d+) identical_count_different_values=(\d+) "
    r"different_count=(\d+) cross_equal_values=(\d+) "
    r"cross_different_values=(\d+) cross_different_count=(\d+)$",
    flags=re.MULTILINE,
)
KEYS=(
    "handlers","vblanks","equal_count_identical_values",
    "equal_count_different_values","different_count",
    "cross_equal_count_identical_values","cross_equal_count_different_values",
    "cross_different_count",
)


def summarize(log: str,raw: bytes):
    match=PATTERN.findall(log)
    if len(match)!=1:
        raise Refused("expected exactly one complete private native identity result")
    metrics=dict(zip(KEYS,map(int,match[0])))
    if any(v>0xffffffff for v in metrics.values()):
        raise Refused("native identity metrics out of unsigned 32-bit range")
    prior=v114(raw)
    handlers=prior["observed_unai_handlers"]
    if metrics["handlers"]!=handlers or metrics["vblanks"]!=4 or handlers<1:
        raise Refused("native observer not bound to canonical Unai/VBlank events")

    same_interval=prior["same_interval_readback_change_count_trends"]
    crossed=prior["cross_vblank_readback_change_count_trends"]
    within_equal=sum(item["equal"] for item in same_interval)
    across_equal=sum(item["pairs"] for item in crossed
                     if item["direction"]=="equal")
    across_other=sum(item["pairs"] for item in crossed
                     if item["direction"]!="equal")
    same_delta_pairs=within_equal+across_equal
    different_delta_pairs=handlers-1-same_delta_pairs
    if (metrics["equal_count_identical_values"]+
            metrics["equal_count_different_values"]!=same_delta_pairs or
        metrics["different_count"]!=different_delta_pairs or
        metrics["cross_equal_count_identical_values"]+
            metrics["cross_equal_count_different_values"]!=across_equal or
        metrics["cross_different_count"]!=across_other or
        metrics["cross_equal_count_identical_values"]>
            metrics["equal_count_identical_values"] or
        metrics["cross_equal_count_different_values"]>
            metrics["equal_count_different_values"]):
        raise Refused("native exact-value classes disagree with independently verified readback counts")
    if sum(item["adjacent_pairs"] for item in
           prior["same_interval_readback_change_count_trends"]
           if "adjacent_pairs" in item):  # no such field in v114; count from trends
        raise Refused("unexpected v114 trend schema")
    return {
        "scope":"pinned_pcsx_synthetic_exact_24_sample_value_identity_native_only",
        "observed_unai_handlers":handlers,
        "emulator_vblank_edges":4,
        "adjacent_unai_pairs":handlers-1,
        "equal_sample_change_count_pairs":same_delta_pairs,
        "equal_count_and_identical_sample_values":
            metrics["equal_count_identical_values"],
        "equal_count_but_different_sample_values":
            metrics["equal_count_different_values"],
        "different_sample_change_count_pairs":different_delta_pairs,
        "cross_vblank_equal_count_and_identical_sample_values":
            metrics["cross_equal_count_identical_values"],
        "cross_vblank_equal_count_but_different_sample_values":
            metrics["cross_equal_count_different_values"],
        "cross_vblank_different_sample_change_count_pairs":
            metrics["cross_different_count"],
        "actual_24_post_handler_16bit_values_compared_in_native_process":True,
        "raw_values_or_pixel_hash_exported":False,
        "same_changed_count_never_assumed_sample_identity":True,
        "only_24_selected_locations_observed":True,
        "full_vram_persistence_proven":False,
        "physical_ps1_vblank_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:
        report=summarize(args.private_runtime_log.read_text(),
                         args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
