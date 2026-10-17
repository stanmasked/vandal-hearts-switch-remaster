#!/usr/bin/env python3
"""Ordinal VBlank/Unai native store audit of private pinned PCSX synthetic traces.

This classifies EVENT APPEND ORDER only. GP0 Unai callbacks carry neither
emulated CPU cycles nor frame numbers. No real-time completion claims.
Only aggregate numeric counters can leave the private CI boundary.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v83_unai_vblank import summarize as v83
from .summarize_map02_v84_unai_samples import summarize as v84
from .summarize_map02_v85_native_stores import summarize as v85

LABELS=("before_first_vblank","between_vblank_1_2",
        "between_vblank_2_3","between_vblank_3_4","after_last_vblank")
METRICS=("unai_handlers","sampled_changed_handlers",
         "sampled_unchanged_handlers","changed_sample_points",
         "native_store_attempts","same_value_native_stores",
         "changed_value_native_stores","gp1_mmio_inputs",
         "gpu_dma2_start_inputs")


def summarize(raw: bytes):
    strict=validate(raw)
    old83=v83(raw)
    old84=v84(raw)
    old85=v85(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[e for e in rows if e["kind"]=="vblank"]
    if len(edges)!=4 or strict["vblank_edges"]!=4:
        raise Refused("expected four authentic-emulator VBlank callbacks")

    boundaries=[e["seq"] for e in edges]
    # Records are append-ordered, NOT timestamp-aligned to emulator cycles.
    def bucket(sequence):
        return sum(sequence>edge for edge in boundaries)

    groups=[dict(label=label,**{field:0 for field in METRICS})
            for label in LABELS]
    nhandlers=0
    ninputs=0
    for i,event in enumerate(rows):
        kind=event["kind"]
        if kind in ("gp1_mmio","gpu_dma2_start"):
            groups[bucket(event["seq"])][
                "gp1_mmio_inputs" if kind=="gp1_mmio" else
                "gpu_dma2_start_inputs"]+=1
            ninputs+=1
        if kind!="gp0_unai_handled":
            continue
        if i+3>=len(rows):
            raise Refused("truncated four-event Unai handler observation")
        four=rows[i:i+4]
        if [r["kind"] for r in four]!=[
                "gp0_unai_handled","unai_sample_delta",
                "unai_store_count","unai_same_store_count"]:
            raise Refused("renderer/store observations not adjacent")
        # No intervening VBlank can divide an individual Unai observation.
        if [r["seq"] for r in four]!=list(range(event["seq"],event["seq"]+4)):
            raise Refused("nonconsecutive Unai observation")
        if four[3]["value"]>four[2]["value"]:
            raise Refused("same-value stores exceed native assignments")
        idx=bucket(event["seq"])
        if any(bucket(r["seq"])!=idx for r in four):
            raise Refused("VBlank split one native handler observation")
        target=groups[idx]
        target["unai_handlers"]+=1
        target["sampled_changed_handlers"]+=int(four[1]["value"]>0)
        target["sampled_unchanged_handlers"]+=int(four[1]["value"]==0)
        target["changed_sample_points"]+=four[1]["value"]
        target["native_store_attempts"]+=four[2]["value"]
        target["same_value_native_stores"]+=four[3]["value"]
        target["changed_value_native_stores"]+=four[2]["value"]-four[3]["value"]
        nhandlers+=1

    totals={field:sum(b[field] for b in groups) for field in METRICS}
    expected={
        "unai_handlers":strict["gp0_unai_handled"],
        "sampled_changed_handlers":old84["changed_handlers"],
        "sampled_unchanged_handlers":old84["unchanged_handlers"],
        "changed_sample_points":old84["changed_sample_points"],
        "native_store_attempts":old85["native_store_attempts"],
        "same_value_native_stores":
            old85["native_stores_writing_previous_value"],
        "changed_value_native_stores":
            old85["native_stores_writing_new_value"],
        "gp1_mmio_inputs":strict["gp1_mmio"],
        "gpu_dma2_start_inputs":strict["gpu_dma2_start"],
    }
    if totals!=expected or nhandlers!=old83["gp0_unai_handled"] or (
            ninputs!=strict["gp1_mmio"]+strict["gpu_dma2_start"]):
        raise Refused("VBlank ordinal buckets do not conserve audited events")
    if [b["unai_handlers"] for b in groups]!=(
            [old83["before_first_vblank"]]+
            [e["unai_handler_events"] for e in old83["between_vblanks"]]+
            [old83["after_last_vblank"]]):
        raise Refused("intervals disagree with original v83 handler audit")

    return {
        "scope":"pinned_pcsx_synthetic_unai_event_append_order",
        "vblank_edges":4,
        "grouping":"ordinal_only_no_gpu_cpu_cycle_or_frame_inference",
        "buckets":groups,
        "totals":totals,
        "actual_native_16bit_store_attempts_observed":True,
        "complete_GPU_command_or_VRAM_coverage":False,
        "vblank_cpu_cycle_accurate_gpu_completion":False,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        result=summarize(args.private_jsonl.read_bytes())
    except (OSError, UnicodeError, Refused) as exc:
        parser.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
