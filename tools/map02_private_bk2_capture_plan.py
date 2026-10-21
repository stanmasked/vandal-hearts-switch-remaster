#!/usr/bin/env python3
"""Make a LOCAL ONLY bounded Octoshock PNG capture plan from a private BK2.

The plan contains private recorded controller indices, never real-map timing.
It must NEVER be uploaded to GitHub or treated as proof of PS1 scene identity.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

from tools.map02_private_bk2_neutral_review_windows import (
    inspect_movie, EXPECTED_FRAMES,
)

SCHEMA = "VH_MAP02_CAPTURE_PLAN_V1"
MAX_WINDOWS = 10


def plan_lines(source: Path, *, limit: int = 4, minimum: int = 180,
               maximum: int = 1800, after: int = 1663,
               before: int = EXPECTED_FRAMES) -> list[str]:
    if type(limit) is not int or not 1 <= limit <= MAX_WINDOWS:
        raise ValueError("private capture limit must be 1..10")
    result = inspect_movie(
        source, minimum=minimum, maximum=maximum,
        limit=limit, after=after, before=before,
    )
    windows = result["review_windows"]
    if not windows:
        raise ValueError("no button-neutral windows qualified")
    rows = []
    for group, item in enumerate(windows, 1):
        indices = item["suggested_local_review_input_indices_zero_based"]
        if (len(indices) != 3 or not indices[0] < indices[1] < indices[2]
                or indices[0] < 1663 or indices[2] >= EXPECTED_FRAMES):
            raise ValueError("source controller index interval inconsistent")
        for role, frame, held in zip(("before", "middle", "after"),
                                     indices, ("held", "neutral", "held")):
            rows.append((frame, group, role, held))
    rows.sort()
    if len({frame for frame, _, _, _ in rows}) != len(rows):
        raise ValueError("duplicate movie frame in capture plan")
    return [
        SCHEMA,
        "movie_frames=%d" % EXPECTED_FRAMES,
        "capture_count=%d" % len(rows),
    ] + [
        "%d,%s,%d,%s" % (group, role, frame, held)
        for frame, group, role, held in rows
    ]


def _reject_git_ancestors(path: Path) -> None:
    for parent in (path, *path.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("never process owner-private BK2/plans inside Git")


def write_private_plan(movie: Path, output: Path, **kwargs) -> int:
    # Resolve and privacy-check both paths BEFORE reading source bytes.
    source = Path(movie)
    if (not source.is_absolute() or source.is_symlink()
            or not source.is_file()):
        raise ValueError("source BK2 must be an absolute regular non-symlink file")
    source = source.resolve(strict=True)
    if not stat.S_ISREG(source.stat().st_mode):
        raise ValueError("source BK2 must be a regular file")
    _reject_git_ancestors(source)

    target = Path(output)
    if not target.is_absolute() or target.exists() or target.is_symlink():
        raise ValueError("private plan requires a new absolute output path")
    if not target.parent.is_dir():
        raise ValueError("private output requires an existing directory")
    resolved_parent = target.parent.resolve(strict=True)
    _reject_git_ancestors(resolved_parent)
    # Use the resolved parent for creation to avoid writing through a
    # symlinked parent after the Git-root check.
    target = resolved_parent / target.name
    if target.exists() or target.is_symlink():
        raise ValueError("refuse overwrite of private plan")

    # Parse and validate the entire source before creating output.
    rows = plan_lines(source, **kwargs)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write("\n".join(rows) + "\n")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if not stat.S_ISREG(target.stat().st_mode):
        raise ValueError("private plan must be regular")
    return len(rows) - 3


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("--private-plan-output", type=Path, required=True)
    parser.add_argument("--max-windows", type=int, default=4)
    parser.add_argument("--min-neutral-frames", type=int, default=180)
    parser.add_argument("--max-neutral-frames", type=int, default=1800)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=EXPECTED_FRAMES)
    a = parser.parse_args()
    try:
        count = write_private_plan(
            a.owner_private_bk2, a.private_plan_output,
            limit=a.max_windows, minimum=a.min_neutral_frames,
            maximum=a.max_neutral_frames, after=a.after_input_frame,
            before=a.before_input_frame,
        )
    except (OSError, ValueError, TypeError, RuntimeError):
        parser.error("owner-private BK2 capture plan unavailable")
    print("VH_MAP02_PRIVATE_CAPTURE_PLAN_READY frames=%d real_scene_authenticated=0" % count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
