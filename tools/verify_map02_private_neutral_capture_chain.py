#!/usr/bin/env python3
"""Private-only audit of the complete BK2->capture-plan->Lua-log->PNG chain.

This verifies supplied metadata and PNG integrity, NOT actual PS1 execution,
input-to-display synchrony, scene identity, or MAP02. Never upload inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from tools.map02_private_bk2_capture_plan import plan_lines
from tools.verify_map02_private_bk2_input_handshake import read_private
from tools.verify_map02_private_visual_candidates import (
    png_header_and_crc, read_png_private,
)
from tools.map02_private_png_idat import verify_idat_scanlines

SCHEMA = "vh.map02.private-neutral-capture-chain-audit.v1"
PLAN_HEADER = "VH_MAP02_CAPTURE_PLAN_V1"
FRAME_COUNT = 933949
PLAN_LIMIT = 8192
LOG_LIMIT = 1024 * 1024
MAX_SHOTS = 30
PLAN_ROW = re.compile(r"([1-9][0-9]*),(before|middle|after),([0-9]+),(held|neutral)")
LOG_ROW = re.compile(
    r"VH_PRIVATE_NEUTRAL_CAPTURE window=([0-9]+) "
    r"role=(before|middle|after) counter=([0-9]+) "
    r"candidate_input=([0-9]+) expected_buttons=(held|neutral) "
    r"png=written display_offset=unverified"
)
START_PREFLIGHT = ("VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 "
                   "candidate_input=1661 first_start_pressed=yes "
                   "ps1_input_delivery=unverified")
COMPLETE = re.compile(
    r"VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=([0-9]+) "
    r"movie_input_only=yes actual_map02=unverified"
)


def parse_plan(private_plan: Path) -> tuple[str, list[tuple[int, str, int, str]]]:
    source = read_private(private_plan, PLAN_LIMIT)
    if not source.endswith("\n") or "\r" in source or not source.isascii():
        raise ValueError("non-canonical private capture plan")
    lines = source.splitlines()
    if len(lines) < 6 or lines[0] != PLAN_HEADER or lines[1] != ("movie_frames=%d" % FRAME_COUNT):
        raise ValueError("wrong private capture plan header")
    expected_count = lines[2]
    if not re.fullmatch(r"capture_count=(?:[1-9][0-9]*)", expected_count):
        raise ValueError("invalid private capture plan count")
    count = int(expected_count.split("=", 1)[1])
    if not 3 <= count <= MAX_SHOTS or count % 3 or len(lines) != count + 3:
        raise ValueError("incomplete private capture plan")
    parsed = []
    roles = {}
    last = 1662
    for row in lines[3:]:
        match = PLAN_ROW.fullmatch(row)
        if match is None:
            raise ValueError("invalid private capture plan record")
        g, role, raw_frame, held = match.groups()
        group, frame = int(g), int(raw_frame)
        if (group > count // 3 or frame <= last or frame >= FRAME_COUNT
                or held != ("neutral" if role == "middle" else "held")):
            raise ValueError("private capture plan has invalid frame or state")
        last = frame
        roles.setdefault(group, {})
        if role in roles[group]:
            raise ValueError("duplicate review group role")
        roles[group][role] = frame
        parsed.append((group, role, frame, held))
    for group in range(1, count // 3 + 1):
        g = roles.get(group)
        if (g is None or set(g) != {"before", "middle", "after"}
                or not (g["before"] < g["middle"] < g["after"])):
            raise ValueError("missing or misordered group in private plan")
    return source, parsed


def verify(private_bk2: Path, private_plan: Path, private_log: Path,
           image_root: Path, *, minimum: int = 180, maximum: int = 1800,
           after: int = 1663, before: int = FRAME_COUNT) -> dict:
    source_text, planned = parse_plan(private_plan)
    windows = len(planned) // 3
    # Re-parse the complete original private BK2 instead of treating an
    # externally supplied plan as authoritative evidence of its button input.
    reconstructed = plan_lines(
        private_bk2, limit=windows,
        minimum=minimum, maximum=maximum, after=after, before=before,
    )
    if source_text != "\n".join(reconstructed) + "\n":
        raise ValueError("private plan was not reconstructed from source BK2")
    lines = read_private(private_log, LOG_LIMIT).splitlines()
    observed = []
    completed = 0
    preflight = False
    for line in lines:
        if line.startswith("VH_PRIVATE_NEUTRAL_START_PREFLIGHT"):
            if line != START_PREFLIGHT or preflight or completed or observed:
                raise ValueError("missing, duplicate or misplaced live Start anchor")
            preflight = True
        elif line.startswith("VH_PRIVATE_NEUTRAL_CAPTURE_ERROR"):
            raise ValueError("private emulator probe reported incomplete capture")
        if line.startswith("VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE"):
            match = COMPLETE.fullmatch(line)
            if match is None or not preflight or completed or len(observed) != len(planned):
                raise ValueError("capture completion is invalid or premature")
            if int(match.group(1)) != len(planned):
                raise ValueError("capture summary count differs")
            completed += 1
        elif line.startswith("VH_PRIVATE_NEUTRAL_CAPTURE"):
            match = LOG_ROW.fullmatch(line)
            if match is None or not preflight or completed or len(observed) >= len(planned):
                raise ValueError("malformed or late private capture record")
            g, role, counter, candidate, held = match.groups()
            item = (int(g), role, int(candidate), held)
            if (item != planned[len(observed)]
                    or int(counter) != int(candidate) + 1):
                raise ValueError("log counter, role or source frame differs")
            observed.append(item)
    if not preflight or completed != 1 or len(observed) != len(planned):
        raise ValueError("capture log missing Start anchor or incomplete")

    root = Path(image_root)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("capture images must be in one real absolute directory")
    # Resolve parent symlinks as well: a private-looking path could otherwise
    # point to a public Git checkout and be committed accidentally.
    resolved = root.resolve(strict=True)
    if any((parent / ".git").exists() or (parent / ".git").is_symlink()
           for parent in (resolved, *resolved.parents)):
        raise ValueError("private screenshots must stay outside Git checkouts")
    inodes = set()
    hash_count = 0
    for group, role, index, _ in planned:
        filename = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, index + 1,
        )
        path = root / filename
        file_stat = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("private capture is not regular")
        inode = (file_stat.st_dev, file_stat.st_ino)
        if inode in inodes:
            raise ValueError("private screenshot inode reused at two frames")
        inodes.add(inode)
        picture = read_png_private(root, filename)
        png_header_and_crc(picture)
        verify_idat_scanlines(picture)
        hashlib.sha256(picture).digest()  # inspect bytes without printing hashes
        hash_count += 1
    return {
        "schema": SCHEMA,
        "review_group_count": windows,
        "screenshot_count": hash_count,
        "private_plan_rebuilt_from_direct_bk2": True,
        "capture_logs_match_each_planned_input_and_counter": True,
        "owner_log_reports_live_first_start_anchor_before_screenshots": True,
        "all_png_crc_zlib_scanlines_pass": True,
        "distinct_screenshot_file_inodes": True,
        "movie_input_to_actual_ps1_delivery_verified": False,
        "real_bizhawk_execution_authenticated": False,
        "actual_displayed_frame_offset_verified": False,
        "image_scene_identity_verified": False,
        "map02_frame_identified": False,
        "source_native_gpu_vram_verified": False,
        "private_input_or_png_published": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("owner_private_bk2", type=Path)
    p.add_argument("owner_private_capture_plan", type=Path)
    p.add_argument("owner_private_bizhawk_log", type=Path)
    p.add_argument("owner_private_screenshot_directory", type=Path)
    p.add_argument("--min-neutral-frames", type=int, default=180)
    p.add_argument("--max-neutral-frames", type=int, default=1800)
    p.add_argument("--after-input-frame", type=int, default=1663)
    p.add_argument("--before-input-frame", type=int, default=FRAME_COUNT)
    args = p.parse_args()
    try:
        report = verify(
            args.owner_private_bk2, args.owner_private_capture_plan,
            args.owner_private_bizhawk_log, args.owner_private_screenshot_directory,
            minimum=args.min_neutral_frames, maximum=args.max_neutral_frames,
            after=args.after_input_frame, before=args.before_input_frame,
        )
    except (OSError, ValueError, TypeError, UnicodeError, KeyError, RuntimeError):
        p.error("private BK2 candidate capture audit unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
