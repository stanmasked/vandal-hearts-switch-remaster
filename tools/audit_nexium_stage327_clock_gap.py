#!/usr/bin/env python3
"""Stage327: quantify wall-vs-monotonic interval disagreement on proven Stage326 source.

A diagnostic only. A host wall-clock jump can go undetected by a strictly
increasing Stage304 epoch, so contrast the already authenticated host clock
intervals WITHOUT changing any original strict verifier. This is not an
audio latency or guest clock measurement.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from audit_nexium_host_clock_pairs import ClockPairError

SCHEMA="vh-stage327-host-clock-interval-disagreement/v1"
STAGE326_RESULT="TWO_DISTINCT_ORIGINAL_NEXIUM_HOST_CLOCK_COHORTS_REPLAYED"
STAGE326_SCHEMA="vh-stage326-original-neXium-two-cohort-host-clock-comparison/v1"
THRESHOLD_NS=1_000_000  # Diagnostic heuristic only; not a physical bound.
EVENTS=("before_plus_down","after_plus_up","control_sequence_end")


def audit_stage326_clock_disagreement(original:dict)->dict:
    if (not isinstance(original,dict)
            or original.get("schema")!=STAGE326_SCHEMA
            or original.get("result")!=STAGE326_RESULT
            or original.get("each_original_stage325_receipt_recomputed_from_original_csv") is not True
            or original.get("each_original_stage304_host_controls_matched_strict_receipt") is not True
            or original.get("each_original_stage305_success_receipt_present") is not True
            or original.get("entire_stage304_or_stage305_pcm_chain_independently_rerun") is not False
            or original.get("guest_to_host_clock_alignment_proven") is not False
            or original.get("sound_latency_or_dropout_verified") is not False
            or original.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ClockPairError("Stage326 original source verdict or evidence scope incomplete")
    pins=[]
    for key in ("first_source_sha256","second_source_sha256"):
        obj=original.get(key)
        if not isinstance(obj,dict) or set(obj)!={"legacy","monotonic"}:
            raise ClockPairError("incomplete original host CSV source pins")
        values=(obj["legacy"],obj["monotonic"])
        if not all(isinstance(v,str) and re.fullmatch(r"[0-9a-f]{64}",v)
                   for v in values):
            raise ClockPairError("malformed original host CSV source pin")
        pins.append(values)
    if pins[0]==pins[1]:
        raise ClockPairError("Stage326 source cohorts not distinct")
    rows=original.get("original_control_pair_comparison")
    if not isinstance(rows,list) or len(rows)!=2:
        raise ClockPairError("expected two original host control intervals")
    out=[]
    for index,row in enumerate(rows):
        if not isinstance(row,dict):
            raise ClockPairError("nonobject original Stage326 interval")
        if (row.get("first_event")!=EVENTS[index] or
                row.get("second_event")!=EVENTS[index+1]):
            raise ClockPairError("original Stage326 event order changed")
        numbers=(
            "first_wall_delta_ms","second_wall_delta_ms",
            "first_monotonic_delta_ns","second_monotonic_delta_ns",
            "first_pcm_file_size_delta_bytes","second_pcm_file_size_delta_bytes",
            "second_minus_first_wall_delta_ms",
            "second_minus_first_monotonic_delta_ns",
        )
        if any(type(row.get(name)) is not int for name in numbers):
            raise ClockPairError("noninteger original Stage326 host interval")
        if any(row[k]<=0 for k in numbers[:6]):
            raise ClockPairError("original successful cohort host interval not positive")
        if (row["second_minus_first_wall_delta_ms"]!=
                row["second_wall_delta_ms"]-row["first_wall_delta_ms"] or
                row["second_minus_first_monotonic_delta_ns"]!=
                row["second_monotonic_delta_ns"]-row["first_monotonic_delta_ns"]):
            raise ClockPairError("original Stage326 host interval difference changed")
        first=row["first_wall_delta_ms"]*1_000_000-row["first_monotonic_delta_ns"]
        second=row["second_wall_delta_ms"]*1_000_000-row["second_monotonic_delta_ns"]
        out.append({
            "first_event":EVENTS[index],
            "second_event":EVENTS[index+1],
            "first_host_wall_minus_monotonic_interval_ns":first,
            "second_host_wall_minus_monotonic_interval_ns":second,
            "second_minus_first_discrepancy_ns":second-first,
            "first_exceeds_illustrative_one_ms_gap":abs(first)>THRESHOLD_NS,
            "second_exceeds_illustrative_one_ms_gap":abs(second)>THRESHOLD_NS,
        })
    return {
        "schema":SCHEMA,
        "result":"STAGE327_TWO_ORIGINAL_HOST_CLOCK_INTERVAL_GAPS_CLASSIFIED",
        "first_source_sha256":{"legacy":pins[0][0],"monotonic":pins[0][1]},
        "second_source_sha256":{"legacy":pins[1][0],"monotonic":pins[1][1]},
        "interval_disagreements":out,
        "diagnostic_one_ms_threshold_ns":THRESHOLD_NS,
        "one_ms_threshold_is_heuristic_not_guaranteed_sampling_bound":True,
        "all_original_stage326_source_scope_flags_conserved":True,
        "absolute_host_wall_epochs_exposed":False,
        "guest_audio_timing_or_clock_causality_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage326",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        if (a.stage326.is_symlink() or not a.stage326.is_file() or
                a.stage326.stat().st_size>100_000):
            raise ClockPairError("missing, symlinked or oversized original Stage326 receipt")
        if a.output.exists() or a.output.is_symlink():
            raise ClockPairError("refuse overwrite Stage327 result")
        original=json.loads(a.stage326.read_text(encoding="utf-8"))
        derived=audit_stage326_clock_disagreement(original)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(derived,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":derived["result"],
            "host_clock_interval_gaps":derived["interval_disagreements"],
            "physical_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({
            "result":"STAGE327_HOST_CLOCK_INTERVAL_GAPS_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_tested":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
