#!/usr/bin/env python3
"""Privately publish a SHA-bound MAP02 BlendG1 witness after upstream verification.

Input is an opt-in, PRIVATE staged BlendG1 JSONL already written by the local
harness: no event is inferred from PutPixel, and no raw words are printed.
The already existing PutPixel manifest/log and VRAM/DrawOTag evidence must pass
their full verifier first. A final witness manifest is linked into place LAST.
A successful synthetic fixture does not authenticate gameplay or PS1 hardware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from tools.map02_blendg1_witness import compare_blendg1_witnesses
from tools.verify_map02_frame_bundle import fields, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_putpixel_scope import (
    PIXEL_LOG, SCHEMA as PIXEL_SCHEMA, verify_pixel_ot,
)
from tools.verify_map02_blendg1_witness import (
    SCHEMA, MANIFEST, LOG, complete_events,
)

STAGED_LOG = "blendg1-native-events.pending.jsonl"
PIXEL_MANIFEST = "gpu-putpixel-ot.json"
MAX_BYTES = 16 * 1024


def _private_directory(directory):
    path = Path(directory).absolute()
    if (path.is_symlink() or not path.is_dir() or
            stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ValueError("witness directory must exist, be private (0700), and not a symlink")
    return path


def _prepare_private_file(destination, raw):
    if destination.exists() or destination.is_symlink():
        raise ValueError("refuse to overwrite completed BlendG1 evidence")
    fd, name = tempfile.mkstemp(prefix="." + destination.name + ".",
                                suffix=".tmp", dir=destination.parent)
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != raw:
            raise ValueError("private witness file failed readback")
        return path
    except BaseException:
        if fd >= 0:
            os.close(fd)
        path.unlink(missing_ok=True)
        raise


def publish_blendg1_witness(source_dir, native_dir, *, compiler="gcc"):
    source_dir = _private_directory(source_dir)
    native_dir = _private_directory(native_dir)
    pixel_meta = private_file(source_dir, PIXEL_MANIFEST, max_bytes=64 * 1024)
    meta = parse_json(pixel_meta, PIXEL_MANIFEST)
    fields(meta, ("schema", "source_frame", "gpu_draw_frame",
                  "overdraw_manifest_sha256", "native_events_sha256",
                  "putpixel_events_sha256"), PIXEL_MANIFEST)
    if meta["schema"] != PIXEL_SCHEMA:
        raise ValueError("wrong upstream PutPixel manifest schema")

    pixel_raw = private_file(native_dir, PIXEL_LOG, max_bytes=MAX_BYTES)
    staged_raw = private_file(native_dir, STAGED_LOG, max_bytes=MAX_BYTES)
    sha_check(pixel_raw, meta["putpixel_events_sha256"], "upstream PutPixel")
    pixels = complete_events(pixel_raw, "upstream PutPixel")
    witnesses = complete_events(staged_raw, "private BlendG1")
    compare_blendg1_witnesses(pixels, witnesses)

    # Source/GTE/DrawOTag/VRAM verification is NOT optional for real publish.
    verified = verify_pixel_ot(source_dir, native_dir, compiler=compiler)
    if verified["observed_native_putpixel_calls"] != len(pixels):
        raise ValueError("upstream PutPixel verification disagrees with staged count")

    # Reject changes while the expensive DrawOTag/VRAM verifier was running.
    for root, name, original, bound in (
        (source_dir, PIXEL_MANIFEST, pixel_meta, 64 * 1024),
        (native_dir, PIXEL_LOG, pixel_raw, MAX_BYTES),
        (native_dir, STAGED_LOG, staged_raw, MAX_BYTES),
    ):
        if private_file(root, name, max_bytes=bound) != original:
            raise ValueError("private witness input changed during verification")

    manifest = {
        "schema": SCHEMA,
        "pixel_ot_manifest_sha256": hashlib.sha256(pixel_meta).hexdigest(),
        "putpixel_events_sha256": hashlib.sha256(pixel_raw).hexdigest(),
        "blendg1_events_sha256": hashlib.sha256(staged_raw).hexdigest(),
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True,
                               separators=(",", ":")) + "\n").encode("utf-8")
    log_final = native_dir / LOG
    manifest_final = source_dir / MANIFEST

    if any(p.exists() or p.is_symlink() for p in (log_final, manifest_final)):
        raise ValueError("completed BlendG1 witness already exists")
    log_temp = manifest_temp = None
    published_log = False
    published_manifest = False
    try:
        log_temp = _prepare_private_file(log_final, staged_raw)
        manifest_temp = _prepare_private_file(manifest_final, manifest_raw)
        os.link(log_temp, log_final)  # atomic, exclusive: no clobber
        published_log = True
        log_temp.unlink()  # downstream witnesses require nlink=1
        if log_final.read_bytes() != staged_raw:
            raise ValueError("published BlendG1 log failed readback")
        os.link(manifest_temp, manifest_final)  # publish completion marker LAST
        published_manifest = True
        manifest_temp.unlink()  # retain single-linked completion marker
        if manifest_final.read_bytes() != manifest_raw:
            raise ValueError("published BlendG1 manifest failed readback")
    except BaseException:
        if published_manifest:
            manifest_final.unlink(missing_ok=True)
        if published_log:
            log_final.unlink(missing_ok=True)
        raise
    finally:
        if log_temp is not None:
            log_temp.unlink(missing_ok=True)
        if manifest_temp is not None:
            manifest_temp.unlink(missing_ok=True)

    return {
        "pixel_events": len(pixels),
        "blendg1_events": len(witnesses),
        "witness_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
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
        result = publish_blendg1_witness(
            args.source_bundle, args.native_capture, compiler=args.compiler)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
