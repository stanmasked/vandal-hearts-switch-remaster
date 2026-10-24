#!/usr/bin/env python3
"""Stage551 fail-closed persistent Linux host and storage preflight.

This checks the OWNER machine, not GitHub CI. It does not invoke rclone,
read game data or create files. Synthetic mount tables are test-only.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import stat
import sys
from typing import Callable, Mapping, Sequence

EPHEMERAL_FS = frozenset({
    "tmpfs", "ramfs", "overlay", "aufs", "squashfs", "iso9660",
    "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2",
})
EPHEMERAL_PATHS = (Path("/tmp"), Path("/var/tmp"), Path("/run"),
                   Path("/dev/shm"), Path("/var/run"))
CI_INDICATORS = ("CI", "GITHUB_ACTIONS", "RUNNER_TEMP", "RUNNER_WORKSPACE",
                 "GITHUB_WORKSPACE", "GITHUB_RUN_ID")
MINIMUM_PREPARE_BYTES = 4 * 1024**3
MINIMUM_PUBLISH_BYTES = 2 * 1024**3


class PersistentHostError(ValueError):
    pass


def _fail() -> None:
    raise PersistentHostError("MAP02 owner host is not verified persistent private Linux storage")


def _unescape_mountpoint(raw: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), raw)


def _mounts(content: str) -> list[tuple[Path, str]]:
    if not isinstance(content, str) or len(content) > 8 * 1024**2:
        _fail()
    found: list[tuple[Path, str]] = []
    for line in content.splitlines():
        left, separator, right = line.partition(" - ")
        fields, filesystem = left.split(), right.split()
        if not separator or len(fields) < 5 or not filesystem:
            _fail()
        mount_path = Path(_unescape_mountpoint(fields[4]))
        if not mount_path.is_absolute() or ".." in mount_path.parts:
            _fail()
        found.append((mount_path, filesystem[0].lower()))
    if not any(p == Path("/") for p, _ in found):
        _fail()
    return found


def verify_persistent_private_host(
    directories: Sequence[Path],
    *,
    minimum_free_bytes: int,
    mountinfo: str | None = None,
    environ: Mapping[str, str] | None = None,
    host_platform: str | None = None,
    machine: str | None = None,
    disk_usage: Callable = shutil.disk_usage,
    temporary_prefixes: Sequence[Path] = EPHEMERAL_PATHS,
) -> dict[str, object]:
    """Reject CI, unsafe mountpoint, public directory and insufficient space.

    Passing a fabricated mountinfo/environ or prefix policy is only for
    unit-test simulation. Production calls NEVER accept these overrides.
    """
    try:
        if (not isinstance(directories, (tuple, list)) or not directories
                or type(minimum_free_bytes) is not int
                or minimum_free_bytes < 512 * 1024**2):
            _fail()
        active_platform = sys.platform if host_platform is None else host_platform
        arch = platform.machine() if machine is None else machine
        if not active_platform.startswith("linux") or arch.lower() not in ("x86_64", "amd64"):
            _fail()
        env = os.environ if environ is None else environ
        if any(env.get(name) for name in CI_INDICATORS):
            _fail()
        if mountinfo is None:
            text = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
        else:
            text = mountinfo
        mounts = _mounts(text)
        devices = set()
        for original in directories:
            candidate = Path(original)
            if (not candidate.is_absolute() or candidate.is_symlink()
                    or not candidate.is_dir()
                    or candidate.resolve(strict=True) != candidate):
                _fail()
            details = candidate.stat()
            if (not stat.S_ISDIR(details.st_mode)
                    or details.st_uid != os.geteuid()
                    or stat.S_IMODE(details.st_mode) != 0o700):
                _fail()
            if any(candidate == prefix or candidate.is_relative_to(prefix)
                   for prefix in temporary_prefixes):
                _fail()
            for ancestor in (candidate, *candidate.parents):
                marker = ancestor / ".git"
                if marker.exists() or marker.is_symlink():
                    _fail()
            matches = [(point, fs) for point, fs in mounts
                       if candidate == point or candidate.is_relative_to(point)]
            if not matches:
                _fail()
            _, filesystem = max(matches, key=lambda pair: len(pair[0].parts))
            if filesystem in EPHEMERAL_FS:
                _fail()
            if disk_usage(candidate).free < minimum_free_bytes:
                _fail()
            devices.add(details.st_dev)
        return {
            "schema": "vh.map02.owner-persistent-host-preflight.v1",
            "platform_accepted": True,
            "ci_environment_rejected": True,
            "private_owner_directories_verified": len(directories),
            "checked_filesystem_devices": len(devices),
            "minimum_free_bytes_verified": minimum_free_bytes,
            "game_media_used": False,
            "drive_upload_performed": False,
            "capture_ready": False,
        }
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError):
        _fail()
