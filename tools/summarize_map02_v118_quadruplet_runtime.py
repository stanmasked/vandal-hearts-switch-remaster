#!/usr/bin/env python3
"""Fail-closed reconciliation of native four-handler exact sampled VRAM returns.

Actual sampled VRAM 16-bit values are compared only in the pinned native
Unai process. The strict private JSONL contains callback order, not pixels.
"""
import argparse
import json
import re
from pathlib import Path

from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v117_triplet_runtime import summarize as v117

FIELDS=("same_as_previous","returned_to_two_back",
        "returned_to_three_back","different_from_all_three")
PATTERN=re.compile(
    r"^VH118_QUADRUPLETS_PASS quads=(\d+) "+r" ".join(
        rf"g{i}=(\d+),(\d+),(\d+),(\d+)" for i in range(5)
    )+r"$",re.MULTILINE,
)


def summarize(log: str,raw: bytes):
    matches=PATTERN.findall(log)
    if len(matches)!=1:
        raise Refused("missing, duplicate or malformed native four-handler witness")
    counts=[int(x) for x in matches[0]]
    if any(x>0xffffffff for x in counts):
        raise Refused("native quadruplet aggregate outside uint32 range")
    claimed=counts[0]
    groups=[dict(vblank_edges_oldest_to_newest=i,
                 **dict(zip(FIELDS,counts[1+4*i:5+4*i])))
            for i in range(5)]
    older=v117(log,raw)
    records=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in records if r["kind"]=="vblank"]
    handlers=[r["seq"] for r in records if r["kind"]=="gp0_unai_handled"]
    if len(edges)!=4 or len(handlers)!=older["observed_unai_handlers"]:
        raise Refused("canonical VBlank/Unai event sequence mismatch")
    expected=[0]*5
    for i in range(3,len(handlers)):
        oldest,newest=handlers[i-3],handlers[i]
        gap=sum(oldest<vblank<newest for vblank in edges)
        if gap>4:
            raise Refused("unsupported four-handler VBlank span")
        expected[gap]+=1
    if claimed!=max(0,len(handlers)-3):
        raise Refused("missing native quadruplets")
    if claimed>older["native_three_callback_windows"]:
        raise Refused("quadruplet population exceeds verified triplets")
    for index,group in enumerate(groups):
        if sum(group[f] for f in FIELDS)!=expected[index]:
            raise Refused("four-handler native equality classified under wrong VBlank span")
    totals={field:sum(g[field] for g in groups) for field in FIELDS}
    if sum(totals.values())!=claimed:
        raise Refused("four-handler native sample observations are not conserved")
    return {
        "scope":"pinned_pcsx_synthetic_native_four_handler_exact_sample_returns",
        "observed_unai_handlers":len(handlers),
        "native_four_callback_windows":claimed,
        "bins_by_vblank_edges_oldest_to_newest":groups,
        "total_same_as_previous":totals["same_as_previous"],
        "total_return_to_two_back":totals["returned_to_two_back"],
        "total_return_to_three_back":totals["returned_to_three_back"],
        "total_different_from_all_three":totals["different_from_all_three"],
        "quadruplet_gap_counts_verified_against_original_private_trace":True,
        "native_v117_triplet_witness_reverified":True,
        "only_native_process_compares_actual_24_values":True,
        "raw_pixel_values_or_hashes_exported":False,
        "observed_return_not_entire_vram_persistence":True,
        "host_append_order_not_hardware_gpu_completion":True,
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
        output=summarize(args.private_runtime_log.read_text(),
                         args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as exc:
        p.exit(2,f"REFUSED: {exc}\n")
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
