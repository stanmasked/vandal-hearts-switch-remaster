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

# Explicit local, disk-backed Linux filesystems, rather than permitting
# unknown FUSE, remote, pseudo and ephemeral mounts by default. This is
# deliberately conservative; extend only after a reviewed persistence test.
PERSISTENT_LOCAL_FS = frozenset({
    "ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "f2fs",
    "bcachefs", "jfs", "nilfs2",
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


def _mounts(content: str) -> list[tuple[Path, str, bool, int]]:
    if not isinstance(content, str) or len(content) > 8 * 1024**2:
        _fail()
    found: list[tuple[Path, str, bool, int]] = []
    for line in content.splitlines():
        left, separator, right = line.partition(" - ")
        fields, filesystem = left.split(), right.split()
        if not separator or len(fields) < 6 or len(filesystem) < 3:
            _fail()
        mount_path = Path(_unescape_mountpoint(fields[4]))
        if not mount_path.is_absolute() or ".." in mount_path.parts:
            _fail()
        # Linux exposes the mounted filesystem's actual st_dev here.
        # The type alone is insufficient: a stale/buried ext4 entry
        # can otherwise hide a different filesystem mounted on top.
        device_text = fields[2]
        if re.fullmatch(r"[0-9]{1,10}:[0-9]{1,10}", device_text) is None:
            _fail()
        major, minor = (int(v) for v in device_text.split(":"))
        try:
            device = os.makedev(major, minor)
        except (OSError, ValueError, OverflowError):
            _fail()
        mount_options = fields[5].split(",")
        super_options = filesystem[2].split(",")
        # A writable owner runtime cannot rely on a read-only mount.
        writable = ("rw" in mount_options and "ro" not in mount_options
                    and "ro" not in super_options)
        found.append((mount_path, filesystem[0].lower(), writable, device))
    if not any(p == Path("/") for p, _, _, _ in found):
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
            matches = [(point, fs, writable, device)
                       for point, fs, writable, device in mounts
                       if candidate == point or candidate.is_relative_to(point)]
            if not matches:
                _fail()
            longest = max(len(item[0].parts) for item in matches)
            closest = [item for item in matches
                       if len(item[0].parts) == longest]
            # Duplicate stacked entries at the exact mountpoint must
            # agree. A hidden ext4 entry does not attest the upper mount.
            if len({(fs, writable, device)
                    for _, fs, writable, device in closest}) != 1:
                _fail()
            _, filesystem, writable, mounted_device = closest[0]
            if (mounted_device != details.st_dev
                    or filesystem not in PERSISTENT_LOCAL_FS or not writable):
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
    except (OSError, ValueError, TypeError, AttributeError, UnicodeError,
            OverflowError):
        _fail()
