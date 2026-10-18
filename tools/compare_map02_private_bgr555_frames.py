#!/usr/bin/env python3
"""Compare two *private* uncompressed BGR555 MAP02 display frames.

This detects byte/pixel differences only. Both capture labels and hashes can
be fabricated, so even zero mismatches never authenticate retail PS1 pixels.
No original image bytes, colors, coordinates or user paths appear in output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct

SCHEMA = "vh.map02.private-bgr555-frame-comparison.v1"
MAX_PIXELS = 1024 * 512
MAX_JSON = 32768
FILE_NAMES = ("reference.bgr555", "candidate.bgr555")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _object_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("MAP02 frame manifest contains duplicate keys")
        result[k] = v
    return result


def _reject_constant(value):
    raise ValueError("MAP02 frame manifest has nonfinite values")


def _read_regular(directory, name, exact_bytes):
    path = directory / name
    if path.is_symlink():
        raise ValueError("MAP02 private frame cannot be a symlink")
    flags = (os.O_RDONLY | os.O_CLOEXEC |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != exact_bytes:
            raise ValueError("MAP02 private frame size or type invalid")
        chunks = []
        remaining = exact_bytes
        while remaining:
            part = os.read(fd, min(remaining, 1024 * 1024))
            if not part:
                raise ValueError("MAP02 private frame truncated while reading")
            chunks.append(part)
            remaining -= len(part)
        after = os.fstat(fd)
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size,
                    s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after):
            raise ValueError("MAP02 private frame changed while reading")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _manifest(directory):
    raw = _read_regular(directory, "frames.json", MAX_JSON)
    # A fixed 32 KiB manifest file is unnecessary; regular bounded JSON
    # is checked by a separate reader below.
    return raw


def _bounded_manifest(directory):
    path = directory / "frames.json"
    if path.is_symlink():
        raise ValueError("MAP02 private manifest cannot be a symlink")
    flags = (os.O_RDONLY | os.O_CLOEXEC |
             getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(path, flags)
    try:
        start = os.fstat(fd)
        if not stat.S_ISREG(start.st_mode) or not 0 < start.st_size <= MAX_JSON:
            raise ValueError("MAP02 private manifest size/type invalid")
        raw = os.read(fd, MAX_JSON + 1)
        end = os.fstat(fd)
        def identity(s):
            return (s.st_dev, s.st_ino, s.st_size,
                    s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != start.st_size or identity(start) != identity(end):
            raise ValueError("MAP02 private manifest changed while reading")
        try:
            obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs,
                             parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("MAP02 private manifest is not valid JSON") from exc
        return obj, hashlib.sha256(raw).hexdigest()
    finally:
        os.close(fd)


def _validated_metadata(meta):
    if type(meta) is not dict or set(meta) != {
            "schema", "frame", "width", "height", "pixel_format", "images"}:
        raise ValueError("MAP02 frame metadata fields invalid")
    if meta["schema"] != SCHEMA or meta["pixel_format"] != "bgr555_le":
        raise ValueError("MAP02 frame format invalid")
    if type(meta["frame"]) is not int or not 1 <= meta["frame"] <= 2**32 - 1:
        raise ValueError("MAP02 frame identifier invalid")
    w, h = meta["width"], meta["height"]
    if (type(w) is not int or type(h) is not int or
            not 1 <= w <= 1024 or not 1 <= h <= 512 or w * h > MAX_PIXELS):
        raise ValueError("MAP02 frame dimensions invalid")
    images = meta["images"]
    if type(images) is not dict or set(images) != set(FILE_NAMES):
        raise ValueError("MAP02 frame image inventory invalid")
    for name in FILE_NAMES:
        entry = images[name]
        if type(entry) is not dict or set(entry) != {"sha256", "frame", "origin"}:
            raise ValueError("MAP02 frame image metadata invalid")
        expected_origin = ("ps1_reference_claimed" if name == FILE_NAMES[0]
                           else "pc_port_candidate_claimed")
        if (entry["origin"] != expected_origin or
                type(entry["frame"]) is not int or
                entry["frame"] != meta["frame"] or
                type(entry["sha256"]) is not str or
                not SHA.fullmatch(entry["sha256"])):
            raise ValueError("MAP02 frame image identity/hash metadata invalid")
    return w, h


def compare(directory):
    """Report only aggregate differences and private hash identifiers."""
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("MAP02 private comparison directory unavailable or symlinked")
    meta, manifest_sha = _bounded_manifest(directory)
    w, h = _validated_metadata(meta)
    expected_bytes = 2 * w * h
    values = []
    raw_hashes = {}
    for name in FILE_NAMES:
        raw = _read_regular(directory, name, expected_bytes)
        sha = hashlib.sha256(raw).hexdigest()
        if sha != meta["images"][name]["sha256"]:
            raise ValueError("MAP02 private frame SHA-256 mismatch: " + name)
        values.append(raw)
        raw_hashes[name] = sha
    a, b = values
    pixels = w * h
    changed = 0
    color_sum = 0
    max_error = 0
    stp_changed = 0
    occupancy = set()
    mask_digest = hashlib.sha256()
    changed_row_count = 0
    for y in range(h):
        row_mask = bytearray(w)
        row_changed = False
        for x in range(w):
            pos = 2 * (y * w + x)
            left = a[pos] | (a[pos+1] << 8)
            right = b[pos] | (b[pos+1] << 8)
            if left == right:
                continue
            row_changed = True
            changed += 1
            row_mask[x] = 1
            occupancy.add((x // 16, y // 16))
            stp_changed += bool((left ^ right) & 0x8000)
            err = sum(abs(((left >> bit) & 31) - ((right >> bit) & 31))
                      for bit in (0, 5, 10))
            color_sum += err
            max_error = max(max_error, err)
        if row_changed:
            changed_row_count += 1
        mask_digest.update(row_mask)
    # Preserve only counts and hashes; report no screenshot bytes or coordinates.
    return {
        "schema": "vh.map02.private-bgr555-frame-differential.v1",
        "frame": meta["frame"],
        "width": w, "height": h, "pixel_count": pixels,
        "reference_sha256": raw_hashes[FILE_NAMES[0]],
        "candidate_sha256": raw_hashes[FILE_NAMES[1]],
        "manifest_sha256": manifest_sha,
        "difference_mask_sha256": mask_digest.hexdigest(),
        "exact_bgr555_pixel_matches": pixels - changed,
        "different_bgr555_pixels": changed,
        "changed_scanlines": changed_row_count,
        "changed_16x16_blocks": len(occupancy),
        "stp_bit_differences": stp_changed,
        "sum_absolute_bgr5_channel_error": color_sum,
        "maximum_bgr5_pixel_channel_error": max_error,
        "pixel_bytes_emitted": False,
        "capture_source_authenticated": False,
        "ps1_hardware_pixel_equivalence_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_frame_directory", type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.private_frame_directory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
