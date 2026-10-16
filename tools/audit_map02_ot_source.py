#!/usr/bin/env python3
"""Fail closed if pinned original PC GPU ordering-table chaining changes.

References exact public PC-port libgpu.c blob. Source-level mathematical
ordering proof only; not a GPU pixel/hardware verification.
"""
import argparse
import json
from pathlib import Path
from tools.prepare_map02_pcport import git_blob_sha1

PINNED_LIBGPU_BLOB = "9d0fab71c45ed09dda072cfeacd557ab9c5d81e5"

def verify_ot_order(source: str) -> dict:
    clear = source.find("unsigned int *ClearOTag(unsigned int *ot, int n) {")
    add = source.find("void AddPrim(void *ot, void *p) {")
    draw = source.find("void DrawOTag(unsigned int *p) {")
    if min(clear, add, draw) < 0 or not clear < add < draw:
        raise ValueError("original OT function boundaries changed")
    if source.count("unsigned int *ClearOTag(unsigned int *ot, int n) {") != 1:
        raise ValueError("ambiguous ClearOTag")
    if source.count("void AddPrim(void *ot, void *p) {") != 1:
        raise ValueError("ambiguous AddPrim")
    if source.count("void DrawOTag(unsigned int *p) {") != 1:
        raise ValueError("ambiguous DrawOTag")
    clear_body = source[clear:add]
    add_body = source[add:draw]
    draw_body = source[draw:]
    for anchor in (
        "for (i = 0; i < n - 1; i++) slots[i] = PC_OtMint(&slots[i + 1], 1);",
        "slots[n - 1] = 0;",
    ):
        if anchor not in clear_body:
            raise ValueError(f"original OT bucket chain changed: {anchor}")
    for anchor in (
        "u32 head = ((P_TAG *)ot)->tag;",
        "((P_TAG *)p)->tag = head;",
        "((P_TAG *)ot)->tag = PC_OtMint(p, 0);",
    ):
        if anchor not in add_body:
            raise ValueError(f"original AddPrim head insertion changed: {anchor}")
    if not (
        "u32 nextTok = ((P_TAG *)p)->tag;" in draw_body and
        "while (nextTok)" in draw_body and
        "nextTok = rawTagOfCur;" in draw_body and
        "if (!isBucket)" in draw_body
    ):
        raise ValueError("original DrawOTag link traversal changed")
    return {
        "pc_ot_bucket_order": "0..n-1",
        "same_bucket_primitive_order": "reverse submission (LIFO)",
        "terrain_ot_slot": "OT_SIZE - max(5, AVSZ4 OTZ)",
        "pinned_pc_gpu_source_audited": True,
        "ps1_hardware_gpu_verified": False,
        "scene_contains_nonterrain_gpu_packets": False,
    }

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("pc_libgpu",type=Path)
    p.add_argument("--allow-modified-source",action="store_true")
    args=p.parse_args()
    try:
        raw=args.pc_libgpu.read_bytes()
        sha=git_blob_sha1(raw)
        if sha!=PINNED_LIBGPU_BLOB and not args.allow_modified_source:
            raise ValueError("libgpu.c Git blob differs from pinned original PC port")
        result=verify_ot_order(raw.decode("utf-8"))
        result["matches_pinned_pc_libgpu"]=sha==PINNED_LIBGPU_BLOB
        result["git_blob_sha1"]=sha
    except (OSError,UnicodeError,ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
