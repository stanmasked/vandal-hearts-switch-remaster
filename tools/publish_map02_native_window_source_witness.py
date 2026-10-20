#!/usr/bin/env python3
"""Publish/reverify SHA-bound source-to-window consistency witness privately.

Never manufactures source game identity or silently rewrites another user's
claim. The manifest binds the compiled-GTE-checked source FT4 subset and
the hashes of *every* bounded native window capture file. Publication happens
only after a fresh full verifier and uses exclusive, private file creation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file,
)
from tools.verify_map02_frame_bundle import (
    fields, number, parse_json,
)
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_source_native_windows import verify_window_source_join

MANIFEST = "gpu-native-window-source-witness.json"
SCHEMA = "vh.map02.native-window-source-witness.v1"
DIGEST_FIELDS = (
    "source_claim_sha256", "verified_source_bundle_sha256",
    "verified_source_events_sha256", "native_window_index_sha256",
    "native_window_all_files_sha256",
)


def witness_payload(report):
    return {
        "schema": SCHEMA,
        **{key: report[key] for key in DIGEST_FIELDS},
        "source_frame": report["source_frame"],
        "gpu_draw_frame": report["gpu_draw_frame"],
        "source_ft4_exact_matches": report["source_ft4_exact_matches"],
        "native_draw_pairs": report["native_draw_pairs"],
        "native_gpu_events": report["native_gpu_events"],
        "native_windows": report["native_windows"],
        "source_texture_palette_words_checked":
            report["source_texture_palette_words_checked"],
        "full_original_scene_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }


def _validated_payload(raw):
    fields_raw = (*DIGEST_FIELDS, "schema", "source_frame", "gpu_draw_frame",
                  "source_ft4_exact_matches", "native_draw_pairs",
                  "native_gpu_events", "native_windows",
                  "source_texture_palette_words_checked",
                  "full_original_scene_authenticated",
                  "physical_ps1_equivalence_proven")
    obj = parse_json(raw, MANIFEST)
    fields(obj, fields_raw, MANIFEST)
    if obj["schema"] != SCHEMA or (
            obj["full_original_scene_authenticated"] is not False) or (
            obj["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated window witness manifest")
    for name in DIGEST_FIELDS:
        value = obj[name]
        if (type(value) is not str or len(value) != 64 or
                any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("malformed SHA-256 in window witness")
    for name, lower, upper in (
        ("source_frame", 1, 2**32-1),
        ("gpu_draw_frame", 1, 2**32-1),
        ("source_ft4_exact_matches", 1, 32),
        ("native_draw_pairs", 1, 63),
        ("native_gpu_events", 2, 126),
        ("native_windows", 1, 2),
        ("source_texture_palette_words_checked", 1, 2**32-1),
    ):
        number(obj[name], name, lower, upper)
    return obj


def publish_window_source_witness(source_dir, window_dir, *, compiler="gcc"):
    source = _private_directory(source_dir)
    report = verify_window_source_join(source, window_dir, compiler=compiler)
    manifest = witness_payload(report)
    raw = (json.dumps(manifest, separators=(",", ":"), sort_keys=True)
           + "\n").encode("utf-8")
    final = source / MANIFEST
    if final.exists() or final.is_symlink():
        raise ValueError("source-window witness already exists; refusing overwrite")
    temporary = None
    linked = False
    try:
        temporary = _prepare_private_file(final, raw)
        # Hardlinking is exclusive; cannot replace existing manifest.
        import os
        os.link(temporary, final)
        linked = True
        # End staging hardlink lifetime before strict nlink=1 readback.
        temporary.unlink()
        if private_file(source, MANIFEST, max_bytes=4096) != raw:
            raise ValueError("private source-window witness readback mismatch")
    except BaseException:
        if linked:
            final.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {
        "window_source_witness_manifest_sha256":
            hashlib.sha256(raw).hexdigest(),
        "verified_source_ft4_subsequence": report["source_ft4_exact_matches"],
        "native_window_file_tree_bound": True,
        "full_original_scene_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }


def verify_published_window_source_witness(source_dir, window_dir,
                                           *, compiler="gcc"):
    source = _private_directory(source_dir)
    raw = private_file(source, MANIFEST, max_bytes=4096)
    original = _validated_payload(raw)
    report = verify_window_source_join(source, window_dir, compiler=compiler)
    if original != witness_payload(report):
        raise ValueError("source-window SHA witness disagrees with verified evidence")
    if private_file(source, MANIFEST, max_bytes=4096) != raw:
        raise ValueError("window witness manifest changed during verification")
    return {
        "window_source_witness_manifest_sha256":
            hashlib.sha256(raw).hexdigest(),
        "source_ft4_exact_matches": report["source_ft4_exact_matches"],
        "native_window_file_tree_bound": True,
        "full_original_scene_authenticated": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_windows", type=Path)
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--publish", action="store_true",
                        help="exclusively create source witness after verification")
    args = parser.parse_args()
    try:
        fn = (publish_window_source_witness if args.publish else
              verify_published_window_source_witness)
        result = fn(args.source_bundle, args.native_windows,
                    compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Never echo source/private capture paths or untrusted witness data.
        parser.error("private MAP02 native window witness unavailable")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
