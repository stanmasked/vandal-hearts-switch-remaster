#!/usr/bin/env python3
"""Owner-private MAP02 PC texture math + source/native FT4 GPU join.

Both constituent validators already exist. This wrapper ensures they consumed
the SAME privately pinned input bytes despite different source/GPU clocks.
It is a consistency witness, not original disc authentication or PS1 parity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_private_timeline_pc_vram4 import (
    verify_private_timeline, snapshot_inputs,
)
from tools.verify_map02_source_native_ft4_join import verify_timeline_join

SCHEMA = "vh.map02.private-pc-vram4-native-ft4-join.v1"
SOURCE_JOIN = "gpu-face-timeline-join.json"
NATIVE_LOG = "gpu-native-events.jsonl"
MAX_RECORDS = 64
MAX_SNAPSHOTS = 32
VRAM_BYTES = 1024 * 512 * 2


def freeze_inputs(source: Path, native: Path):
    """Keep data plus fstat/inode stamps; never take paths from manifests."""
    source = _private_directory(source)
    native = _private_directory(native)
    if source == native:
        raise ValueError("private source and native directories must be distinct")
    timeline_raw = private_file(source, "timeline.json", max_bytes=65536)
    timeline = parse_json(timeline_raw, "timeline")
    descriptions = timeline.get("snapshots")
    if type(descriptions) is not list or not 1 <= len(descriptions) <= MAX_SNAPSHOTS:
        raise ValueError("private timeline must describe 1–32 snapshots")
    source_pinned = snapshot_inputs(source, len(descriptions))
    claim = private_file(
        source, SOURCE_JOIN, max_bytes=65536, _with_identity=True,
    )
    native_log = private_file(
        native, NATIVE_LOG, max_bytes=128 * 1024, _with_identity=True,
    )
    native_lines = native_log[0].splitlines()
    if not 1 <= len(native_lines) <= MAX_RECORDS:
        raise ValueError("native GPU log has invalid record count")
    paths = []
    for i, raw in enumerate(native_lines):
        event = parse_json(raw, f"native GPU log record {i}")
        if type(event) is not dict:
            raise ValueError("native GPU event is not a JSON object")
        name = event.get("snapshot")
        if type(name) is not str:
            raise ValueError("native GPU event snapshot name missing")
        if name not in paths:
            paths.append(name)
    native_pinned = tuple(
        (name, private_file(
            native, name, expected=VRAM_BYTES, _with_identity=True,
        ))
        for name in paths
    )
    return source_pinned, claim, native_log, native_pinned


def verify_unified(source_dir: Path, native_dir: Path, raster: Path,
                   *, compiler: str = "gcc") -> dict:
    source = _private_directory(source_dir)
    native = _private_directory(native_dir)
    if source == native:
        raise ValueError("source and native evidence directories must differ")
    first = freeze_inputs(source, native)
    public_raster = Path(raster).absolute()
    if public_raster.is_symlink() or not public_raster.is_file():
        raise ValueError("pinned public PC source unavailable")
    source_bytes = public_raster.read_bytes()

    pc = verify_private_timeline(source, public_raster, compiler=compiler)
    if (pc.get("source_gte_and_snapshot_timeline_verified") is not True or
            pc.get("post_verification_input_stability_checked") is not True or
            type(pc.get("submitted_faces")) is not int or
            pc["submitted_faces"] < 1 or
            pc.get("compiled_pc_source_4bpp_texels_compared") !=
                pc["submitted_faces"] * 65536):
        raise ValueError("private PC texture-source witness incomplete")

    joined = verify_timeline_join(source, native, compiler=compiler)
    count = pc["submitted_faces"]
    if (joined.get("source_submissions_verified") != count or
            joined.get("uniquely_matched_source_faces") != count or
            joined.get("per_submission_vram_snapshots_compared") != count or
            joined.get("screen_corners_uv_page_clut_window_exact") is not True or
            joined.get("pc_gte_source_timeline_verified") is not True or
            joined.get("native_gpu_capture_verified") is not True or
            joined.get("source_to_gpu_frame_binding_authenticated") is not False):
        raise ValueError("private PC sampling and native FT4 join disagree")

    # Fail closed if any owned source or native file was swapped after either
    # validator ran; this is not a kernel-level atomic snapshot guarantee.
    if first != freeze_inputs(source, native):
        raise ValueError("private source/native input changed during combined checks")
    if (public_raster.is_symlink() or
            public_raster.read_bytes() != source_bytes):
        raise ValueError("pinned public PC source changed during combined checks")

    return {
        "schema": SCHEMA,
        "source_submissions_checked": count,
        "source_native_ft4_unique_matches": count,
        "per_ft4_vram_snapshots_compared": count,
        "compiled_pc_sampletexture_texels_checked": count * 65536,
        "source_gpu_frame_mapping_explicit_and_hash_bound": True,
        "full_source_native_inputs_rechecked_after_both_validators": True,
        "native_draw_order_assumed_same_as_source": False,
        "continuous_gpu_vram_monitoring_proven": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_raster_parity_proven": False,
        "private_game_bytes_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_source_timeline", type=Path)
    parser.add_argument("private_native_gpu_capture", type=Path)
    parser.add_argument("pinned_public_pc_raster", type=Path)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = parser.parse_args()
    try:
        result = verify_unified(
            args.private_source_timeline, args.private_native_gpu_capture,
            args.pinned_public_pc_raster, compiler=args.compiler,
        )
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        parser.error("local MAP02 source/native FT4 verification unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
