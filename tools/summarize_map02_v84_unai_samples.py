#!/usr/bin/env python3
"""Fail-closed v84 read-only 24-point Unai pre/post comparison summary.

Deltas describe changed sampled VRAM VALUES only. Delta=0 cannot distinguish
absence of writes from a same-value write, blending or overwritten pixels.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v83_unai_vblank import summarize as summarize_v83
from .verify_map02_v82_native_trace import Refused

def summarize(raw: bytes):
    base=summarize_v83(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    handled=[(i,e) for i,e in enumerate(events) if e["kind"]=="gp0_unai_handled"]
    samples=[e for e in events if e["kind"]=="unai_sample_delta"]
    if not samples or len(samples)!=len(handled):
        raise Refused("not exactly one sample event per Unai handler")
    paired=[]
    for index, event in handled:
        if index+1>=len(events) or events[index+1]["kind"]!="unai_sample_delta":
            raise Refused("missing immediately adjacent post-handler readback")
        sample=events[index+1]
        if sample["seq"]!=event["seq"]+1:
            raise Refused("readback sequence differs from handler sequence")
        paired.append((event["seq"],sample["value"]))
    changed=sum(value>0 for _,value in paired)
    equal=sum(value==0 for _,value in paired)
    if changed==0 or equal==0:
        raise Refused("fixture lacks both changed and unchanged readbacks")
    edges=[e for e in events if e["kind"]=="vblank"]
    result=[]
    for a,b in zip(edges,edges[1:]):
        vals=[value for seq,value in paired if a["seq"]<seq<b["seq"]]
        result.append({
            "from_emulated_frame":a["frame"],
            "to_emulated_frame":b["frame"],
            "handlers_with_sample_delta":len(vals),
            "sampled_vram_changed_handlers":sum(v>0 for v in vals),
            "sampled_vram_unchanged_handlers":sum(v==0 for v in vals),
            "changed_sample_points":sum(vals)
        })
    return {
        "scope":"pinned_pcsx_synthetic_unai_24_source_vram_readbacks",
        "sample_points_per_handler":24,
        "handler_comparisons":len(paired),
        "changed_handlers":changed,
        "unchanged_handlers":equal,
        "changed_sample_points":sum(value for _,value in paired),
        "between_vblank_intervals":result,
        "no_actual_pixel_write_inferred_from_zero_delta":True,
        "same_color_write_distinguished":False,
        "actual_PutPixel_calls_observed":False,
        "physical_ps1_vblank_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_trace",type=Path)
    args=p.parse_args()
    try:
        report=summarize(args.private_trace.read_bytes())
    except (OSError,Refused,UnicodeError) as error:
        p.exit(2,f"REFUSED: {error}\n")
    print(json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
