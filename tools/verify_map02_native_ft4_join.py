#!/usr/bin/env python3
"""Bounded private join: source-keyed MAP02 FT4 submissions vs native PC GPU FT4.

The original PC renderer can draw primitives in reverse OT bucket order, so
matching is one-to-one by *complete observed FT4 packet*, never by position in
a guessed event stream. Both source/GTE/VRAM timeline and native GPU snapshot
capture are independently verified first. Ambiguous or missing matches fail.

A successful join confirms agreement between caller-supplied observations,
not that they came from the original game. No raw pixels, faces, GPU
coordinates or texture register values are emitted in the report.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_frame_bundle import parse_json, safe_file_max, number
from tools.verify_map02_vram_timeline import (
    EVENT_LIMIT, read_events, verify_timeline,
)
from tools.verify_map02_native_gpu_capture import (
    LOG, MAX_EVENT_BYTES, private_file, verify_capture,
)


def signature_source(event):
    """FT4 hardware corner order x0/x1/x2/x3 = perimeter 0/1/3/2."""
    corners = event["gte"]["perimeter_xy"]
    tex = event["texture"]
    u, v, w, h = (tex[k] for k in ("u", "v", "w", "h"))
    gpu_xy = tuple(axis for i in (0, 1, 3, 2) for axis in corners[i])
    uv = (u, v, u + w, v, u, v + h, u + w, v + h)
    window = tuple(tex[k] for k in
                   ("mask_x", "mask_y", "offset_x", "offset_y"))
    return (tuple(gpu_xy), tuple(uv), tex["tpage"], tex["clut"], window)


def signature_native(event):
    q = event["ft4"]
    return (tuple(q["xy"]), tuple(q["uv"]), q["tpage"], q["clut"],
            tuple(event["window"]))


def verify_native_ft4_join(
    timeline_dir: Path, native_dir: Path, *, compiler="gcc", header=None,
):
    timeline_dir = Path(timeline_dir).absolute()
    native_dir = Path(native_dir).absolute()
    args = {"compiler": compiler}
    if header is not None:
        args["header"] = header
    # Validate original source keys, GTE, each VRAM hash and actual crops
    # before examining untrusted native GPU event metadata.
    timeline = verify_timeline(timeline_dir, **args)
    frame = number(timeline["frame"], "MAP02 frame", 1, 2**32 - 1)
    native = verify_capture(native_dir, target_frame=frame)
    if native["record_cap_reached"]:
        raise ValueError("native GPU capture reached its event cap; incomplete")
    if native["draw_otag_primitive_pairs"] < timeline["submitted_faces_checked"]:
        raise ValueError("native DrawOTag captured fewer primitives than MAP02 submissions")

    source_raw = safe_file_max(timeline_dir, "gpu-events.jsonl", EVENT_LIMIT)
    source_events = read_events(source_raw)
    native_raw = private_file(native_dir, LOG, max_bytes=MAX_EVENT_BYTES)
    native_events = [parse_json(line, f"native FT4 {i}")
                     for i, line in enumerate(native_raw.splitlines())]
    native_ft4 = []
    for index in range(0, len(native_events), 2):
        before, after = native_events[index:index + 2]
        if before["operation"] != "draw" or before["ft4"] is None:
            continue
        # verify_capture checks paired geometry metadata; also require stable
        # texture/draw state, which is not part of its general pair contract.
        if (before["window"] != after["window"] or
                before["draw_mode"] != after["draw_mode"]):
            raise ValueError("native FT4 before/after GPU texture state changed")
        native_ft4.append(signature_native(before))

    if not native_ft4:
        raise ValueError("native capture does not contain FT4 packets")
    found = set()
    for source in source_events:
        sig = signature_source(source)
        matching = [index for index, item in enumerate(native_ft4)
                    if sig == item]
        if not matching:
            raise ValueError("source-keyed MAP02 FT4 absent from native GPU capture")
        if len(matching) != 1 or matching[0] in found:
            raise ValueError("ambiguous native FT4 packet; cannot attribute source face")
        found.add(matching[0])

    # This join intentionally permits extra native FT4 packets belonging to
    # other game objects. It does NOT establish that the complete draw stream
    # was captured (even below the hard recording cap).
    return {
        "frame": frame,
        "pc_source_commit": timeline["pc_source_commit"],
        "source_timeline_manifest_sha256": timeline["timeline_manifest_sha256"],
        "source_events_sha256": timeline["events_sha256"],
        "native_gpu_events_sha256": native["native_gpu_events_sha256"],
        "source_ft4_submissions_checked": len(source_events),
        "native_ft4_packets_observed": len(native_ft4),
        "one_to_one_packets_matched": len(found),
        "unmatched_native_ft4_packets": len(native_ft4) - len(found),
        "native_capture_cap_reached": False,
        "native_draw_order_assumed": False,
        "native_gpu_stream_proven_complete": False,
        "source_face_attribution_authenticated": False,
        "retail_ps1_pixels_verified": False,
        "raw_game_data_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeline_directory", type=Path)
    parser.add_argument("native_gpu_directory", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = verify_native_ft4_join(
            args.timeline_directory, args.native_gpu_directory,
            compiler=args.compiler)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
