#!/usr/bin/env python3
"""Owner-local integrity checks for manually marked MAP02 screenshot candidates.

A valid report is NOT an authenticated PS1 frame, a MAP02 discovery, or
an independently verified relationship between movie input and video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import zlib

from tools.validate_map02_private_replay_markers import (
    MARKER, MAX_LOG_BYTES, _read_regular, verify as verify_marker_log,
)

SCHEMA = "vh.map02.private-visual-candidates.v1"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.png$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST = 64 * 1024
MAX_PNG = 16 * 1024 * 1024
MAX_SHOTS = 30


def png_header_and_crc(data: bytes) -> tuple[int, int]:
    """Check PNG structure/chunk CRCs without accepting it as rendered proof."""
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG signature")
    offset = len(PNG_SIG)
    n = 0
    dimensions = None
    has_data = False
    has_end = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk header")
        count = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        offset += 8
        if (count > MAX_PNG or offset + count + 4 > len(data)
                or not re.fullmatch(rb"[A-Za-z]{4}", kind)):
            raise ValueError("invalid PNG chunk")
        payload = data[offset:offset + count]
        expected = struct.unpack_from(">I", data, offset + count)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != expected:
            raise ValueError("PNG chunk checksum differs")
        offset += count + 4
        if n == 0:
            if kind != b"IHDR" or count != 13:
                raise ValueError("missing first PNG IHDR")
            width, height, bit_depth, color, compress, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if (not 1 <= width <= 8192 or not 1 <= height <= 8192
                    or width * height > 40_000_000 or bit_depth not in (1, 2, 4, 8, 16)
                    or color not in (0, 2, 3, 4, 6)
                    or (compress, filt, interlace) not in ((0, 0, 0), (0, 0, 1))):
                raise ValueError("unsupported PNG header")
            dimensions = (width, height)
        elif kind == b"IHDR":
            raise ValueError("duplicate PNG header")
        elif kind == b"IDAT":
            if not has_end:
                has_data = True
        elif kind == b"IEND":
            if count != 0 or has_end or offset != len(data):
                raise ValueError("malformed PNG terminator or trailing bytes")
            has_end = True
        elif kind[0] & 32 == 0 and kind not in (b"PLTE",):
            raise ValueError("unsupported critical PNG chunk")
        if has_end:
            break
        n += 1
        if n > 20000:
            raise ValueError("excessive PNG chunk count")
    if not has_data or not has_end or dimensions is None:
        raise ValueError("PNG image data or end marker missing")
    return dimensions


def read_png_private(root: Path, basename: str) -> bytes:
    if not NAME.fullmatch(basename) or basename in (".", ".."):
        raise ValueError("unsafe private screenshot filename")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("image root is not a real directory")
    target = root / basename
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PNG:
            raise ValueError("screenshot exceeds limit or is not regular")
        with os.fdopen(os.dup(fd), "rb") as source:
            contents = source.read(MAX_PNG + 1)
        if len(contents) > MAX_PNG:
            raise ValueError("PNG too large")
        return contents
    finally:
        os.close(fd)


def verify(inspection_json: Path, marker_log: Path, manifest_json: Path,
           image_root: Path) -> dict:
    # Existing stage verifies known game's BK2 input-frame range, log order,
    # and candidate=(counter-1); this stage never upgrades those claims.
    verify_marker_log(inspection_json, marker_log)
    counters = set()
    for line in _read_regular(marker_log, MAX_LOG_BYTES).splitlines():
        m = MARKER.fullmatch(line)
        if m:
            counters.add(int(m.group(1)))
    manifest = json.loads(_read_regular(manifest_json, MAX_MANIFEST))
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "observations"}:
        raise ValueError("invalid screenshot manifest schema")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unsupported screenshot manifest")
    shots = manifest["observations"]
    if not isinstance(shots, list) or not 2 <= len(shots) <= MAX_SHOTS:
        raise ValueError("need between 2 and 30 screenshot observations")
    seen_files = set()
    previous = 0
    pre = None
    candidate = None
    for shot in shots:
        if not isinstance(shot, dict) or set(shot) != {"emulator_counter", "movie_input_candidate", "label", "png_file", "sha256"}:
            raise ValueError("malformed screenshot observation")
        counter, frame = shot["emulator_counter"], shot["movie_input_candidate"]
        if (type(counter) is not int or type(frame) is not int
                or not previous < counter or counter not in counters
                or frame != counter - 1):
            raise ValueError("screenshot has unmatched or unordered marker")
        label, filename, digest = shot["label"], shot["png_file"], shot["sha256"]
        if label not in ("pre_map02", "map02_candidate", "post_map02"):
            raise ValueError("unrecognized manual scene label")
        if not isinstance(filename, str) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError("invalid private PNG name or hash")
        if filename in seen_files:
            raise ValueError("same screenshot file used twice")
        seen_files.add(filename)
        data = read_png_private(image_root, filename)
        png_header_and_crc(data)
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("private screenshot hash mismatch")
        if label == "pre_map02":
            if candidate is not None:
                raise ValueError("pre-scene marker after candidate")
            pre = counter
        if label == "map02_candidate" and candidate is None:
            if pre is None:
                raise ValueError("MAP02 candidate lacks preceding scene")
            candidate = counter
        if label == "post_map02" and candidate is None:
            raise ValueError("post scene label lacks candidate")
        previous = counter
    if pre is None or candidate is None:
        raise ValueError("no bracketing manual scene labels")
    return {
        "schema": SCHEMA,
        "integrity_checked_png_count": len(shots),
        "markers_matching_screenshot_metadata": True,
        "png_envelopes_crcs_sha256_match": True,
        "pre_candidate_observed_emulator_counter": pre,
        "first_map02_candidate_emulator_counter": candidate,
        "manual_candidate_interval_counter_exclusive_inclusive": [pre, candidate],
        "visual_scene_content_authenticated": False,
        "original_ps1_game_authenticated": False,
        "input_to_emulator_video_alignment_verified": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_vram_captured": False,
        "private_screenshots_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_inspection_json", type=Path)
    parser.add_argument("private_marker_log", type=Path)
    parser.add_argument("private_screenshot_manifest", type=Path)
    parser.add_argument("--image-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = verify(args.private_inspection_json, args.private_marker_log,
                         args.private_screenshot_manifest, args.image_root)
    except (OSError, ValueError, TypeError, UnicodeError, KeyError):
        parser.error("private visual-candidate integrity review unavailable")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
