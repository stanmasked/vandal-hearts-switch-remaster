#!/usr/bin/env python3
"""Strict, privacy-preserving MAP02 source-face -> native PC GPU FT4 packet join.

Requires TWO separately verified private inputs:
  * an original-format decoded MAP02 + source/GTE/VRAM bundle;
  * an opt-in native PC GPU DrawOTag before/after VRAM capture.
The two frame counters are different clocks. An explicit, SHA-bound
user assertion binds them; equality is NEVER assumed or guessed.

A link is accepted only if its GPU XY (0,1,3,2), every UV, tpage,
CLUT and the full active texture window match exactly, there are no
ambiguous duplicates, and the input source/palette VRAM words relevant
to the face agree with the VRAM snapshot before its GPU draw.
No asset bytes, colors, camera values or source locations are output.
This is a *consistency check*, not authentication of retail gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import (
    MAX_FACES, fields, number, parse_json, safe_file_max, sha_check,
    verify_bundle,
)
from tools.verify_map02_native_gpu_capture import (
    LOG as NATIVE_LOG, private_file, verify_capture, VRAM_BYTES,
)
from tools.verify_map02_vram_timeline import (
    EVENT_LIMIT, read_events, referenced_words, verify_timeline,
)

SCHEMA = "vh.map02.source-native-ft4-join.v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source_signature(event):
    corners = event["gte"]["perimeter_xy"]
    t = event["texture"]
    u, v, w, h = (t["u"], t["v"], t["w"], t["h"])
    xy = [coordinate for index in (0, 1, 3, 2)
          for coordinate in corners[index]]
    uv = [u, v, u+w, v, u, v+h, u+w, v+h]
    window = [t["mask_x"], t["mask_y"], t["offset_x"], t["offset_y"]]
    return xy, uv, t["tpage"], t["clut"], window


def _native_signature(event):
    packet = event["ft4"]
    if event["operation"] != "draw" or packet is None:
        return None
    return (packet["xy"], packet["uv"], packet["tpage"],
            packet["clut"], event["window"])


def _material_bytes_equal(source, before, event):
    """Compare every 16-bit source word that either VRAM source samples.

    The output-frame pixels may legitimately differ due to earlier
    primitives; do not compare whole render-target VRAM with a frozen
    texture reference. If a different texel index selects a different
    CLUT entry, the union of both palettes is checked too.
    """
    texture_a, palette_a = referenced_words(event, source)
    texture_b, palette_b = referenced_words(event, before)
    addresses = texture_a | texture_b | palette_a | palette_b
    for word in addresses:
        offset = word * 2
        if source[offset:offset+2] != before[offset:offset+2]:
            return False, len(addresses)
    return True, len(addresses)


def _verified_native_draw_packets(native_events):
    """Return only FT4 draws with internally stable per-primitive GPU state."""
    gpu_draw_events = []
    for i in range(0, len(native_events), 2):
        before, after = native_events[i:i+2]
        if _native_signature(before) is None:
            continue
        # A DR_MODE primitive may change GPU state; an individual FT4 must
        # not change its texture/window registers between before and after.
        if (before["window"] != after["window"] or
                before["draw_mode"] != after["draw_mode"]):
            raise ValueError("native FT4 texture/draw state changed during primitive")
        gpu_draw_events.append(before)
    return gpu_draw_events


def _unique_ft4_matches(source_events, native_ft4):
    """Match exact packets without assuming order or inventing source keys."""
    if not native_ft4:
        raise ValueError("native capture has no FT4 draw packets")
    source_signatures = [_source_signature(e) for e in source_events]
    draw_signatures = [_native_signature(e) for e in native_ft4]
    selected = []
    for face_index, sig in enumerate(source_signatures):
        matches = [i for i, candidate in enumerate(draw_signatures)
                   if sig == candidate]
        if not matches:
            raise ValueError(
                f"source face event {face_index}: no exact GPU FT4 geometry/UV/page/CLUT/window match")
        if len(matches) != 1:
            raise ValueError(
                f"source face event {face_index}: ambiguous GPU FT4 packets ({len(matches)})")
        selected.append(matches[0])
    if len(set(selected)) != len(selected):
        raise ValueError("one GPU FT4 packet matches multiple source-keyed MAP02 faces")
    return selected


def verify_join(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    manifest_raw = safe_file_max(source_dir, "gpu-face-join.json", 64*1024)
    manifest = parse_json(manifest_raw, "gpu-face-join.json")
    fields(manifest, (
        "schema", "source_frame", "gpu_draw_frame",
        "bundle_manifest_sha256", "native_events_sha256",
    ), "source/native mapping")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unsupported source/native join schema")
    source_frame = number(manifest["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(manifest["gpu_draw_frame"], "native GPU frame", 1, 2**32-1)
    bundle_raw = private_file(source_dir, "bundle.json", max_bytes=64*1024)
    log_raw = private_file(native_dir, NATIVE_LOG, max_bytes=128*1024)
    sha_check(bundle_raw, manifest["bundle_manifest_sha256"], "source manifest")
    sha_check(log_raw, manifest["native_events_sha256"], "native GPU event log")

    # Do not match unverified source geometry or a damaged GPU capture.
    source_report = verify_bundle(source_dir, compiler=compiler)
    native_report = verify_capture(native_dir, target_frame=gpu_frame)
    if source_report["frame"] != source_frame:
        raise ValueError("declared source frame differs from verified bundle")
    if native_report["frame"] != gpu_frame:
        raise ValueError("declared native frame differs from verified capture")
    if native_report["record_cap_reached"]:
        raise ValueError("native trace exhausted its 64-record cap; cannot make exhaustive join")
    if source_report["submitted_faces_checked"] > MAX_FACES:
        raise ValueError("too many source faces")
    source_events = [
        parse_json(line, f"source event {i}")
        for i, line in enumerate(
            private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024).splitlines())
    ]
    native_events = [
        parse_json(line, f"GPU event {i}")
        for i, line in enumerate(log_raw.splitlines())
    ]
    # Every before/after pair has already passed source-native validation.
    gpu_draw_events = _verified_native_draw_packets(native_events)
    selected = _unique_ft4_matches(source_events, gpu_draw_events)

    reference = private_file(source_dir, "gpu-vram-le.bin", expected=VRAM_BYTES)
    material_words_checked = 0
    for face_index, match_index in enumerate(selected):
        native = gpu_draw_events[match_index]
        snapshot = private_file(native_dir, native["snapshot"], expected=VRAM_BYTES)
        equal, word_count = _material_bytes_equal(
            reference, snapshot, source_events[face_index])
        if not equal:
            raise ValueError(
                f"source face event {face_index}: texture or CLUT words differ "
                "from native VRAM immediately before primitive")
        material_words_checked += word_count

    # The draw walk is not in source submission order; no attempt to sort
    # by source index, material, depth, position or replay guessed OT order.
    return {
        "join_manifest_sha256": sha(manifest_raw),
        "source_bundle_manifest_sha256": sha(bundle_raw),
        "native_gpu_event_log_sha256": sha(log_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "source_face_count": len(source_events),
        "native_gpu_ft4_packets": len(gpu_draw_events),
        "uniquely_matched_source_faces": len(selected),
        "material_vram_words_compared": material_words_checked,
        "screen_corners_uv_page_clut_window_exact": True,
        "source_gte_verified_by_compiled_reference": True,
        "native_before_after_capture_verified": True,
        "source_to_gpu_frame_binding_authenticated": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_raster_pixels_verified": False,
        "raw_game_data_emitted": False,
    }



TIMELINE_JOIN_SCHEMA = "vh.map02.source-native-ft4-timeline-join.v1"


def verify_timeline_join(source_dir, native_dir, *, compiler="gcc"):
    """Bind independently audited multi-VRAM source submissions to native FT4.

    The source/GTE submission frame and native DrawOTag frame are DIFFERENT
    clocks. Require an explicit user-authored SHA-bound mapping; do not infer
    frame equality, OT execution order, or GPU rasterization identity.
    Each source face's own snapshot (not a frame-wide VRAM image) is compared
    to the native GPU's pre-draw texture/CLUT words.
    """
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    raw_manifest = safe_file_max(source_dir, "gpu-face-timeline-join.json", 64*1024)
    mapping = parse_json(raw_manifest, "gpu-face-timeline-join.json")
    fields(mapping, ("schema", "source_frame", "gpu_draw_frame",
                     "timeline_manifest_sha256", "native_events_sha256"),
           "source/native timeline mapping")
    if mapping["schema"] != TIMELINE_JOIN_SCHEMA:
        raise ValueError("unsupported source/native timeline join schema")
    source_frame = number(mapping["source_frame"], "source frame", 1, 2**32-1)
    native_frame = number(mapping["gpu_draw_frame"], "GPU draw frame", 1, 2**32-1)
    timeline_raw = private_file(source_dir, "timeline.json", max_bytes=64*1024)
    native_raw = private_file(native_dir, NATIVE_LOG, max_bytes=128*1024)
    sha_check(timeline_raw, mapping["timeline_manifest_sha256"], "timeline manifest")
    sha_check(native_raw, mapping["native_events_sha256"], "native GPU log")

    timeline_report = verify_timeline(source_dir, compiler=compiler)
    native_report = verify_capture(native_dir, target_frame=native_frame)
    if timeline_report["frame"] != source_frame:
        raise ValueError("mapped source frame differs from verified timeline")
    if native_report["frame"] != native_frame:
        raise ValueError("mapped native frame differs from verified capture")
    if native_report["record_cap_reached"]:
        raise ValueError("native capture exhausted 64-record limit; incomplete")

    source_events = read_events(private_file(
        source_dir, "gpu-events.jsonl", max_bytes=EVENT_LIMIT))
    native_events = [parse_json(line, f"GPU event {i}")
                     for i, line in enumerate(native_raw.splitlines())]
    native_ft4 = _verified_native_draw_packets(native_events)
    selected = _unique_ft4_matches(source_events, native_ft4)

    compared = 0
    for source_index, native_index in enumerate(selected):
        reference = private_file(
            source_dir, f"gpu-vram-{source_index:03d}.bin", expected=VRAM_BYTES)
        before = private_file(
            native_dir, native_ft4[native_index]["snapshot"],
            expected=VRAM_BYTES)
        matched, count = _material_bytes_equal(
            reference, before, source_events[source_index])
        if not matched:
            raise ValueError(
                f"source submission {source_index}: texture or CLUT words differ "
                "from native VRAM immediately before primitive")
        compared += count

    return {
        "timeline_join_manifest_sha256": sha(raw_manifest),
        "source_timeline_manifest_sha256": sha(timeline_raw),
        "native_gpu_event_log_sha256": sha(native_raw),
        "source_frame": source_frame,
        "native_gpu_frame": native_frame,
        "source_submissions_verified": len(source_events),
        "native_ft4_packets": len(native_ft4),
        "uniquely_matched_source_faces": len(selected),
        "per_submission_vram_snapshots_compared": len(selected),
        "material_vram_words_compared": compared,
        "screen_corners_uv_page_clut_window_exact": True,
        "pc_gte_source_timeline_verified": True,
        "native_gpu_capture_verified": True,
        "source_gpu_frames_assumed_same": False,
        "draw_execution_order_assumed": False,
        "native_stream_authenticated_complete": False,
        "source_to_gpu_frame_binding_authenticated": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_raster_pixels_verified": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_gpu_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    p.add_argument("--timeline", action="store_true",
                   help="use per-submission VRAM timeline and SHA-bound "
                        "gpu-face-timeline-join.json instead of a single frame bundle")
    args = p.parse_args()
    try:
        if args.timeline:
            report = verify_timeline_join(
                args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
        else:
            report = verify_join(
                args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
