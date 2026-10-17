#!/usr/bin/env python3
"""Bind native exact 24-value A-B-A witness to trusted Unai/VBlank order.

The private JSONL contains only event metadata and readback change counts,
never actual sampled 16-bit values. Only the native C sidecar can determine
exact-value equality. Public data are non-identifying class counts.
"""
import argparse
import json
import re
from pathlib import Path

from .verify_map02_v82_native_trace import Refused
from .summarize_map02_v116_gap_identity_runtime import summarize as v116

FIELDS=("same_as_previous","returned_to_two_back","different_from_both")
PATTERN=re.compile(
    r"^VH117_TRIPLETS_PASS triples=(\d+) "+r" ".join(
        rf"g{i}=(\d+),(\d+),(\d+)" for i in range(5)
    )+r"$",re.MULTILINE,
)


def summarize(log: str,raw: bytes):
    found=PATTERN.findall(log)
    if len(found)!=1:
        raise Refused("missing, duplicate or truncated native 3-handler identity witness")
    counts=[int(x) for x in found[0]]
    if any(x>0xffffffff for x in counts):
        raise Refused("native sampled-state return counter out of uint32 range")
    claimed=counts[0]
    bins=[dict(vblank_edges_oldest_to_newest=k,
               **dict(zip(FIELDS,counts[1+3*k:4+3*k])))
          for k in range(5)]

    older=v116(log,raw)
    rows=[json.loads(line) for line in raw.decode("ascii").splitlines()]
    edges=[r["seq"] for r in rows if r["kind"]=="vblank"]
    handlers=[r["seq"] for r in rows if r["kind"]=="gp0_unai_handled"]
    if len(edges)!=4 or len(handlers)!=older["observed_unai_handlers"]:
        raise Refused("original private Unai/VBlank event population mismatch")
    expected=[0]*5
    for index in range(2,len(handlers)):
        before=handlers[index-2]
        after=handlers[index]
        gap=sum(before<edge<after for edge in edges)
        if gap>4:
            raise Refused("more than four VBlank callbacks between observed triples")
        expected[gap]+=1
    if claimed!=max(0,len(handlers)-2):
        raise Refused("native triplet count cannot reconcile with private handler count")
    for i,bin_ in enumerate(bins):
        if sum(bin_[field] for field in FIELDS)!=expected[i]:
            raise Refused("exact-value three-handler classification assigned to wrong VBlank gap")
    if sum(sum(bin_[field] for field in FIELDS) for bin_ in bins)!=claimed:
        raise Refused("lost three-handler native value observations")
    return {
        "scope":"pinned_pcsx_synthetic_native_three_handler_sample_value_return",
        "observed_unai_handlers":len(handlers),
        "native_three_callback_windows":claimed,
        "bins_by_vblank_edges_oldest_to_newest":bins,
        "exact_return_to_two_back_total":sum(
            b["returned_to_two_back"] for b in bins),
        "exact_same_as_previous_total":sum(
            b["same_as_previous"] for b in bins),
        "exact_different_from_both_total":sum(
            b["different_from_both"] for b in bins),
        "gap_totals_checked_against_canonical_private_event_order":True,
        "source_v116_exact_adjacent_sample_equality_revalidated":True,
        "only_native_process_compares_actual_24_values":True,
        "raw_pixel_values_and_hashes_exported":False,
        "three_handler_return_does_not_prove_whole_vram_persistence":True,
        "host_callback_order_not_ps1_gpu_completion":True,
        "original_retail_MAP02_verified":False,
        "physical_PS1_verified":False,
        "HD_replacement_approved":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("private_runtime_log",type=Path)
    parser.add_argument("private_jsonl",type=Path)
    args=parser.parse_args()
    try:
        result=summarize(args.private_runtime_log.read_text(),
                         args.private_jsonl.read_bytes())
    except (OSError,UnicodeError,Refused) as err:
        parser.exit(2,f"REFUSED: {err}\n")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
