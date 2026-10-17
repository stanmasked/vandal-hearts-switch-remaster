#!/usr/bin/env python3
"""Run-length/edge-conservation audit for native Unai writes with zero sample delta.

Private pinned synthetic PCSX trace only. A zero delta on the 24 sampled
locations does NOT assert unchanged whole VRAM or non-completion of a command.
The only chronology is host observer append order, never emulated CPU cycles.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v109_gp0_class_vblank_stores import CLASSES, classify
from .summarize_map02_v110_class_boundary_checkpoints import summarize as v110
from .summarize_map02_v111_sample_store_divergence import summarize as v111

ELIGIBLE="unchanged_sample_with_instrumented_stores"
FIELDS=("handlers","native_store_attempts","same_value_native_stores",
        "changed_value_native_stores")


def _blank():
    return {k:0 for k in FIELDS}


def summarize(raw: bytes):
    validate(raw)
    preceding=v111(raw)
    native_boundaries=v110(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[item["seq"] for item in rows if item["kind"]=="vblank"]
    if len(edges)!=4:
        raise Refused("expected four recorded VBlank edges")

    handlers=[]
    for idx,row in enumerate(rows):
        if row["kind"]!="gp0_unai_handled":
            continue
        block=rows[idx:idx+4]
        if len(block)!=4 or [r["kind"] for r in block]!=[
            "gp0_unai_handled","unai_sample_delta",
            "unai_store_count","unai_same_store_count"
        ] or [r["seq"] for r in block]!=list(range(row["seq"],row["seq"]+4)):
            raise Refused("incomplete Unai handler sample/store group")
        bucket=sum(row["seq"]>edge for edge in edges)
        if any(sum(r["seq"]>edge for edge in edges)!=bucket for r in block):
            raise Refused("VBlank splits an indivisible Unai readback")
        sample,stores,same=block[1]["value"],block[2]["value"],block[3]["value"]
        if sample>24 or same>stores:
            raise Refused("invalid instrumented native store or sample count")
        handlers.append({
            "seq":row["seq"],"bucket":bucket,"class":classify(row["value"]),
            "eligible":sample==0 and stores>0,"stores":stores,"same":same,
        })

    # Runs are consecutive *observed Unai handlers* (one 4-record quartet
    # each), not uninterrupted machine execution. VBlank and GP1 input
    # records can occur between adjacent observed handlers.
    runs=[]
    current=[]
    for handler in handlers:
        if not handler["eligible"]:
            if current:
                runs.append(current)
                current=[]
        else:
            current.append(handler)
    if current:
        runs.append(current)

    totals_by_bucket=[
        {klass:_blank() for klass in CLASSES} for _ in range(5)
    ]
    for handler in handlers:
        if not handler["eligible"]:
            continue
        item=totals_by_bucket[handler["bucket"]][handler["class"]]
        item["handlers"]+=1
        item["native_store_attempts"]+=handler["stores"]
        item["same_value_native_stores"]+=handler["same"]
        item["changed_value_native_stores"]+=handler["stores"]-handler["same"]

    overall=_blank()
    for bucket_no,bucket in enumerate(totals_by_bucket):
        for klass in CLASSES:
            expected=preceding["per_vblank_class_cases"][bucket_no][
                "classes"][klass][ELIGIBLE]
            for field in FIELDS:
                if bucket[klass][field]!=expected[field]:
                    raise Refused("v111 class-by-VBlank store partition disagreement")
                overall[field]+=bucket[klass][field]

    crossing_edges=[0,0,0,0]
    within_pairs=[0]*5
    cross_pairs=0
    pairs={}
    for run in runs:
        for left,right in zip(run,run[1:]):
            if right["seq"]<=left["seq"] or right["bucket"]<left["bucket"]:
                raise Refused("out-of-order native Unai callback sequence")
            if left["bucket"]==right["bucket"]:
                within_pairs[left["bucket"]]+=1
            else:
                cross_pairs+=1
            for edge_index,edge in enumerate(edges):
                if left["seq"]<edge<right["seq"]:
                    crossing_edges[edge_index]+=1
            label=(left["class"],right["class"],
                   "same_vblank_bucket" if left["bucket"]==right["bucket"]
                   else "crosses_vblank")
            pairs[label]=pairs.get(label,0)+1

    eligible=sum(h["eligible"] for h in handlers)
    run_sizes=[len(run) for run in runs]
    if eligible!=overall["handlers"] or sum(run_sizes)!=eligible:
        raise Refused("eligible sample-unchanged Unai handlers lost")
    if sum(within_pairs)+cross_pairs!=sum(max(n-1,0) for n in run_sizes):
        raise Refused("same/cross VBlank qualifying handler pairs not conserved")
    if sum(crossing_edges)!=sum(
        right["bucket"]-left["bucket"]
        for run in runs for left,right in zip(run,run[1:])
    ):
        raise Refused("number of crossed VBlank boundaries inconsistent")
    # Each edge can be bridged by no more than one run of consecutive
    # qualifying callbacks, since the underlying Unai observer is ordered.
    if any(count>1 for count in crossing_edges):
        raise Refused("overlapping qualifying runs at a VBlank boundary")

    checkpoints=[]
    for i,edge in enumerate(edges):
        counter={klass:_blank() for klass in CLASSES}
        for handler in handlers:
            if not handler["eligible"] or handler["seq"]>=edge:
                continue
            item=counter[handler["class"]]
            item["handlers"]+=1
            item["native_store_attempts"]+=handler["stores"]
            item["same_value_native_stores"]+=handler["same"]
            item["changed_value_native_stores"]+=handler["stores"]-handler["same"]
        old=preceding["before_vblank_cumulative_sample_unchanged_stores"][i][
            "sample_unchanged_with_stores_cumulative_by_class"]
        for klass in CLASSES:
            for new_key,old_key in (
                ("handlers","unchanged_sample_with_instrumented_stores"),
                ("native_store_attempts","native_stores_with_unchanged_samples"),
                ("same_value_native_stores","same_value_stores_with_unchanged_samples"),
                ("changed_value_native_stores","changed_value_stores_with_unchanged_samples"),
            ):
                if counter[klass][new_key]!=old[klass][old_key]:
                    raise Refused("v111 native sampled-unchanged VBlank prefix differs")
            if counter[klass]["native_store_attempts"]>(
                native_boundaries["snapshots_before_vblank"][i][
                    "cumulative_by_class"][klass]["native_store_attempts"]
            ):
                raise Refused("qualifying native stores exceed entire VBlank prefix")
        checkpoints.append({
            "vblank_ordinal":i+1,
            "cumulative_unchanged_sample_stores_by_class":counter,
            "run_of_consecutive_qualifying_handlers_spans_edge":
                crossing_edges[i]==1,
        })
    return {
        "scope":"pinned_pcsx_synthetic_unai_zero_sample_delta_native_store_runs",
        "vblank_edges":4,
        "qualifying_unai_handlers":eligible,
        "qualifying_runs":len(runs),
        "multi_handler_runs":sum(n>=2 for n in run_sizes),
        "longest_consecutive_qualifying_handlers":max(run_sizes,default=0),
        "intra_interval_adjacent_qualifying_pairs":within_pairs,
        "adjacent_qualifying_pairs_crossing_vblank":cross_pairs,
        "vblank_edges_crossed_by_consecutive_qualifying_pairs":crossing_edges,
        "qualifying_class_pair_transitions":[
            {"from_class":a,"to_class":b,"boundary":type_,"pairs":count}
            for (a,b,type_),count in sorted(pairs.items())
        ],
        "per_vblank_class_native_stores":totals_by_bucket,
        "total_qualifying_native_stores":overall,
        "before_vblank_native_store_prefixes":checkpoints,
        "observed_unai_handlers":len(handlers),
        "zero_sample_delta_is_not_whole_VRAM_unchanged":True,
        "crossing_vblank_does_not_establish_VRAM_persistence":True,
        "same_value_stores_are_real_16bit_assignments":True,
        "complete_GPU_DMA_assembly_coverage":False,
        "emulated_gpu_completion_cycles_proven":False,
        "physical_ps1_vblank_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:
        report=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
