#!/usr/bin/env python3
"""Independent native-store versus sampled-VRAM-delta mismatch audit.

Only an opt-in pinned synthetic PCSX Unai trace is accepted. A 24-point
readback with zero changed points is NOT evidence of no VRAM writes.
No private pixels, GP0 words, addresses, CPU cycles or frames are emitted.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v109_gp0_class_vblank_stores import (
    CLASSES, classify, summarize as v109,
)
from .summarize_map02_v110_class_boundary_checkpoints import summarize as v110

CASES=(
    "unchanged_sample_no_instrumented_stores",
    "unchanged_sample_with_instrumented_stores",
    "changed_sample_no_instrumented_stores",
    "changed_sample_with_instrumented_stores",
)
COUNTS=("handlers","changed_sample_points","native_store_attempts",
        "same_value_native_stores","changed_value_native_stores")


def blank():
    return {field:0 for field in COUNTS}


def classify_case(sample_delta,store_attempts):
    return CASES[(2 if sample_delta else 0)+(1 if store_attempts else 0)]


def summarize(raw: bytes):
    audit=validate(raw)
    previous=v109(raw)
    boundaries=v110(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in rows if r["kind"]=="vblank"]
    if len(edges)!=4 or audit["vblank_edges"]!=4:
        raise Refused("required four observed emulator VBlank edges absent")

    intervals=[
        {"interval":reference["interval"],
         "classes":{klass:{case:blank() for case in CASES}
                    for klass in CLASSES}}
        for reference in previous["intervals"]
    ]
    collected=[]
    for index,event in enumerate(rows):
        if event["kind"]!="gp0_unai_handled":
            continue
        block=rows[index:index+4]
        if len(block)!=4 or [r["kind"] for r in block]!=[
            "gp0_unai_handled","unai_sample_delta",
            "unai_store_count","unai_same_store_count"
        ] or [r["seq"] for r in block]!=list(range(event["seq"],event["seq"]+4)):
            raise Refused("native Unai quartet missing or not sequential")
        ordinal=sum(event["seq"]>v for v in edges)
        if any(sum(x["seq"]>v for v in edges)!=ordinal for x in block):
            raise Refused("VBlank split one Unai observed handler")
        delta,stores,same=(block[1]["value"],block[2]["value"],block[3]["value"])
        if delta>24 or same>stores:
            raise Refused("invalid sampled VRAM or instrumented store count")
        klass=classify(event["value"])
        case=classify_case(delta,stores)
        counters=intervals[ordinal]["classes"][klass][case]
        counters["handlers"]+=1
        counters["changed_sample_points"]+=delta
        counters["native_store_attempts"]+=stores
        counters["same_value_native_stores"]+=same
        counters["changed_value_native_stores"]+=stores-same
        collected.append((event["seq"],klass,case,stores,same))

    totals={klass:{case:blank() for case in CASES} for klass in CLASSES}
    for i,entry in enumerate(intervals):
        for klass in CLASSES:
            reference=previous["intervals"][i]["classes"][klass]
            bycase=entry["classes"][klass]
            for field,sourcefield in (
                ("handlers","handlers"),
                ("changed_sample_points","changed_sample_points"),
                ("native_store_attempts","native_store_attempts"),
                ("same_value_native_stores","same_value_native_stores"),
                ("changed_value_native_stores","changed_value_native_stores"),
            ):
                actual=sum(c[field] for c in bycase.values())
                if actual!=reference[sourcefield]:
                    raise Refused("per-class/per-VBlank readback/store partition mismatch")
                for case in CASES:
                    totals[klass][case][field]+=bycase[case][field]
            # Case definitions themselves are independently checked.
            for case in CASES:
                stats=bycase[case]
                if case.startswith("unchanged") and stats["changed_sample_points"]:
                    raise Refused("unchanged samples misclassified")
                if case.endswith("no_instrumented_stores") and stats["native_store_attempts"]:
                    raise Refused("zero-store sample case had instrumented stores")
                if stats["native_store_attempts"]!=(
                    stats["same_value_native_stores"]+stats["changed_value_native_stores"]):
                    raise Refused("native 16-bit store accounting mismatch")

    snapshots=[]
    for i,edge in enumerate(edges):
        prefix={klass:{
            "unchanged_sample_with_instrumented_stores":0,
            "native_stores_with_unchanged_samples":0,
            "same_value_stores_with_unchanged_samples":0,
            "changed_value_stores_with_unchanged_samples":0,
        } for klass in CLASSES}
        for seq,klass,case,stores,same in collected:
            if seq>=edge or case!="unchanged_sample_with_instrumented_stores":
                continue
            counters=prefix[klass]
            counters["unchanged_sample_with_instrumented_stores"]+=1
            counters["native_stores_with_unchanged_samples"]+=stores
            counters["same_value_stores_with_unchanged_samples"]+=same
            counters["changed_value_stores_with_unchanged_samples"]+=stores-same
        for klass in CLASSES:
            expected=sum(
                intervals[b]["classes"][klass][
                    "unchanged_sample_with_instrumented_stores"]["native_store_attempts"]
                for b in range(i+1)
            )
            if prefix[klass]["native_stores_with_unchanged_samples"]!=expected:
                raise Refused("VBlank boundary missed sampled-unchanged stores")
            previous_stores=boundaries["snapshots_before_vblank"][i][
                "cumulative_by_class"][klass]["native_store_attempts"]
            if prefix[klass]["native_stores_with_unchanged_samples"]>previous_stores:
                raise Refused("sample-invisible store count exceeds native prefix")
        snapshots.append({"vblank_ordinal":i+1,
                          "sample_unchanged_with_stores_cumulative_by_class":prefix})

    overall={case:blank() for case in CASES}
    for klass in CLASSES:
        for case in CASES:
            for field in COUNTS:
                overall[case][field]+=totals[klass][case][field]
    if sum(x["handlers"] for x in overall.values())!=audit["gp0_unai_handled"]:
        raise Refused("Unai case partition does not conserve handlers")
    if sum(x["native_store_attempts"] for x in overall.values())!=sum(
        r["native_store_attempts"] for r in previous["class_totals"].values()
    ):
        raise Refused("native store attempts lost in sample/store classification")
    if sum(x["changed_sample_points"] for x in overall.values())!=sum(
        r["changed_sample_points"] for r in previous["class_totals"].values()
    ):
        raise Refused("observed sample changes lost in classification")

    return {
        "scope":"pinned_pcsx_synthetic_unai_sampled_VRAM_vs_native_stores",
        "vblank_edges":4,
        "sampled_vram_locations_per_handler":24,
        "case_definitions":list(CASES),
        "per_vblank_class_cases":intervals,
        "totals_by_class_and_case":totals,
        "overall_case_totals":overall,
        "before_vblank_cumulative_sample_unchanged_stores":snapshots,
        "zero_sample_delta_does_not_mean_no_VRAM_writes":True,
        "sample_change_without_instrumented_store_is_not_proof_of_no_write":True,
        "instrumented_sites_cover_all_vram_writes":False,
        "cpu_cycle_accurate_gpu_timing_verified":False,
        "original_retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        report=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        parser.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
