#!/usr/bin/env python3
"""Privately promote ONE staged PutPixel log after full original-PC verification.

The two C staging streams are not independently authenticated merely because
they share a frame. This publisher uses an existing source-keyed PutPixel
manifest and the original DrawOTag/VRAM verifier. It never invents events,
source keys, snapshot hashes, or a manifest from the captured pixel stream.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file, MAX_BYTES,
)
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_blendg1_witness import complete_events
from tools.verify_map02_putpixel_scope import (
    SCHEMA, FIELDS, PIXEL_LOG, verify_pixel_ot,
)

PENDING = "putpixel-native-events.pending.jsonl"
MANIFEST = "gpu-putpixel-ot.json"


def promote_staged_putpixel(source_dir, native_dir, *, compiler="gcc"):
    source_dir = _private_directory(source_dir)
    native_dir = _private_directory(native_dir)
    manifest_raw = private_file(source_dir, MANIFEST, max_bytes=64 * 1024)
    meta = parse_json(manifest_raw, MANIFEST)
    fields(meta, ("schema", "source_frame", "gpu_draw_frame",
                  "overdraw_manifest_sha256", "native_events_sha256",
                  "putpixel_events_sha256"), MANIFEST)
    if meta["schema"] != SCHEMA:
        raise ValueError("staged PutPixel manifest schema mismatch")
    raw = private_file(native_dir, PENDING, max_bytes=MAX_BYTES)
    sha_check(raw, meta["putpixel_events_sha256"], "staged native PutPixel")
    rows = complete_events(raw, "staged native PutPixel")
    frame = number(meta["gpu_draw_frame"], "GPU DrawOTag frame", 1, 2**32 - 1)
    for index, row in enumerate(rows):
        fields(row, FIELDS, "staged PutPixel")
        if row["stage"] != "native_putpixel" or number(
                row["step"], "PutPixel step", 0, 63) != index:
            raise ValueError("staged PutPixel stage or step inconsistent")
        if number(row["frame"], "PutPixel frame", 1, 2**32 - 1) != frame:
            raise ValueError("staged PutPixel frame differs from manifest")
        for key, low, high in (
                ("primitive_ordinal", 0, 2**32 - 1),
                ("primitive_type", 0, 255),
                ("x", 0, 1023), ("y", 0, 511),
                ("before", 0, 65535), ("front", 0, 65535),
                ("after", 0, 65535), ("abr", 0, 3),
                ("semi", 0, 1), ("textured", 0, 1),
                ("accurate", 0, 1)):
            number(row[key], key, low, high)

    target = native_dir / PIXEL_LOG
    if target.exists() or target.is_symlink():
        raise ValueError("verified PutPixel destination already exists")
    temp = None
    created = False
    try:
        temp = _prepare_private_file(target, raw)
        os.link(temp, target)  # exclusive: cannot replace existing log
        created = True
        # The verified log must be single-linked during downstream audits.
        temp.unlink()
        report = verify_pixel_ot(source_dir, native_dir, compiler=compiler)
        if report["observed_native_putpixel_calls"] != len(rows):
            raise ValueError("verified original PutPixel event count disagrees")
        if (private_file(native_dir, PIXEL_LOG, max_bytes=MAX_BYTES) != raw or
                private_file(native_dir, PENDING, max_bytes=MAX_BYTES) != raw or
                private_file(source_dir, MANIFEST,
                             max_bytes=64 * 1024) != manifest_raw):
            raise ValueError("private PutPixel evidence changed during verification")
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
    return {
        "verified_native_putpixel_calls": len(rows),
        "putpixel_events_sha256": hashlib.sha256(raw).hexdigest(),
        "source_keyed_drawotag_vram_verified": True,
        "original_gameplay_authenticated": False,
        "ps1_hardware_equivalence_proven": False,
        "raw_game_data_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_capture", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        report = promote_staged_putpixel(args.source_bundle,
                                        args.native_capture,
                                        compiler=args.compiler)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
