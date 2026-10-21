#!/usr/bin/env python3
"""Check owner-local BizHawk frame markers; NEVER assert MAP02 from markers."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import stat

SCHEMA = "vh.map02.private-replay-markers.v1"
MARKER = re.compile(
    r"^VH_PRIVATE_REPLAY_MARKER counter=([0-9]+) "
    r"candidate_input=([0-9]+) mode=PLAY scene=unverified$"
)
MAX_LOG_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 32 * 1024
MAX_MARKERS = 200


def _read_regular(path: Path, limit: int) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("requires a regular owner-local file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("local file exceeds size bound")
    with path.open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("local file exceeds size bound")
    return raw.decode("utf-8")


def verify(inspection_json: Path, marker_log: Path) -> dict:
    inspection = json.loads(_read_regular(inspection_json, MAX_REPORT_BYTES))
    if not isinstance(inspection, dict) or inspection.get("schema") != "vh.psx.bizhawk.private-bk2-input-inspection.v1":
        raise ValueError("unsupported private BK2 inspection schema")
    frames = inspection.get("input_log_frame_count")
    if type(frames) is not int or not 1 <= frames <= 1_500_000:
        raise ValueError("invalid BK2 frame count")
    if inspection.get("platform") != "PSX" or inspection.get("core") != "Octoshock" or inspection.get("game") != "Vandal Hearts (USA)":
        raise ValueError("mismatched game or emulator core")
    if inspection.get("original_ps1_game_image_authenticated") is not False or inspection.get("map02_scene_frame_identified") is not False:
        raise ValueError("inspection must not claim game or scene authentication")
    raw = _read_regular(marker_log, MAX_LOG_BYTES)
    observed = []
    for line in raw.splitlines():
        if not line.startswith("VH_PRIVATE_REPLAY_MARKER"):
            continue  # Ignore unrelated BizHawk console output, never echo it.
        match = MARKER.fullmatch(line)
        if not match:
            raise ValueError("invalid private marker record")
        counter, candidate = (int(x) for x in match.groups())
        if counter <= 0 or candidate != counter - 1 or candidate >= frames:
            raise ValueError("unusable emulator counter or out-of-range candidate")
        if observed and counter <= observed[-1]:
            raise ValueError("nonmonotonic or duplicate emulator marker")
        observed.append(counter)
        if len(observed) > MAX_MARKERS:
            raise ValueError("too many private markers")
    if not observed:
        raise ValueError("no valid movie-playback markers")
    return {
        "schema": SCHEMA,
        "markers_count": len(observed),
        "first_emulator_counter": observed[0],
        "last_emulator_counter": observed[-1],
        "all_candidate_frames_inside_movie": True,
        "movie_mode_when_marked": "PLAY",
        "scene_observation_authenticated": False,
        "map02_scene_frame_identified": False,
        "emu_to_movie_frame_offset_verified": False,
        "ps1_gpu_captures_read": False,
        "private_movie_or_screenshots_uploaded": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_inspection_json", type=Path)
    p.add_argument("private_marker_log", type=Path)
    args = p.parse_args()
    try:
        output = verify(args.private_inspection_json, args.private_marker_log)
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError):
        p.error("owner-private replay marker validation unavailable")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
