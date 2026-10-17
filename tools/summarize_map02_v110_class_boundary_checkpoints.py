#!/usr/bin/env python3
"""Native Unai GP0 class continuity at *observed* emulator VBlank edges.

The public result contains only ordinal cumulative counters and coarse
classes. This does not infer CPU/GPU completion cycles or retail MAP02 frames.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v109_gp0_class_vblank_stores import (
    summarize as v109, classify, CLASSES, FIELDS,
)

SNAPSHOT_FIELDS=("handlers","native_store_attempts",
                 "same_value_native_stores","changed_value_native_stores")


def _empty():
    return {field:0 for field in SNAPSHOT_FIELDS}


def summarize(raw: bytes):
    validate(raw)
    prior=v109(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in rows if r["kind"]=="vblank"]
    if len(edges)!=4 or len(prior["intervals"])!=5:
        raise Refused("four emulator VBlank callback edges required")
    observed=[]
    for index,row in enumerate(rows):
        if row["kind"]!="gp0_unai_handled":
            continue
        block=rows[index:index+4]
        if len(block)!=4 or [r["kind"] for r in block]!=[
                "gp0_unai_handled","unai_sample_delta",
                "unai_store_count","unai_same_store_count"]:
            raise Refused("incomplete renderer/store observation")
        if [r["seq"] for r in block]!=list(range(row["seq"],row["seq"]+4)):
            raise Refused("renderer/store sequence gap")
        ordinal=sum(row["seq"]>edge for edge in edges)
        if any(sum(event["seq"]>edge for edge in edges)!=ordinal
               for event in block):
            raise Refused("renderer/native-store quartet split by VBlank")
        stores=block[2]["value"]
        same=block[3]["value"]
        if same>stores:
            raise Refused("same-value assignment overflow")
        observed.append({
            "seq":row["seq"],"bucket":ordinal,"class":classify(row["value"]),
            "handlers":1,"native_store_attempts":stores,
            "same_value_native_stores":same,
            "changed_value_native_stores":stores-same,
        })

    # Check independently reconstructed per-class totals from every bucket.
    class_totals=[{klass:_empty() for klass in CLASSES} for _ in range(5)]
    for record in observed:
        entry=class_totals[record["bucket"]][record["class"]]
        for field in SNAPSHOT_FIELDS:
            entry[field]+=record[field]
    for index,bucket in enumerate(prior["intervals"]):
        for klass in CLASSES:
            if any(class_totals[index][klass][field]!=
                   bucket["classes"][klass][field]
                   for field in SNAPSHOT_FIELDS):
                raise Refused("native class store totals inconsistent with v109")

    # Cumulative snapshots are taken strictly BEFORE each VBlank event.
    # Delta between adjacent snapshots must recover prior per-class buckets.
    snapshots=[]
    for edge_index,edge_seq in enumerate(edges):
        counters={klass:_empty() for klass in CLASSES}
        for record in observed:
            if record["seq"]>=edge_seq:
                continue
            target=counters[record["class"]]
            for field in SNAPSHOT_FIELDS:
                target[field]+=record[field]
        for klass in CLASSES:
            for field in SNAPSHOT_FIELDS:
                expected=sum(class_totals[b][klass][field]
                             for b in range(edge_index+1))
                if counters[klass][field]!=expected:
                    raise Refused("VBlank cumulative class boundary mismatch")
        previous=next((x for x in reversed(observed)
                       if x["seq"]<edge_seq),None)
        following=next((x for x in observed
                        if x["seq"]>edge_seq),None)
        snapshots.append({
            "vblank_ordinal":edge_index+1,
            "cumulative_by_class":counters,
            "last_prior_unai_class":None if previous is None else previous["class"],
            "first_later_unai_class":None if following is None else following["class"],
            "first_later_gap_vblank_edges":(
                None if previous is None or following is None else
                sum(previous["seq"]<candidate<following["seq"]
                    for candidate in edges)),
        })

    within=[]
    crossing=0
    for i,bucket in enumerate(prior["intervals"]):
        members=[record for record in observed if record["bucket"]==i]
        pairs={}
        for left,right in zip(members,members[1:]):
            key=(left["class"],right["class"])
            pairs[key]=pairs.get(key,0)+1
        if sum(pairs.values())!=max(len(members)-1,0):
            raise Refused("intra-interval Unai class adjacency not conserved")
        if len(members)!=sum(c["handlers"] for c in bucket["classes"].values()):
            raise Refused("Unai interval population mismatch")
        within.append({
            "interval":bucket["interval"],
            "adjacent_handler_pairs":sum(pairs.values()),
            "class_transitions":[
                {"from_class":a,"to_class":b,"pairs":count}
                for (a,b),count in sorted(pairs.items())
            ],
        })
    for left,right in zip(observed,observed[1:]):
        if left["bucket"]!=right["bucket"]:
            crossing+=1
    if sum(v["adjacent_handler_pairs"] for v in within)+crossing!=max(len(observed)-1,0):
        raise Refused("GPU callback adjacency cannot be reconciled")
    return {
        "scope":"pinned_pcsx_unai_ordinal_native_store_boundary_continuity",
        "vblank_edges":4,
        "snapshots_before_vblank":snapshots,
        "intra_interval_transitions":within,
        "handler_pairs_crossing_one_or_more_vblank_edges":crossing,
        "observed_unai_handlers":len(observed),
        "classification":"host_callback_append_order_only",
        "exact_gpu_cpu_timing_verified":False,
        "all_gpu_DMA_asm_or_legacy_stores_observed":False,
        "retail_MAP02_verified":False,
        "physical_ps1_vblank_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        report=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as e:
        parser.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
