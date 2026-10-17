#!/usr/bin/env python3
"""Classify observed Unai GP0 callbacks and native stores by VBlank append order.

Only *coarse command classes and counters* leave the private trace. Callback
order is not an emulated cycle, pixel-raster-completion or retail MAP02 time.
"""
import argparse
import json
from pathlib import Path

from .verify_map02_v82_native_trace import Refused, validate
from .summarize_map02_v108_vblank_store_buckets import (
    summarize as v108, LABELS,
)

CLASSES=("fill_vram","polygon_primitive","line_primitive",
         "rectangle_sprite_primitive","gpu_state")
FIELDS=("handlers","sampled_changed_handlers","sampled_unchanged_handlers",
        "changed_sample_points","native_store_attempts",
        "same_value_native_stores","changed_value_native_stores")


def classify(word):
    """Allowed Unai dispatch classes; never return header words or coordinates."""
    op=word>>24
    if op==0x02:
        return "fill_vram"
    if 0x20<=op<=0x3f:
        return "polygon_primitive"
    if 0x40<=op<=0x43 or 0x48<=op<=0x53 or 0x58<=op<=0x5f:
        return "line_primitive"
    if 0x60<=op<=0x6b or 0x70<=op<=0x7f:
        return "rectangle_sprite_primitive"
    if 0xe1<=op<=0xe6:
        return "gpu_state"
    raise Refused("unclassified or unsupported observed Unai command")


def empty():
    return {metric:0 for metric in FIELDS}


def summarize(raw: bytes):
    strict=validate(raw)
    prior=v108(raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edge_seqs=[row["seq"] for row in rows if row["kind"]=="vblank"]
    if len(edge_seqs)!=4:
        raise Refused("four original VBlank callbacks required")
    per_vblank=[
        {"interval":name,"classes":{kind:empty() for kind in CLASSES}}
        for name in LABELS
    ]
    for pos,event in enumerate(rows):
        if event["kind"]!="gp0_unai_handled":
            continue
        block=rows[pos:pos+4]
        if len(block)!=4 or [r["kind"] for r in block]!=[
                "gp0_unai_handled","unai_sample_delta",
                "unai_store_count","unai_same_store_count"]:
            raise Refused("incomplete native Unai observation block")
        if [r["seq"] for r in block]!=list(range(event["seq"],event["seq"]+4)):
            raise Refused("non-consecutive renderer/store observations")
        target_interval=sum(event["seq"]>edge for edge in edge_seqs)
        if any(sum(r["seq"]>edge for edge in edge_seqs)!=target_interval
               for r in block):
            raise Refused("VBlank divided the native Unai observation")
        klass=classify(event["value"])
        target=per_vblank[target_interval]["classes"][klass]
        sampled=block[1]["value"]
        writes=block[2]["value"]
        unchanged=block[3]["value"]
        if unchanged>writes:
            raise Refused("native same-value assignments exceed all assignments")
        # E1..E6 are GP0 environment/state operations, not raster pixel stores.
        # A nonzero instrumented store must not be silently grouped as geometry.
        if klass=="gpu_state" and writes:
            raise Refused("state-only GPU command had instrumented pixel writes")
        target["handlers"]+=1
        target["sampled_changed_handlers"]+=int(sampled>0)
        target["sampled_unchanged_handlers"]+=int(sampled==0)
        target["changed_sample_points"]+=sampled
        target["native_store_attempts"]+=writes
        target["same_value_native_stores"]+=unchanged
        target["changed_value_native_stores"]+=writes-unchanged

    totals_by_class={klass:empty() for klass in CLASSES}
    for index,segment in enumerate(per_vblank):
        reference=prior["buckets"][index]
        if segment["interval"]!=reference["label"]:
            raise Refused("ordinal interval label mismatch")
        for field,prior_field in (
            ("handlers","unai_handlers"),
            ("sampled_changed_handlers","sampled_changed_handlers"),
            ("sampled_unchanged_handlers","sampled_unchanged_handlers"),
            ("changed_sample_points","changed_sample_points"),
            ("native_store_attempts","native_store_attempts"),
            ("same_value_native_stores","same_value_native_stores"),
            ("changed_value_native_stores","changed_value_native_stores"),
        ):
            if sum(values[field] for values in segment["classes"].values())!=reference[prior_field]:
                raise Refused("GP0 class totals differ from native ordinal VBlank audit")
        for klass,values in segment["classes"].items():
            for field in FIELDS:
                totals_by_class[klass][field]+=values[field]

    if sum(item["handlers"] for item in totals_by_class.values())!=strict["gp0_unai_handled"]:
        raise Refused("unaccounted native Unai dispatch")
    for field,prior_field in (
        ("changed_sample_points","changed_sample_points"),
        ("native_store_attempts","native_store_attempts"),
        ("same_value_native_stores","same_value_native_stores"),
        ("changed_value_native_stores","changed_value_native_stores"),
    ):
        if sum(item[field] for item in totals_by_class.values())!=prior["totals"][prior_field]:
            raise Refused("GP0 class-native store conservation failure")
    return {
        "scope":"pinned_pcsx_synthetic_unai_gp0_classes_only",
        "vblank_edges":4,
        "grouping":"native_callback_append_order_not_emulated_GPU_completion",
        "intervals":per_vblank,
        "class_totals":totals_by_class,
        "native_instrumented_store_attempts_observed":True,
        "gpu_state_command_store_attempts_refused":True,
        "complete_GPU_DMA_assembly_or_legacy_renderer_coverage":False,
        "physical_ps1_raster_timing_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:
        report=summarize(args.private_jsonl.read_bytes())
    except (OSError, UnicodeError, Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
