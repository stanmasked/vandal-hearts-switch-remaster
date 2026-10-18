#!/usr/bin/env python3
"""Privately seal four MAP02 GPU diagnostic streams to verified source GTE.

A completed source/GTE-to-windows witness is MANDATORY, never optional.
Actual original-PC DrawOTag GPU windows, scoped PutPixel, BlendG1 and
independently read per-primitive VRAM edges are reverified before
publishing and whenever reopening this final SHA-256 manifest.

The artifact is a structural integrity witness only: it cannot establish
retail game provenance, complete frame coverage or physical PS1 parity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file,
)
from tools.publish_map02_native_window_source_witness import (
    MANIFEST as SOURCE_WITNESS,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_window_scoped_join import verify_window_scoped_join

SCHEMA = "vh.map02.native-window-scoped-source-witness.v1"
MANIFEST = "gpu-native-window-scoped-source-witness.json"
DIGEST_FIELDS = (
    "source_window_witness_manifest_sha256",
    "all_native_window_file_bytes_sha256",
    "capture_session_sha256",
    "putpixel_staged_sha256",
    "blendg1_staged_sha256",
    "direct_vram_edges_staged_sha256",
)
REQUIRED = (
    "schema", "gpu_frame", "global_draw_ordinals_checked",
    "global_event_indices_of_first_and_last_draw",
    "draws_at_start_of_following_windows",
    "independently_sampled_draw_edges",
    "unchanged_draws_at_selected_pixel",
    "selected_pixel_putpixel_events",
    "selected_pixel_blendg1_events", "source_gte_subsequence_verified",
    "capture_session_linked",
    "whole_original_gameplay_frame_proven",
    "physical_ps1_equivalence_proven", *DIGEST_FIELDS,
)


def _digest(blob):
    return hashlib.sha256(blob).hexdigest()


def _payload(report):
    if report.get("source_gte_subsequence_verified") is not True:
        raise ValueError("a fully verified original GTE source witness is mandatory")
    if report.get("capture_session_linked") is not True:
        raise ValueError("same-process GPU/scoped capture session receipt is mandatory")
    result = {key: report[key] for key in REQUIRED if key != "schema"}
    result["schema"] = SCHEMA
    return _validate(result)


def _validate(record):
    if type(record) is not dict:
        raise ValueError("window-scoped witness is not a JSON object")
    fields(record, REQUIRED, MANIFEST)
    if (record["schema"] != SCHEMA or
            record["source_gte_subsequence_verified"] is not True or
            record["capture_session_linked"] is not True or
            record["whole_original_gameplay_frame_proven"] is not False or
            record["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated MAP02 scoped witness")
    for name in DIGEST_FIELDS:
        value = record[name]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("malformed SHA-256: " + name)
    for name, low, high in (
        ("gpu_frame", 1, 2**32 - 1),
        ("global_draw_ordinals_checked", 1, 63),
        ("draws_at_start_of_following_windows", 0, 1),
        ("independently_sampled_draw_edges", 1, 63),
        ("unchanged_draws_at_selected_pixel", 0, 63),
        ("selected_pixel_putpixel_events", 1, 63),
        ("selected_pixel_blendg1_events", 1, 63),
    ):
        number(record[name], name, low, high)
    indices = record["global_event_indices_of_first_and_last_draw"]
    if (type(indices) is not list or len(indices) != 2):
        raise ValueError("invalid global DrawOTag event-index endpoints")
    first = number(indices[0], "first global event", 0, 125)
    last = number(indices[1], "last global event", 0, 125)
    if first > last or (record["global_draw_ordinals_checked"] > 1 and
                        first >= last):
        raise ValueError("inconsistent DrawOTag event-index endpoints")
    if (record["independently_sampled_draw_edges"] !=
            record["global_draw_ordinals_checked"] or
            record["selected_pixel_blendg1_events"] >
            record["selected_pixel_putpixel_events"] or
            record["unchanged_draws_at_selected_pixel"] >=
            record["global_draw_ordinals_checked"]):
        raise ValueError("inconsistent four-stream MAP02 event counts")
    return record


def _verified_payload(source_dir, native_dir, scoped_dir, *, frame, compiler):
    verified = verify_window_scoped_join(
        native_dir, scoped_dir, target_frame=frame,
        source_dir=source_dir, compiler=compiler)
    result = _payload(verified)
    # Confirm the source witness file we hash is the one that passed
    # expensive compiled-GTE/FT4 verification in the preceding join.
    raw_source = private_file(source_dir, SOURCE_WITNESS, max_bytes=4096)
    if _digest(raw_source) != result["source_window_witness_manifest_sha256"]:
        raise ValueError("GTE window witness changed during four-stream join")
    return result


def publish_window_scoped_witness(source_dir, native_dir, scoped_dir, *,
                                  frame, compiler="gcc"):
    source = _private_directory(source_dir)
    native = _private_directory(native_dir)
    scoped = _private_directory(scoped_dir)
    if len({source.resolve(), native.resolve(), scoped.resolve()}) != 3:
        raise ValueError("source, GPU windows and scoped captures must be separate")
    target = source / MANIFEST
    if target.exists() or target.is_symlink():
        raise ValueError("final four-stream MAP02 witness already exists")
    payload = _verified_payload(source, native, scoped,
                                frame=frame, compiler=compiler)
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"))
           + "\n").encode("utf-8")
    temp = None
    installed = False
    try:
        temp = _prepare_private_file(target, raw)
        # Recheck ALL source, scoped and window files before the final marker.
        if _verified_payload(source, native, scoped, frame=frame,
                             compiler=compiler) != payload:
            raise ValueError("MAP02 witness inputs changed before publication")
        os.link(temp, target)  # exclusive, no overwrite
        installed = True
        # Remove staging alias before the nlink=1 evidence readback.
        temp.unlink()
        if private_file(source, MANIFEST, max_bytes=4096) != raw:
            raise ValueError("final MAP02 witness write/readback mismatch")
    except BaseException:
        if installed:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return {
        "private_witness_sha256": _digest(raw),
        "global_draw_ordinals_checked": payload["global_draw_ordinals_checked"],
        "four_scoped_gpu_streams_source_bound": True,
        "full_original_gameplay_frame_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def verify_published_window_scoped_witness(source_dir, native_dir, scoped_dir,
                                           *, frame, compiler="gcc"):
    source = _private_directory(source_dir)
    native = _private_directory(native_dir)
    scoped = _private_directory(scoped_dir)
    raw = private_file(source, MANIFEST, max_bytes=4096)
    original = _validate(parse_json(raw, MANIFEST))
    if original["gpu_frame"] != number(frame, "selected GPU frame",
                                       1, 2**32 - 1):
        raise ValueError("selected GPU frame differs from final witness")
    fresh = _verified_payload(source, native, scoped,
                              frame=frame, compiler=compiler)
    if original != fresh:
        raise ValueError("four-stream MAP02 witness does not match verified inputs")
    if private_file(source, MANIFEST, max_bytes=4096) != raw:
        raise ValueError("final MAP02 manifest changed during re-verification")
    return {
        "private_witness_sha256": _digest(raw),
        "global_draw_ordinals_checked": fresh["global_draw_ordinals_checked"],
        "four_scoped_gpu_streams_source_bound": True,
        "full_original_gameplay_frame_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_source", type=Path)
    p.add_argument("private_gpu_windows", type=Path)
    p.add_argument("private_scoped_capture", type=Path)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--compiler", default="gcc")
    p.add_argument("--publish", action="store_true",
                   help="exclusive publication; otherwise reverify existing witness")
    args = p.parse_args()
    function = (publish_window_scoped_witness if args.publish else
                verify_published_window_scoped_witness)
    try:
        report = function(
            args.private_source, args.private_gpu_windows,
            args.private_scoped_capture, frame=args.frame,
            compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
