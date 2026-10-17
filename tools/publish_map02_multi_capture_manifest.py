#!/usr/bin/env python3
"""Publish a private two-word MAP02 capture receipt only after full replay.

Original game data, VRAM snapshots, geometry and pixel coordinates never
leave their private directories. A successful software replay checks a
*claimed* capture; it does not authenticate retail game execution.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import LOG, private_file
from tools.verify_map02_putpixel_scope import PIXEL_LOG
from tools.verify_map02_putpixel_multi_scope import (
    MANIFEST, SCHEMA, verify_multi_pixel_ot,
)

OVERDRAW_MANIFEST = "gpu-native-overdraw.json"


def _capture_dependency_inventory(source_dir, native_dir):
    """Fingerprint every flat private source/native file, not only 3 logs.

    The full replay depends on original source/OT/GTE files, upload payloads
    and 1 MiB VRAM snapshots as well as the JSONL files. A rehashed GPU log
    alone cannot detect their replacement during replay. This is an in-memory
    equality guard, not an identity proof or a public list of private files.
    """
    inventory = []
    for role, directory in (("source", source_dir), ("native", native_dir)):
        children = sorted(directory.iterdir(), key=lambda item: item.name)
        if len(children) > 256:
            raise ValueError("too many private capture dependency files")
        for path in children:
            if path.is_symlink() or not path.is_file():
                raise ValueError("private capture dependencies must be regular, nonlinked files")
            # After exclusive creation the exact new receipt is excluded
            # from the input set, but it is checked bytewise below.
            if role == "source" and path.name == MANIFEST:
                continue
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                before = os.fstat(handle.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_size > 16 * 1024 * 1024:
                    raise ValueError("private capture dependency is not a bounded regular file")
                digest = hashlib.sha256()
                size = 0
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                after = os.fstat(handle.fileno())
            current = os.stat(path, follow_symlinks=False)
            keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if size != before.st_size or any(
                    getattr(before, key) != getattr(after, key)
                    or getattr(before, key) != getattr(current, key)
                    for key in keys):
                raise ValueError("private capture dependency changed while hashing")
            inventory.append((role, path.name, digest.hexdigest(),
                              before.st_dev, before.st_ino, before.st_size,
                              before.st_mtime_ns, before.st_ctime_ns))
    if not inventory:
        raise ValueError("private capture dependency files are missing")
    return tuple(inventory)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _input_bytes(source_dir, native_dir):
    return {
        "overdraw_manifest_sha256": _sha(
            private_file(source_dir, OVERDRAW_MANIFEST, max_bytes=64*1024)),
        "native_events_sha256": _sha(
            private_file(native_dir, LOG, max_bytes=128*1024)),
        "putpixel_events_sha256": _sha(
            private_file(native_dir, PIXEL_LOG, max_bytes=16*1024)),
    }


def publish_multi_manifest(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    for root in (source_dir, native_dir):
        if root.is_symlink() or not root.is_dir():
            raise ValueError("private capture directory missing or symlinked")
    target = source_dir / MANIFEST
    if target.exists() or target.is_symlink():
        raise ValueError("two-word receipt already exists; refusing overwrite")
    dependencies_before = _capture_dependency_inventory(source_dir, native_dir)

    overdraw_raw = private_file(
        source_dir, OVERDRAW_MANIFEST, max_bytes=64*1024)
    metadata = parse_json(overdraw_raw, OVERDRAW_MANIFEST)
    fields(metadata, ("schema", "source_frame", "gpu_draw_frame",
                      "ot_order_manifest_sha256", "native_events_sha256"),
           OVERDRAW_MANIFEST)
    if metadata["schema"] != "vh.map02.native-overdraw.v1":
        raise ValueError("unexpected native overdraw manifest schema")
    frame = number(metadata["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(metadata["gpu_draw_frame"], "GPU frame", 1, 2**32-1)
    input_hashes = _input_bytes(source_dir, native_dir)
    candidate = {
        "schema": SCHEMA,
        "source_frame": frame,
        "gpu_draw_frame": gpu_frame,
        **input_hashes,
    }
    raw = (json.dumps(candidate, sort_keys=True, indent=2) + "\n").encode("utf-8")

    # Re-run GTE/FT4/OT, full GPU VRAM and each of the two selected
    # native WritePixel histories before creating ANY receipt on disk.
    verified = verify_multi_pixel_ot(
        source_dir, native_dir, compiler=compiler, manifest_bytes=raw)
    if verified["two_word_manifest_sha256"] != _sha(raw):
        raise ValueError("in-memory receipt digest differs after replay")
    current = _input_bytes(source_dir, native_dir)
    if _capture_dependency_inventory(source_dir, native_dir) != dependencies_before:
        raise ValueError("private capture dependencies mutated during verification")
    for label, expected in input_hashes.items():
        if not hmac.compare_digest(current[label], expected):
            raise ValueError(label + ": input mutated during verification")

    # Exclusive creation: fail closed on existing file/symlink, never
    # overwrite prior audit evidence. Owner-readable private file.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if stat.S_IMODE(target.stat().st_mode) != 0o600:
            raise ValueError("receipt has unexpected file permissions")
        directory_fd = os.open(source_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        # After fsync confirm neither the source/OT/GTE nor native VRAM
        # dependencies changed before the receipt became durable.
        if _capture_dependency_inventory(source_dir, native_dir) != dependencies_before:
            raise ValueError("private capture dependencies mutated after receipt fsync")
        if private_file(source_dir, MANIFEST, max_bytes=64*1024) != raw:
            raise ValueError("private two-word receipt changed after fsync")
    except BaseException:
        target.unlink(missing_ok=True)
        raise

    # Neither private absolute paths nor selected XY/BGR555 are returned.
    return {
        "schema": SCHEMA,
        "source_frame": frame,
        "native_gpu_frame": gpu_frame,
        "two_word_manifest_sha256": _sha(raw),
        "distinct_private_vram_words_verified":
            verified["distinct_private_vram_words_verified"],
        "source_keyed_ft4_draws_checked":
            verified["source_keyed_ft4_draws_checked"],
        "private_receipt_published": True,
        "private_capture_dependencies_rechecked": True,
        "private_capture_dependency_file_count": len(dependencies_before),
        "full_original_pc_replay_verified": True,
        "real_map02_gameplay_authenticated": False,
        "native_capture_process_identity_authenticated": False,
        "physical_ps1_pixel_equivalence_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_gpu_capture", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = publish_multi_manifest(
            args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
