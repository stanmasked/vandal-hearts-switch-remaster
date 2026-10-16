#!/usr/bin/env python3
"""Check claimed AddPrim submission order against real-format DrawOTag traversal.

This is an offline consistency gate for user-owned, independently verified
source and GPU traces. Manifest assertions about submission chronology and
shared OT identity are NOT authenticated, and capture completeness is not
proven. Existing source/GTE/VRAM packet checks must pass first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import (
    fields, number, parse_json, safe_file_max, sha_check,
)
from tools.verify_map02_native_gpu_capture import LOG, private_file
from tools.verify_map02_source_native_ft4_join import (
    _native_signature, _source_signature, verify_join,
)

SCHEMA = "vh.map02.source-native-ot-order.v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def expected_addprim_draw_indices(source_events, ot_size):
    """Order source-event indices as pinned ClearOTag/AddPrim/DrawOTag.

    Buckets are traversed from low to high; AddPrim inserts at the head.
    Hence the lower OT slot (higher depth) draws first, with same-bucket
    source events in REVERSE claimed submission order.
    """
    if type(source_events) is not list or not source_events:
        raise ValueError("no source faces for OT ordering")
    number(ot_size, "ordering-table size", 5, 4096)
    slots = []
    for i, event in enumerate(source_events):
        if type(event) is not dict or type(event.get("gte")) is not dict:
            raise ValueError("missing original GTE depth")
        depth = number(event["gte"].get("raw_otz"), "AVSZ4 raw OTZ", 0, 65535)
        depth = max(5, depth)
        if depth > ot_size:
            raise ValueError("face depth outside ordering table")
        slots.append((ot_size-depth, -i, i))
    return [item[2] for item in sorted(slots)]


def _bbox_overlap_candidates(source_events):
    """Only AABB intersection, NOT exact FT4 polygon coverage/overdraw."""
    boxes = []
    for event in source_events:
        xy = event["gte"]["perimeter_xy"]
        x = [p[0] for p in xy]
        y = [p[1] for p in xy]
        boxes.append((min(x), min(y), max(x), max(y)))
    overlapping = 0
    same_bucket_overlap = 0
    for a in range(len(boxes)):
        for b in range(a+1, len(boxes)):
            xa, ya, xb, yb = boxes[a]
            xc, yc, xd, yd = boxes[b]
            if max(xa, xc) < min(xb, xd) and max(ya, yc) < min(yb, yd):
                overlapping += 1
                if max(5, source_events[a]["gte"]["raw_otz"]) == max(
                    5, source_events[b]["gte"]["raw_otz"]
                ):
                    same_bucket_overlap += 1
    return overlapping, same_bucket_overlap


def verify_ot_join(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    manifest_raw = safe_file_max(source_dir, "gpu-ot-order-join.json", 64*1024)
    m = parse_json(manifest_raw, "gpu-ot-order-join.json")
    fields(m, (
        "schema", "source_frame", "gpu_draw_frame", "face_join_manifest_sha256",
        "source_events_sha256", "native_events_sha256",
        "source_events_in_addprim_order", "one_clear_otag_one_draw_otag",
    ), "source-to-GPU OT claims")
    if m["schema"] != SCHEMA:
        raise ValueError("unknown source-to-native OT manifest schema")
    if m["source_events_in_addprim_order"] is not True:
        raise ValueError("source AddPrim chronology must be asserted explicitly")
    if m["one_clear_otag_one_draw_otag"] is not True:
        raise ValueError("single ClearOTag/DrawOTag pass must be asserted explicitly")
    src_frame = number(m["source_frame"], "source game frame", 1, 2**32-1)
    gpu_frame = number(m["gpu_draw_frame"], "native GPU frame", 1, 2**32-1)
    join_raw = private_file(source_dir, "gpu-face-join.json", max_bytes=64*1024)
    source_raw = private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024)
    native_raw = private_file(native_dir, LOG, max_bytes=128*1024)
    sha_check(join_raw, m["face_join_manifest_sha256"], "source/native face join")
    sha_check(source_raw, m["source_events_sha256"], "source AddPrim event log")
    sha_check(native_raw, m["native_events_sha256"], "native DrawOTag event log")

    # Repeat the independent whole-file, native-packet and original-GTE/VRAM
    # checks first. Never assert an OT match on unverifiable data.
    checked = verify_join(source_dir, native_dir, compiler=compiler)
    if checked["source_frame"] != src_frame or checked["native_gpu_frame"] != gpu_frame:
        raise ValueError("claimed OT pass frame binding differs from verified join")

    source_events = [
        parse_json(line, f"source AddPrim event {i}")
        for i, line in enumerate(source_raw.splitlines())
    ]
    gpu_events = [
        parse_json(line, f"native GPU event {i}")
        for i, line in enumerate(native_raw.splitlines())
    ]
    native_draws = [
        gpu_events[i] for i in range(0, len(gpu_events), 2)
        if _native_signature(gpu_events[i]) is not None
    ]
    # verify_join established a 1:1 unique match. Reconstruct its
    # source->observed-draw mapping without using guessed GFX/OT depth.
    native_sig = [_native_signature(e) for e in native_draws]
    source_positions = []
    for index, ev in enumerate(source_events):
        match = [i for i, sig in enumerate(native_sig) if sig == _source_signature(ev)]
        if len(match) != 1:
            raise ValueError(f"source face event {index}: ambiguous or absent FT4")
        source_positions.append(match[0])
    ot_manifest = parse_json(
        private_file(source_dir, "bundle.json", max_bytes=64*1024),
        "bundle manifest",
    )
    ot_size = number(ot_manifest["ot_size"], "source OT size", 5, 4096)
    expected = expected_addprim_draw_indices(source_events, ot_size)
    actual = sorted(range(len(source_events)), key=lambda i: source_positions[i])
    if actual != expected:
        raise ValueError(
            "native DrawOTag terrain subsequence violates "
            "claimed source AddPrim OT depth/LIFO order"
        )

    depth = [max(5, ev["gte"]["raw_otz"]) for ev in source_events]
    same_slot_pairs = sum(depth[i] == depth[j]
                          for i in range(len(depth))
                          for j in range(i+1, len(depth)))
    cross_slot_pairs = len(depth)*(len(depth)-1)//2 - same_slot_pairs
    aabb_pairs, overlap_same_depth = _bbox_overlap_candidates(source_events)
    return {
        "ot_join_manifest_sha256": digest(manifest_raw),
        "verified_face_join_manifest_sha256": digest(join_raw),
        "source_addprim_log_sha256": digest(source_raw),
        "native_drawotag_log_sha256": digest(native_raw),
        "source_frame": src_frame,
        "native_gpu_frame": gpu_frame,
        "terrain_faces_with_verified_relative_ot_order": len(source_events),
        "same_ot_bucket_order_pairs_checked": same_slot_pairs,
        "different_ot_bucket_order_pairs_checked": cross_slot_pairs,
        "screen_aabb_overlap_candidates": aabb_pairs,
        "same_ot_bucket_aabb_overlap_candidates": overlap_same_depth,
        "intervening_unmatched_ft4_packets": len(native_draws)-len(source_events),
        "source_to_gpu_ft4_and_vram_join_verified": True,
        "pc_ot_bucket_forward_lifo_model_applied": True,
        "source_addprim_order_authenticated": False,
        "single_ot_pass_authenticated": False,
        "all_drawotag_packets_source_keyed": False,
        "exact_pixel_overdraw_verified": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_pixels_verified": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_gpu_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    args = p.parse_args()
    try:
        report = verify_ot_join(args.source_bundle, args.native_gpu_capture,
                                compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
