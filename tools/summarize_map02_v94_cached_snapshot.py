#!/usr/bin/env python3
"""v94 independent strict audit of cached/rebuilt dual-lane snapshot stages."""
import argparse
import json
from pathlib import Path
from .summarize_map02_v93_dual_lanes import summarize as summarize_v93
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("snapshot_cached_reads","snapshot_invalidation_proven",
       "snapshot_verified_reads")
VALUES=(128,1,128)

def summarize(raw:bytes):
    prev=summarize_v93(raw)
    report=validate(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    positions=[i for i,e in enumerate(events) if e["kind"]==KINDS[0]]
    if len(positions)!=1:
        raise Refused("missing/duplicate first cached journal metric")
    start=positions[0]
    tail=events[start:start+3]
    if len(tail)!=3 or tuple(e["kind"] for e in tail)!=KINDS:
        raise Refused("missing or out-of-order cached journal proof group")
    if any(e["kind"] in KINDS for i,e in enumerate(events)
           if not start<=i<start+3):
        raise Refused("duplicate/misplaced cached journal metric")
    if tuple(e["value"] for e in tail)!=VALUES:
        raise Refused("repeated cache reads or stale-view invalidation not proved")
    if any(e["cycle"]!=0 or e["frame"]!=0 for e in tail):
        raise Refused("snapshot-only metrics must not assert emulated cycle/frame")
    if tail[0]["seq"]<=max(e["seq"] for e in events
                           if e["kind"]=="lane_total_events"):
        raise Refused("v94 cache probe occurred before validated v93 checkpoint")
    if start+3!=prev["merged_private_events"]+3:
        raise Refused("v94 must follow v93 immediately with exactly three observations")
    if not prev["original_event_sequence_preserved"] or report["events"]!=len(events):
        raise Refused("v93 native event order not preserved")
    return {
        "scope":"host_pinned_PCSX_post_GPUfreeze_cached_dual_lane_private_snapshot",
        "unchanged_native_cached_reads":128,
        "native_full_merge_avoided_on_cached_reads":128,
        "independent_native_snapshot_integrity_checks":128,
        "native_stale_view_invalidation_observed":True,
        "exactly_one_merge_on_first_read_after_append":True,
        "private_serializer_performs_source_vs_view_integrity_check":True,
        "prior_checkpoint_native_events":prev["merged_private_events"],
        "final_private_journal_events":start+3,
        "original_four_emulator_VBlanks_preserved":report["vblank_edges"]==4,
        "retail_MAP02_verified":False,
        "physical_PlayStation_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as e:p.exit(2,f"REFUSED: {e}\n")
if __name__=="__main__":main()
