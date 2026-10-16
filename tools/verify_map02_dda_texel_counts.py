#!/usr/bin/env python3
"""Validate source-pinned PC native FT4 executed DDA texel aggregate captures.

Require independently audited native before/after GPU trace and a private
SHA-bound mapping to one counter file. Counters represent sampling decisions
inside native DDA, NOT exact VRAM writes, physical PS1 pixels or provenance.
Only counts and hashes are exposed; no per-texel/XY/game bytes leave this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import LOG, private_file, verify_capture

SCHEMA = "vh.map02.native-dda-ft4-texel-counts.v1"
ROWS = "native-dda-ft4-texel-counts.jsonl"
MANIFEST = "native-dda-ft4-counts.json"
MAX_ROWS = 64


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_dda_counts(directory, *, target_frame):
    directory = Path(directory).absolute()
    raw = private_file(directory, MANIFEST, max_bytes=16 * 1024)
    manifest = parse_json(raw, MANIFEST)
    fields(manifest, ("schema", "gpu_draw_frame",
                      "native_events_sha256", "texel_counts_sha256"),
           "DDA counts manifest")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unexpected native DDA counts manifest schema")
    if number(manifest["gpu_draw_frame"], "GPU frame", 1, 2**32-1) != target_frame:
        raise ValueError("DDA counts target frame differs from manifest")
    native_raw = private_file(directory, LOG, max_bytes=128 * 1024)
    counts_raw = private_file(directory, ROWS, max_bytes=16 * 1024)
    sha_check(native_raw, manifest["native_events_sha256"], "native GPU events")
    sha_check(counts_raw, manifest["texel_counts_sha256"], "native DDA texel counts")
    checked = verify_capture(directory, target_frame=target_frame)
    if checked["record_cap_reached"]:
        raise ValueError("native GPU snapshots reached cap; completeness unknown")
    events = [parse_json(line, f"native GPU event {i}")
              for i, line in enumerate(native_raw.splitlines())]
    ft4_ordinals = [
        i for i, event in enumerate(events[::2])
        if event["operation"] == "draw" and event["primitive_type"] == 2
        and event["ft4"] is not None
    ]
    lines = counts_raw.splitlines()
    if not 1 <= len(lines) < MAX_ROWS or any(not row.strip() for row in lines):
        raise ValueError("DDA count records missing, blank or at cap")
    if len(ft4_ordinals) != len(lines):
        raise ValueError("DDA FT4 counts incomplete or native GPU capture incomplete")
    totals = [0, 0, 0]
    zero_sample_primitives = 0
    for i, (line, expected_ordinal) in enumerate(zip(lines, ft4_ordinals)):
        event = parse_json(line, f"DDA primitive count {i}")
        fields(event, ("stage", "step", "frame", "primitive_ordinal",
                       "primitive_type", "zero", "stp", "opaque"),
               f"DDA primitive count {i}")
        if event["stage"] != "native_dda_ft4_texel_counts":
            raise ValueError("not a native DDA sampling counter event")
        if number(event["step"], "DDA count step", 0, MAX_ROWS-1) != i:
            raise ValueError("DDA record steps are not contiguous")
        if number(event["frame"], "DDA GPU frame", 1, 2**32-1) != target_frame:
            raise ValueError("DDA count record belongs to wrong GPU frame")
        if number(event["primitive_ordinal"], "FT4 ordinal", 0, MAX_ROWS-1) != expected_ordinal:
            raise ValueError("DDA primitive ordinal not linked to native FT4")
        if number(event["primitive_type"], "FT4 type", 0, 255) != 2:
            raise ValueError("DDA count record not an FT4")
        vals = [number(event[k], f"DDA {k} counter", 0, 2**64-1)
                for k in ("zero", "stp", "opaque")]
        if any(x + y > 2**64-1 for x, y in zip(totals, vals)):
            raise ValueError("DDA counters overflow aggregate")
        totals = [x + y for x, y in zip(totals, vals)]
        zero_sample_primitives += sum(vals) == 0
    return {
        "native_dda_counts_manifest_sha256": digest(raw),
        "native_gpu_event_log_sha256": digest(native_raw),
        "native_dda_texel_counts_sha256": digest(counts_raw),
        "native_gpu_frame": target_frame,
        "native_ft4_primitives_correlated": len(lines),
        "native_dda_bgr555_zero_samples": totals[0],
        "native_dda_nonzero_stp_samples": totals[1],
        "native_dda_nonzero_opaque_samples": totals[2],
        "native_ft4_primitives_without_dda_samples": zero_sample_primitives,
        "complete_native_ft4_set_in_bounded_capture": True,
        "all_sampling_decisions_in_original_dda": True,
        "legacy_barycentric_sampling_included": False,
        "primitive_pixel_write_count_inferred": False,
        "source_keyed_map02_attribution_proven": False,
        "hardware_ps1_pixel_equivalence_proven": False,
        "original_gameplay_authenticated": False,
        "raw_game_data_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_gpu_capture", type=Path)
    parser.add_argument("--frame", required=True, type=int)
    args = parser.parse_args()
    try:
        report = verify_dda_counts(args.private_gpu_capture,
                                   target_frame=args.frame)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
