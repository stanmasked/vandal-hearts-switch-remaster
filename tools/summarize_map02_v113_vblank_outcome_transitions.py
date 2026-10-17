#!/usr/bin/env python3
"""Conserved GP0 sample/store outcome transitions across native VBlank callbacks.

VBlank is a marker in host event append order, not evidence of the pixel
state in a physical PS1 scanout, GPU completion cycle or whole-VRAM memory.
Only coarse classifications and integer counts may be exported.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v109_gp0_class_vblank_stores import CLASSES, classify
from .summarize_map02_v110_class_boundary_checkpoints import summarize as v110
from .summarize_map02_v111_sample_store_divergence import (
    CASES, classify_case, summarize as v111,
)
from .summarize_map02_v112_unchanged_sample_runs import summarize as v112

QUALIFYING="unchanged_sample_with_instrumented_stores"


def summarize(raw: bytes):
    source=validate(raw)
    prev110=v110(raw)
    prev111=v111(raw)
    prev112=v112(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[row["seq"] for row in rows if row["kind"]=="vblank"]
    if len(edges)!=4:
        raise Refused("missing native four VBlank observations")

    handlers=[]
    for index,evt in enumerate(rows):
        if evt["kind"]!="gp0_unai_handled":
            continue
        group=rows[index:index+4]
        if len(group)!=4 or [r["kind"] for r in group]!=[
            "gp0_unai_handled","unai_sample_delta",
            "unai_store_count","unai_same_store_count"
        ] or [r["seq"] for r in group]!=list(range(evt["seq"],evt["seq"]+4)):
            raise Refused("incomplete renderer sample/store quartet")
        ordinal=sum(evt["seq"]>edge for edge in edges)
        if any(sum(row["seq"]>edge for edge in edges)!=ordinal for row in group):
            raise Refused("VBlank split renderer/store observation")
        sample,stores,same=(group[1]["value"],group[2]["value"],group[3]["value"])
        if sample>24 or same>stores:
            raise Refused("native sampled readback/store counter invalid")
        handlers.append({
            "seq":evt["seq"],"bucket":ordinal,
            "class":classify(evt["value"]),
            "case":classify_case(sample,stores),
        })

    # Each observed handler participates in at most two adjacent pairs.
    # Expose only aggregate class/outcome transitions, never command words.
    intervals=[{
        "ordinal":index,
        "observed_handlers":0,
        "adjacent_pairs":0,
        "outcome_transitions":[],
    } for index in range(5)]
    within=[{} for _ in range(5)]
    cross={}
    class_pairs=[{} for _ in range(5)]
    edge_crossings=[0,0,0,0]
    qualifying_crossed=[0,0,0,0]
    qualifying_within=[0]*5
    qualifying_across=0

    for event in handlers:
        intervals[event["bucket"]]["observed_handlers"]+=1
    for left,right in zip(handlers,handlers[1:]):
        gap=right["bucket"]-left["bucket"]
        if gap<0 or gap>4:
            raise Refused("native GPU handler/VBlank order reversed")
        key=(left["case"],right["case"])
        if not gap:
            bucket=left["bucket"]
            within[bucket][key]=within[bucket].get(key,0)+1
            ckey=(left["class"],right["class"])
            class_pairs[bucket][ckey]=class_pairs[bucket].get(ckey,0)+1
            intervals[bucket]["adjacent_pairs"]+=1
        else:
            xkey=(gap,left["case"],right["case"])
            cross[xkey]=cross.get(xkey,0)+1
            for i in range(left["bucket"],right["bucket"]):
                edge_crossings[i]+=1
        if left["case"]==right["case"]==QUALIFYING:
            if gap:
                qualifying_across+=1
                for i in range(left["bucket"],right["bucket"]):
                    qualifying_crossed[i]+=1
            else:
                qualifying_within[left["bucket"]]+=1

    for i,bucket in enumerate(intervals):
        bucket["outcome_transitions"]=[
            {"from_outcome":a,"to_outcome":b,"pairs":count}
            for (a,b),count in sorted(within[i].items())
        ]
        previous=prev110["intra_interval_transitions"][i]
        if bucket["observed_handlers"]!=sum(
            x["handlers"] for x in prev111["per_vblank_class_cases"][i][
                "classes"].values() for x in x.values()
        ):
            raise Refused("observed handler count inconsistent with v111")
        if bucket["adjacent_pairs"]!=previous["adjacent_handler_pairs"]:
            raise Refused("outcome transitions do not conserve native handler pairs")
        actual_class=[
            {"from_class":a,"to_class":b,"pairs":count}
            for (a,b),count in sorted(class_pairs[i].items())
        ]
        if actual_class!=previous["class_transitions"]:
            raise Refused("outcome transitions disagree with native class order")

    crossing=sum(cross.values())
    if crossing!=prev110["handler_pairs_crossing_one_or_more_vblank_edges"]:
        raise Refused("missing cross-VBlank native callback transitions")
    if sum(bucket["adjacent_pairs"] for bucket in intervals)+crossing!=max(
        len(handlers)-1,0
    ):
        raise Refused("adjacent observed GPU handler pairs not conserved")
    if qualifying_across!=prev112["adjacent_qualifying_pairs_crossing_vblank"]:
        raise Refused("qualifying pair VBlank crossing changed since v112")
    if qualifying_within!=prev112["intra_interval_adjacent_qualifying_pairs"]:
        raise Refused("qualifying same-interval adjacency changed since v112")
    if qualifying_crossed!=prev112[
        "vblank_edges_crossed_by_consecutive_qualifying_pairs"
    ]:
        raise Refused("qualifying VBlank edge observations differ from v112")

    edge_witnesses=[]
    for index,edge in enumerate(edges):
        before=next((h for h in reversed(handlers) if h["seq"]<edge),None)
        after=next((h for h in handlers if h["seq"]>edge),None)
        v110_snapshot=prev110["snapshots_before_vblank"][index]
        before_class=None if before is None else before["class"]
        after_class=None if after is None else after["class"]
        if (before_class!=v110_snapshot["last_prior_unai_class"] or
            after_class!=v110_snapshot["first_later_unai_class"]):
            raise Refused("VBlank adjacent class witnesses differ from v110")
        witnessed_gap=0 if before is None or after is None else (
            after["bucket"]-before["bucket"]
        )
        if before is not None and after is not None and witnessed_gap<1:
            raise Refused("missing VBlank between before/after witnesses")
        expected=1 if before is not None and after is not None else 0
        if edge_crossings[index]!=expected:
            raise Refused("VBlank edge witness pair inconsistent")
        if (before is not None and after is not None and
            witnessed_gap!=v110_snapshot["first_later_gap_vblank_edges"]):
            raise Refused("VBlank edge distance differs from v110")
        edge_witnesses.append({
            "vblank_ordinal":index+1,
            "previous_handler_class":before_class,
            "previous_handler_outcome":None if before is None else before["case"],
            "next_handler_class":after_class,
            "next_handler_outcome":None if after is None else after["case"],
            "vblank_edges_between_nearest_observed_handlers":
                None if not expected else witnessed_gap,
            "qualifying_zero_sample_store_pair_spans_edge":
                qualifying_crossed[index]==1,
        })

    cross_rows=[
        {"vblank_edges_crossed":gap,"from_outcome":left,
         "to_outcome":right,"pairs":count}
        for (gap,left,right),count in sorted(cross.items())
    ]
    if sum(r["vblank_edges_crossed"]*r["pairs"] for r in cross_rows)!=sum(
        edge_crossings
    ):
        raise Refused("VBlank edge crossing sum differs from pair gaps")
    return {
        "scope":"pinned_pcsx_unai_ordinal_sample_store_outcome_transitions",
        "observed_unai_handlers":len(handlers),
        "observed_emulator_vblank_edges":4,
        "outcome_classes":list(CASES),
        "within_vblank_intervals":intervals,
        "cross_vblank_outcome_transitions":cross_rows,
        "adjacent_pairs_spanning_vblank":crossing,
        "vblank_edge_witnesses":edge_witnesses,
        "observed_handler_pairs_per_edge":edge_crossings,
        "zero_sample_delta_store_pairs_per_edge":qualifying_crossed,
        "zero_delta_does_not_prove_whole_vram_unchanged":True,
        "cross_vblank_pairs_do_not_prove_vram_persistence":True,
        "observed_append_order_is_not_gpu_completion_timing":True,
        "all_gpu_dma_assembly_or_legacy_stores_covered":False,
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
