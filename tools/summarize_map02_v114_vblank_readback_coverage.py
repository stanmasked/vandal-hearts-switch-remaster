#!/usr/bin/env python3
"""Observed 24-point Unai VRAM readback coverage at four emulator VBlank edges.

Readback sample deltas are COUNTS, not persistent frame state or actual
pixel-address snapshots. Only host callback append order is available.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v109_gp0_class_vblank_stores import classify
from .summarize_map02_v111_sample_store_divergence import (
    classify_case, summarize as v111,
)
from .summarize_map02_v113_vblank_outcome_transitions import summarize as v113

BUCKET_NAMES=("before_first_vblank","between_vblank_1_2",
              "between_vblank_2_3","between_vblank_3_4","after_last_vblank")
METRICS=("observed_readbacks","sample_changed_readbacks",
         "sample_unchanged_readbacks","changed_sample_points",
         "instrumented_16bit_store_attempts","same_value_16bit_stores")


def _blank(name):
    return {"interval":name,**{k:0 for k in METRICS}}


def _coverage(count,changed):
    if count==0:
        return "no_observed_unai_readback"
    if changed==0:
        return "only_zero_sample_deltas"
    if changed==count:
        return "only_nonzero_sample_deltas"
    return "mixed_zero_and_nonzero_sample_deltas"


def summarize(raw: bytes):
    verified=validate(raw)
    prev111=v111(raw)
    prev113=v113(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in rows if r["kind"]=="vblank"]
    if len(edges)!=4:
        raise Refused("four native emulator VBlank callbacks missing")
    handlers=[]
    buckets=[_blank(n) for n in BUCKET_NAMES]
    for i,row in enumerate(rows):
        if row["kind"]!="gp0_unai_handled":
            continue
        quartet=rows[i:i+4]
        if len(quartet)!=4 or [x["kind"] for x in quartet]!=[
            "gp0_unai_handled","unai_sample_delta",
            "unai_store_count","unai_same_store_count"
        ] or [x["seq"] for x in quartet]!=list(range(row["seq"],row["seq"]+4)):
            raise Refused("incomplete or nonadjacent Unai readback/store group")
        bucket=sum(row["seq"]>edge for edge in edges)
        if any(sum(x["seq"]>edge for edge in edges)!=bucket for x in quartet):
            raise Refused("native VBlank splits Unai handler/readback observation")
        delta,attempts,same=[x["value"] for x in quartet[1:4]]
        if delta>24 or same>attempts:
            raise Refused("impossible native sample delta or store count")
        data={
            "seq":row["seq"],"bucket":bucket,"class":classify(row["value"]),
            "delta":delta,"attempts":attempts,"same":same,
            "case":classify_case(delta,attempts),
        }
        handlers.append(data)
        item=buckets[bucket]
        item["observed_readbacks"]+=1
        item["sample_changed_readbacks"]+=int(delta>0)
        item["sample_unchanged_readbacks"]+=int(delta==0)
        item["changed_sample_points"]+=delta
        item["instrumented_16bit_store_attempts"]+=attempts
        item["same_value_16bit_stores"]+=same

    for index,item in enumerate(buckets):
        old=prev111["per_vblank_class_cases"][index]["classes"]
        expected={
            "observed_readbacks":0,
            "sample_changed_readbacks":0,
            "sample_unchanged_readbacks":0,
            "changed_sample_points":0,
            "instrumented_16bit_store_attempts":0,
            "same_value_16bit_stores":0,
        }
        for perclass in old.values():
            for case,counters in perclass.items():
                count=counters["handlers"]
                expected["observed_readbacks"]+=count
                expected["sample_changed_readbacks"]+=(
                    count if case.startswith("changed_sample_") else 0)
                expected["sample_unchanged_readbacks"]+=(
                    count if case.startswith("unchanged_sample_") else 0)
                expected["changed_sample_points"]+=counters["changed_sample_points"]
                expected["instrumented_16bit_store_attempts"]+=counters[
                    "native_store_attempts"]
                expected["same_value_16bit_stores"]+=counters[
                    "same_value_native_stores"]
        if any(item[field]!=expected[field] for field in METRICS):
            raise Refused("VBlank readback coverage disagrees with v111 class counts")
        if item["observed_readbacks"]!=(
            item["sample_changed_readbacks"]+item["sample_unchanged_readbacks"]
        ):
            raise Refused("observed readbacks do not partition")
        item["coverage"]= _coverage(
            item["observed_readbacks"],item["sample_changed_readbacks"])
        item["unobserved_whole_vram_state"]=True

    # A VBlank with no Unai callback between its previous and next edge
    # is a BLIND OBSERVATION WINDOW, not a witnessed unchanged GPU frame.
    windows=[]
    max_empty_streak=0
    empty_streak=0
    for i in range(1,4):
        bucket=buckets[i]
        blind=bucket["observed_readbacks"]==0
        empty_streak=empty_streak+1 if blind else 0
        max_empty_streak=max(max_empty_streak,empty_streak)
        windows.append({
            "between_vblank_ordinals":[i,i+1],
            "observed_readbacks":bucket["observed_readbacks"],
            "observed_changed_readbacks":bucket["sample_changed_readbacks"],
            "changed_sample_points":bucket["changed_sample_points"],
            "observation_coverage":bucket["coverage"],
            "no_readback_does_not_imply_unchanged_vram":True,
        })

    # Compare the NUMBER of changed sample locations observed by consecutive
    # callbacks. The same 24 site locations are not exported, and these
    # comparisons do NOT identify persistent pixel contents.
    trends=[{"interval":name,"increasing":0,"equal":0,"decreasing":0}
            for name in BUCKET_NAMES]
    cross_trends={}
    crosses=[0,0,0,0]
    for a,b in zip(handlers,handlers[1:]):
        direction=("increasing" if b["delta"]>a["delta"] else
                   "decreasing" if b["delta"]<a["delta"] else "equal")
        gap=b["bucket"]-a["bucket"]
        if gap==0:
            trends[a["bucket"]][direction]+=1
        elif 1<=gap<=4:
            key=(gap,direction)
            cross_trends[key]=cross_trends.get(key,0)+1
            for k in range(a["bucket"],b["bucket"]):
                crosses[k]+=1
        else:
            raise Refused("callback ordering reversed")
    for i,row in enumerate(trends):
        if sum(row[k] for k in ("increasing","equal","decreasing"))!=(
            prev113["within_vblank_intervals"][i]["adjacent_pairs"]
        ):
            raise Refused("readback trends do not conserve same-window callbacks")
    if sum(cross_trends.values())!=prev113["adjacent_pairs_spanning_vblank"]:
        raise Refused("cross-VBlank readback trends lack observed pairs")
    if crosses!=prev113["observed_handler_pairs_per_edge"]:
        raise Refused("readback trend VBlank crossings disagree with v113")

    edge_witness=[]
    for index,edge in enumerate(edges):
        before=next((h for h in reversed(handlers) if h["seq"]<edge),None)
        after=next((h for h in handlers if h["seq"]>edge),None)
        prior=prev113["vblank_edge_witnesses"][index]
        if ((None if before is None else before["case"])!=
            prior["previous_handler_outcome"] or
            (None if after is None else after["case"])!=
            prior["next_handler_outcome"] or
            (None if before is None else before["class"])!=
            prior["previous_handler_class"] or
            (None if after is None else after["class"])!=
            prior["next_handler_class"]):
            raise Refused("nearest readback witnesses differ from verified v113")
        gap=None if before is None or after is None else (
            after["bucket"]-before["bucket"])
        if gap!=prior["vblank_edges_between_nearest_observed_handlers"]:
            raise Refused("nearest readback VBlank gap differs from v113")
        edge_witness.append({
            "vblank_ordinal":index+1,
            "prior_observed_changed_sample_points":None if before is None
                    else before["delta"],
            "next_observed_changed_sample_points":None if after is None
                    else after["delta"],
            "native_vblank_edges_between_observed_readbacks":gap,
            "no_direct_whole_vram_state_observation":True,
        })
    if sum(b["observed_readbacks"] for b in buckets)!=verified[
        "gp0_unai_handled"]:
        raise Refused("lost observed Unai handlers")
    if sum(b["changed_sample_points"] for b in buckets)!=verified[
        "sampled_pixels_changed"]:
        raise Refused("lost native Unai readback delta observations")
    return {
        "scope":"pinned_pcsx_unai_sample_readback_coverage_only",
        "emulator_vblank_edges":4,
        "intervals":buckets,
        "between_vblank_observation_windows":windows,
        "windows_without_any_observed_unai_readback":sum(
            window["observed_readbacks"]==0 for window in windows),
        "longest_consecutive_between_vblank_windows_without_readbacks":
            max_empty_streak,
        "same_interval_readback_change_count_trends":trends,
        "cross_vblank_readback_change_count_trends":[
            {"vblank_edges_crossed":gap,"direction":direction,"pairs":count}
            for (gap,direction),count in sorted(cross_trends.items())
        ],
        "readback_pair_observed_vblank_edges":crosses,
        "nearest_observed_readbacks_around_vblank":edge_witness,
        "observed_unai_handlers":len(handlers),
        "only_24_sample_locations_per_handler":True,
        "no_readback_is_not_proof_of_no_vram_changes":True,
        "same_delta_count_is_not_proof_of_same_pixel_values":True,
        "host_event_order_is_not_ps1_gpu_completion":True,
        "original_retail_MAP02_verified":False,
        "physical_PS1_vblank_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(summarize(args.private_jsonl.read_bytes()),sort_keys=True))
    except (OSError,UnicodeError,Refused) as err:
        parser.exit(2,f"REFUSED: {err}\n")


if __name__=="__main__":
    main()
