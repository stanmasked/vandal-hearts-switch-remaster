#!/usr/bin/env python3
"""Independent v85 audit of actual Unai C++ pixel-store attempts by GP0 handler.

A counted same-value store really executed an assignment in a pinned instrumented
C++ inner loop. Uninstrumented assembly / DMA / old renderer are out of scope.
"""
import argparse
import json
from pathlib import Path
from .summarize_map02_v84_unai_samples import summarize as summarize_v84
from .verify_map02_v82_native_trace import Refused

def summarize(raw: bytes):
    previous=summarize_v84(raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    handlers=[(i,e) for i,e in enumerate(events) if e["kind"]=="gp0_unai_handled"]
    counts=[e for e in events if e["kind"]=="unai_store_count"]
    same=[e for e in events if e["kind"]=="unai_same_store_count"]
    if not handlers or len(handlers)!=len(counts) or len(handlers)!=len(same):
        raise Refused("missing native write observations")
    pairs=[]
    for index,evt in handlers:
        if index+3>=len(events):
            raise Refused("incomplete Unai 4-event sequence")
        group=events[index:index+4]
        if [e["kind"] for e in group]!=[
            "gp0_unai_handled","unai_sample_delta",
            "unai_store_count","unai_same_store_count"]:
            raise Refused("incorrect pairing of GPU handler, samples, writes, same-value writes")
        if group[2]["seq"]!=evt["seq"]+2 or group[3]["seq"]!=evt["seq"]+3:
            raise Refused("incorrect native store order")
        if group[3]["value"]>group[2]["value"]:
            raise Refused("same-value store count larger than all stores")
        pairs.append((evt["seq"],group[2]["value"],group[3]["value"]))
    attempts=sum(e[1] for e in pairs)
    unchanged=sum(e[2] for e in pairs)
    changed=attempts-unchanged
    if attempts==0 or unchanged==0 or changed==0:
        raise Refused("fixture did not exercise same and different value stores")
    before=[0,0,0];after=[0,0,0]
    edges=[e for e in events if e["kind"]=="vblank"]
    intervals=[]
    for a,b in zip(edges,edges[1:]):
        items=[x for x in pairs if a["seq"]<x[0]<b["seq"]]
        intervals.append({"from_frame":a["frame"],"to_frame":b["frame"],
            "handlers":len(items),
            "native_store_attempts":sum(x[1] for x in items),
            "same_value_stores":sum(x[2] for x in items)})
    return {
        "source":"pinned_pcsx_unai_instrumented_native_16bit_software_stores_synthetic_only",
        "gp0_handlers":len(pairs),
        "native_store_attempts":attempts,
        "native_stores_writing_previous_value":unchanged,
        "native_stores_writing_new_value":changed,
        "handlers_with_zero_observed_stores":sum(1 for p in pairs if p[1]==0),
        "between_emulator_vblanks":intervals,
        "sample_changed_handlers":previous["changed_handlers"],
        "sample_unchanged_handlers":previous["unchanged_handlers"],
        "same_color_writes_distinguished_within_instrumented_sites":True,
        "complete_unai_dma_asm_or_legacy_pixel_write_coverage":False,
        "physical_ps1_vblank_verified":False,
        "original_retail_MAP02_verified":False,
        "HD_replacement_approved":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try: report=summarize(args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as e:
        p.exit(2,f"REFUSED: {e}\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
