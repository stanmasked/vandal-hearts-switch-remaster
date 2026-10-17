#!/usr/bin/env python3
"""Strict five-handler native VRAM sample equality versus canonical VBlank order."""
import argparse
import json
import re
from pathlib import Path

from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v118_quadruplet_runtime import summarize as v118

FIELDS=("same_as_previous","returned_to_two_back",
        "returned_to_three_back","returned_to_four_back",
        "different_from_all_four")
PATTERN=re.compile(
    r"^VH119_QUINTUPLETS_PASS quints=(\d+) "+r" ".join(
        rf"g{i}=(\d+),(\d+),(\d+),(\d+),(\d+)" for i in range(5)
    )+r"$",re.MULTILINE,
)


def summarize(log: str,raw: bytes):
    found=PATTERN.findall(log)
    if len(found)!=1:
        raise Refused("missing, duplicate or malformed native five-handler witness")
    numbers=[int(x) for x in found[0]]
    if any(n>0xffffffff for n in numbers):
        raise Refused("native quintuplet counter outside uint32 range")
    claimed=numbers[0]
    buckets=[
        dict(vblank_edges_oldest_to_newest=i,
             **dict(zip(FIELDS,numbers[1+5*i:6+5*i])))
        for i in range(5)
    ]
    older=v118(log,raw)
    events=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in events if r["kind"]=="vblank"]
    handlers=[r["seq"] for r in events if r["kind"]=="gp0_unai_handled"]
    if len(edges)!=4 or len(handlers)!=older["observed_unai_handlers"]:
        raise Refused("canonical Unai/VBlank event totals differ from v118")
    expected=[0]*5
    for i in range(4,len(handlers)):
        start,end=handlers[i-4],handlers[i]
        gap=sum(start<edge<end for edge in edges)
        if gap>4:
            raise Refused("more than four VBlank callbacks in native quintuplet")
        expected[gap]+=1
    if claimed!=max(0,len(handlers)-4):
        raise Refused("native five-handler observation count not conserved")
    if claimed>older["native_four_callback_windows"]:
        raise Refused("native quintuplet population exceeds v118 windows")
    for index,bucket in enumerate(buckets):
        if sum(bucket[f] for f in FIELDS)!=expected[index]:
            raise Refused("five-handler native state classified in wrong VBlank gap")
    sums={f:sum(b[f] for b in buckets) for f in FIELDS}
    if sum(sums.values())!=claimed:
        raise Refused("five-handler state outcome counts are not exhaustive")
    return {
        "scope":"pinned_pcsx_synthetic_bounded_native_five_handler_value_returns",
        "observed_unai_handlers":len(handlers),
        "native_five_callback_windows":claimed,
        "bins_by_vblank_edges_oldest_to_newest":buckets,
        "total_same_as_previous":sums["same_as_previous"],
        "total_return_to_two_back":sums["returned_to_two_back"],
        "total_return_to_three_back":sums["returned_to_three_back"],
        "total_return_to_four_back":sums["returned_to_four_back"],
        "total_different_from_all_four":sums["different_from_all_four"],
        "quintuplet_gap_counts_verified_against_original_private_trace":True,
        "native_v118_four_handler_witness_reverified":True,
        "native_previous_samples_bounded_to_four_24_value_buffers":True,
        "actual_sample_values_compared_inside_native_process_only":True,
        "raw_pixel_values_or_hashes_exported":False,
        "observed_return_not_full_vram_persistence":True,
        "callback_append_order_not_ps1_gpu_completion":True,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("private_runtime_log",type=Path)
    p.add_argument("private_jsonl",type=Path)
    args=p.parse_args()
    try:
        report=summarize(args.private_runtime_log.read_text(),
                         args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
