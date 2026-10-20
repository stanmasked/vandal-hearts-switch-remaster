#!/usr/bin/env python3
"""Read-only prelaunch directory layout audit for a private MAP02 PC session.

This checks filesystem layout only. The signed build, retail game inputs,
actual subprocess, in-process GPU events and pixels are validated elsewhere.
Neither this module nor its CLI reads retail image contents or launches code.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from tools.map02_local_capture_handoff import PLAN

ROLES = ("source", "native", "scoped", "handoff",
         "cycle", "preview", "preoverlay")
CAPTURE_ROLES = ("native", "scoped", "cycle", "preview", "preoverlay")


def _directory_identity(path, role):
    # lstat first to reject even a symlink whose target is owner-private.
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("missing private MAP02 directory: " + role) from None
    if (not stat.S_ISDIR(info.st_mode) or
            info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("private MAP02 directory is not owner-only: " + role)
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_mtime_ns, info.st_ctime_ns)


def _check_plan(root):
    # Prelaunch requires the exclusively prepared plan, not a final process
    # receipt. Do not consume its content or treat the file as authenticated.
    if {p.name for p in root.iterdir()} != {PLAN}:
        raise ValueError("prelaunch handoff must contain only its plan")
    try:
        item = (root / PLAN).lstat()
    except OSError:
        raise ValueError("missing private MAP02 prelaunch plan") from None
    if (not stat.S_ISREG(item.st_mode) or
            item.st_uid != os.geteuid() or item.st_nlink != 1 or
            stat.S_IMODE(item.st_mode) != 0o600 or
            not 0 < item.st_size <= 4096):
        raise ValueError("invalid private MAP02 prelaunch plan metadata")


def inspect_private_launch_layout(source, native, scoped, handoff,
                                  cycle, preview, preoverlay):
    """Validate exactly seven disjoint, owner-private directories.

    This never inspects source-game data and cannot certify a game's launch.
    """
    roots = dict(zip(
        ROLES, map(lambda p: Path(p).absolute(),
                   (source, native, scoped, handoff,
                    cycle, preview, preoverlay))))
    before = {role: _directory_identity(path, role)
              for role, path in roots.items()}
    real = {role: path.resolve() for role, path in roots.items()}
    names = list(ROLES)
    for i, role in enumerate(names):
        for other in names[i + 1:]:
            a, b = real[role], real[other]
            if (a == b or a in b.parents or b in a.parents or
                    before[role][:2] == before[other][:2]):
                raise ValueError("private MAP02 launch directories overlap")
    for role in CAPTURE_ROLES:
        if any(roots[role].iterdir()):
            raise ValueError("prelaunch MAP02 capture directory is not empty: " + role)
    _check_plan(roots["handoff"])
    # Detect a concurrent rename or write during this finite preflight.
    if any(_directory_identity(path, role) != before[role]
           for role, path in roots.items()):
        raise ValueError("private MAP02 launch directory changed during audit")
    for role in CAPTURE_ROLES:
        if any(roots[role].iterdir()):
            raise ValueError("prelaunch MAP02 capture directory changed: " + role)
    _check_plan(roots["handoff"])
    return {
        "schema": "vh.map02.prelaunch-directory-layout.v1",
        "private_directory_roles_checked": len(ROLES),
        "capture_output_directories_empty": len(CAPTURE_ROLES),
        "single_private_handoff_plan_present": True,
        "prelaunch_layout_ready": True,
        "original_pc_elf_verified": False,
        "original_game_image_verified": False,
        "original_gameplay_executed": False,
        "map02_frame_authenticated": False,
        "private_game_bytes_read": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ROLES:
        parser.add_argument("private_" + role + "_directory", type=Path)
    args = parser.parse_args()
    try:
        report = inspect_private_launch_layout(
            *(getattr(args, "private_" + role + "_directory")
              for role in ROLES))
    except (OSError, ValueError):
        # A path from a user's owned CD/ELF must never reach stderr.
        parser.error("private MAP02 prelaunch layout unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
