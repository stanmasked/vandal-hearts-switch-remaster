#!/usr/bin/env python3
"""Audit v93 separated native detailed/aggregate rings and exact old ordering.

The C observer physically separates records, but their unique global event
sequence, byte-exact private JSONL and original v80-v92 evidence survive.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v92_queue_pressure import summarize as summarize_v92
from .verify_map02_v82_native_trace import Refused,validate

KINDS=("lane_detail_events","lane_aggregate_events","lane_total_events")
DETAIL_TYPES={
    "vblank","gp1_mmio","gpu_dma2_start",
    "gp0_unai_handled","unai_sample_delta",
    "unai_store_count","unai_same_store_count",
}
DETAIL_CAPACITY=4096
AGGREGATE_CAPACITY=256

def summarize(raw:bytes):
    previous=summarize_v92(raw)
    report=validate(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    starts=[i for i,row in enumerate(rows) if row["kind"]==KINDS[0]]
    if len(starts)!=1:
        raise Refused("missing/duplicate v93 detailed lane metric")
    start=starts[0]
    group=rows[start:start+3]
    if len(group)!=3 or tuple(row["kind"] for row in group)!=KINDS:
        raise Refused("missing/out-of-order v93 separated lane proof")
    if any(row["kind"] in KINDS for i,row in enumerate(rows)
           if not start<=i<start+3):
        raise Refused("duplicate native lane counters")
    checkpoint=rows[:start+3]
    detail,agg,total=(row["value"] for row in group)
    counted_detail=sum(row["kind"] in DETAIL_TYPES for row in checkpoint)
    counted_aggregate=len(checkpoint)-counted_detail
    if detail!=counted_detail or agg!=counted_aggregate:
        raise Refused("reported lane capacity disagrees with actual native event types")
    if total!=len(checkpoint) or total!=detail+agg or report["events"]!=len(rows):
        raise Refused("globally ordered event count differs from independent lane totals")
    if not (0<detail<=DETAIL_CAPACITY and 3<=agg<=AGGREGATE_CAPACITY
            and DETAIL_CAPACITY<total<=DETAIL_CAPACITY+AGGREGATE_CAPACITY):
        raise Refused("v93 did not demonstrate legitimate combined >4096 events")
    if any(row["cycle"]!=0 or row["frame"]!=0 for row in group):
        raise Refused("host-only lane counters cannot claim MIPS CPU/frame ownership")
    if group[0]["seq"]<=max(row["seq"] for row in rows
                            if row["kind"]=="pressure_sync_same"):
        raise Refused("v93 capacity audit preceded real v92 GPU queue drain")
    if not previous["all_host_16bit_assignments_verified"]:
        raise Refused("v92 worker/sync pixel observation incomplete")
    return {
        "provenance":"synthetic_native_pinned_PCSX_private_dual_lane_journal",
        "detailed_renderer_lane_events":detail,
        "GPU_aggregate_lane_events":agg,
        "merged_private_events":total,
        "detailed_renderer_lane_capacity":DETAIL_CAPACITY,
        "GPU_aggregate_lane_capacity":AGGREGATE_CAPACITY,
        "combined_lane_capacity":DETAIL_CAPACITY+AGGREGATE_CAPACITY,
        "old_total_4096_event_limit_exceeded_without_drop":total>4096,
        "original_event_sequence_preserved":True,
        "private_byte_exact_journal_required":True,
        "v92_worker_fallback_stores_verified":True,
        "genuine_retail_MAP02_verified":False,
        "physical_playstation_verified":False,
        "HD_replacement_approved":False
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("private_jsonl",type=Path)
    args=ap.parse_args()
    try:r=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as e:
        ap.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(r,sort_keys=True))
if __name__=="__main__":main()
