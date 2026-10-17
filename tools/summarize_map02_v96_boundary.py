#!/usr/bin/env python3
"""Strict v96 native GPU two-lane remaining capacity and stable export audit.

The live pinned PCSX smoke remains publishable (zero dropped). Actual
overflow is exercised in isolated native C ABI tests, where refusal
must not alter any previously verified event bytes or sequence.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v95_roundtrip import summarize as summarize_v95
from .summarize_map02_v93_dual_lanes import DETAIL_TYPES
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("boundary_detail_remaining","boundary_aggregate_remaining",
       "boundary_identical_serializations")
DETAIL_CAPACITY=4096
AGG_CAPACITY=256

def summarize(raw:bytes):
    previous=summarize_v95(raw)
    validated=validate(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    tail=rows[-3:]
    if len(tail)!=3 or tuple(row["kind"] for row in tail)!=KINDS:
        raise Refused("missing/out-of-order native near-boundary capacity suffix")
    if any(row["kind"] in KINDS for row in rows[:-3]):
        raise Refused("duplicate or misplaced native near-capacity metric")
    if any(row["cycle"]!=0 or row["frame"]!=0 for row in tail):
        raise Refused("host-only capacity metrics cannot claim CPU/VBlank timestamps")
    if tail[0]["seq"]!=previous["final_private_journal_events"]+1:
        raise Refused("v96 capacity report must follow v95 snapshot checkpoint exactly")
    if len(rows)!=previous["final_private_journal_events"]+3:
        raise Refused("unexpected records inserted around v96 capacity audit")
    detail_used=sum(row["kind"] in DETAIL_TYPES for row in rows)
    agg_used=len(rows)-detail_used
    expected_detail=DETAIL_CAPACITY-detail_used
    expected_agg=AGG_CAPACITY-agg_used
    if not (0<expected_detail<=256 and 0<expected_agg<AGG_CAPACITY):
        raise Refused("native v96 fixture did not approach capacity safely")
    if (tail[0]["value"],tail[1]["value"],tail[2]["value"])!=(
        expected_detail,expected_agg,2):
        raise Refused("recorded remaining slots differ from real private event classes")
    if validated["events"]!=len(rows) or validated["vblank_edges"]!=4:
        raise Refused("private export does not match observed original MIPS oracle")
    return {
        "provenance":"post_GPUfreeze_native_pinned_PCSX_dual_lane_checkpoint",
        "native_detailed_lane_remaining":expected_detail,
        "native_aggregate_lane_remaining":expected_agg,
        "native_detailed_lane_capacity":DETAIL_CAPACITY,
        "native_aggregate_lane_capacity":AGG_CAPACITY,
        "native_successful_replayed_serializations":2,
        "verified_prior_bytes_preserved_in_native_C":True,
        "preceding_snapshot_events":previous["final_private_journal_events"],
        "private_events":len(rows),
        "native_overcapacity_must_fail_closed_in_isolated_C_tests":True,
        "real_retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: result=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__": main()
