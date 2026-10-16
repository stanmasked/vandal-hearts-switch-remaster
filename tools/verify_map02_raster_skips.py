#!/usr/bin/env python3
"""Validate native PC raster *executed* zero-texel/clip skip events.

Each event comes from the exact branch in the original source-instrumented
PC rasterizer and carries the live DrawOTag frame/ordinal/type. Re-check
the private source-keyed MAP02→GTE→GPU→VRAM→OTZ overdraw evidence
before attributing to a source terrain FT4. Do not infer why unlogged
pixels were skipped. This is not physical PS1 mask/clip emulation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import LOG, private_file
from tools.verify_map02_native_overdraw import verify_native_overdraw
from tools.verify_map02_source_native_ft4_join import _source_signature, _native_signature

SCHEMA = "vh.map02.native-raster-skip.v1"
SKIP_LOG = "putpixel-native-skips.jsonl"
EVENT_FIELDS = ("stage", "step", "frame", "primitive_ordinal",
                "primitive_type", "x", "y", "reason")
MAX_RECORDS = 64


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_skips(source_dir, native_dir, *, compiler="gcc"):
    source_dir, native_dir = Path(source_dir).absolute(), Path(native_dir).absolute()
    manifest_raw = private_file(source_dir, "gpu-raster-skips.json", max_bytes=64*1024)
    m = parse_json(manifest_raw, "gpu-raster-skips.json")
    fields(m, ("schema", "source_frame", "gpu_draw_frame",
               "overdraw_manifest_sha256", "native_events_sha256",
               "raster_skip_events_sha256"), "raster skip manifest")
    if m["schema"] != SCHEMA:
        raise ValueError("unexpected native raster skip schema")
    source_frame = number(m["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(m["gpu_draw_frame"], "native DrawOTag frame", 1, 2**32-1)
    overdraw_raw = private_file(source_dir, "gpu-native-overdraw.json", max_bytes=64*1024)
    native_raw = private_file(native_dir, LOG, max_bytes=128*1024)
    skip_raw = private_file(native_dir, SKIP_LOG, max_bytes=16*1024)
    sha_check(overdraw_raw, m["overdraw_manifest_sha256"], "source-keyed overdraw")
    sha_check(native_raw, m["native_events_sha256"], "native GPU event sequence")
    sha_check(skip_raw, m["raster_skip_events_sha256"], "native raster skip log")

    checked = verify_native_overdraw(source_dir, native_dir, compiler=compiler)
    if checked["source_frame"] != source_frame or checked["native_gpu_frame"] != gpu_frame:
        raise ValueError("raster skip frame labels disagree with verified original FT4")
    source_raw = private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024)
    src = [parse_json(line, "MAP02 source face") for line in source_raw.splitlines()]
    source_sigs = [_source_signature(e) for e in src]
    native = [parse_json(line, "native DrawOTag event") for line in native_raw.splitlines()]
    draw_packets = [native[i] for i in range(0, len(native), 2)
                    if native[i]["operation"] == "draw"]
    source_ordinals = {
        ordinal for ordinal, e in enumerate(draw_packets)
        if _native_signature(e) in source_sigs
    }
    if len(source_ordinals) != len(src):
        raise ValueError("not every source MAP02 FT4 has a unique DrawOTag ordinal")
    rows = skip_raw.splitlines()
    if not 1 <= len(rows) < MAX_RECORDS or any(not line.strip() for line in rows):
        raise ValueError("raster skip log empty, incomplete, or at record cap")
    sampled_xy = None
    last_ordinal = -1
    counts = {1: 0, 2: 0, 3: 0}
    source_counts = {1: 0, 2: 0, 3: 0}
    source_primitive_ordinals = set()
    for i, line in enumerate(rows):
        e = parse_json(line, f"native raster skip {i}")
        fields(e, EVENT_FIELDS, f"native raster skip {i}")
        if e["stage"] != "native_raster_skip":
            raise ValueError("not a native PC raster branch event")
        if number(e["step"], "raster skip index", 0, MAX_RECORDS-1) != i:
            raise ValueError("raster skip steps are not contiguous")
        if number(e["frame"], "raster skip GPU frame", 1, 2**32-1) != gpu_frame:
            raise ValueError("raster skip belongs to another DrawOTag frame")
        ordinal = number(e["primitive_ordinal"], "primitive ordinal",
                         0, len(draw_packets)-1)
        if ordinal < last_ordinal:
            raise ValueError("raster skip primitive order decreased")
        last_ordinal = ordinal
        observed_type = number(e["primitive_type"], "primitive type", 0, 255)
        if observed_type != draw_packets[ordinal]["primitive_type"]:
            raise ValueError("raster skip type disagrees with native DrawOTag packet")
        x = number(e["x"], "native VRAM X", 0, 1023)
        y = number(e["y"], "native VRAM Y", 0, 511)
        if sampled_xy is None:
            sampled_xy = (x, y)
        elif sampled_xy != (x, y):
            raise ValueError("raster skip log switches private VRAM coordinate")
        reason = number(e["reason"], "original raster skip reason", 1, 3)
        # Both zero-texel branches are exclusively textured FT4 or SPRT
        # in the fixed PC GPU dispatch; F4/TILE cannot sample a texture.
        if reason in (1, 3) and observed_type not in (2, 3):
            raise ValueError("zero-texture event on a nontextured native primitive")
        counts[reason] += 1
        if ordinal in source_ordinals:
            source_counts[reason] += 1
            source_primitive_ordinals.add(ordinal)

    return {
        "raster_skip_manifest_sha256": sha(manifest_raw),
        "source_overdraw_manifest_sha256": sha(overdraw_raw),
        "native_gpu_capture_log_sha256": sha(native_raw),
        "native_raster_skip_log_sha256": sha(skip_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "observed_skip_events": len(rows),
        "observed_dda_zero_bgr555_texel_events": counts[1],
        "observed_dda_horizontal_span_clip_events": counts[2],
        "observed_legacy_zero_bgr555_texel_events": counts[3],
        "source_keyed_dda_zero_texel_events": source_counts[1],
        "source_keyed_dda_horizontal_clip_events": source_counts[2],
        "source_keyed_legacy_zero_texel_events": source_counts[3],
        "source_keyed_ft4_primitives_with_direct_skip_observation":
            len(source_primitive_ordinals),
        "verified_original_source_to_native_gpu_join": True,
        "native_drawotag_frame_and_ordinal_checked": True,
        "all_executed_raster_skip_branches_captured": False,
        "unlogged_pixel_cause_inferred": False,
        "vertical_clip_per_pixel_confirmed": False,
        "triangle_coverage_and_mask_test_verified": False,
        "ps1_hardware_stp_abr_mask_equivalence": False,
        "original_gameplay_authenticated": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_gpu_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    try:
        report = verify_skips(a.source_bundle, a.native_gpu_capture,
                              compiler=a.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
