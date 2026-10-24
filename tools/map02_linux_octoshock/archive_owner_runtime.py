#!/usr/bin/env python3
"""Owner-only MAP02 Linux runtime archive readback gate.

Compare an existing staged private runtime to a separately restored copy
downloaded from the owner's private archive. This tool neither uploads nor
downloads data. It prints no file paths, per-file hashes or private contents.
A valid local comparison does not itself prove that Drive stored the copy.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat

from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime

MAX_ENTRIES = 50000
BLOCK_SIZE = 1024 * 1024


class ArchiveReadbackError(ValueError):
    """A generic rejection that does not disclose owner-private filenames."""


def _fail() -> None:
    raise ArchiveReadbackError("owner-private runtime archive readback rejected")


def _root(value: Path) -> Path:
    raw = Path(value)
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        _fail()
    root = raw.resolve(strict=True)
    info = root.stat()
    if (not stat.S_ISDIR(info.st_mode) or
            stat.S_IMODE(info.st_mode) != 0o700 or
            info.st_uid != os.geteuid()):
        _fail()
    return root


def _digest(path: Path, expected: os.stat_result) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        identity = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
        if (not stat.S_ISREG(before.st_mode) or
                identity(before) != identity(expected)):
            _fail()
        hasher = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(BLOCK_SIZE), b""):
                hasher.update(chunk)
        after = os.fstat(fd)
        now = os.stat(path, follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(now):
            _fail()
        return hasher.hexdigest()
    finally:
        os.close(fd)


def _inventory(root: Path) -> tuple[dict[str, tuple], int, int]:
    records: dict[str, tuple] = {}
    total = 0
    files = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda e: e.name)
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if not relative or relative.startswith("/") or len(records) >= MAX_ENTRIES:
                _fail()
            info = os.stat(path, follow_symlinks=False)
            mode = stat.S_IMODE(info.st_mode)
            if info.st_uid != os.geteuid():
                _fail()
            if stat.S_ISDIR(info.st_mode):
                records[relative] = ("directory", mode)
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                records[relative] = ("file", mode, info.st_size, _digest(path, info))
                total += info.st_size
                files += 1
            else:
                # No symlinks, FIFOs, sockets or block/character devices.
                _fail()
    if not files:
        _fail()
    return records, files, total


def verify_archive_readback(source_value: Path, restored_value: Path,
                            trusted_pin_file: Path) -> dict[str, object]:
    """Require two disjoint complete trees, each independently manifest-pinned."""
    try:
        source = _root(source_value)
        restored = _root(restored_value)
        if (source == restored or source in restored.parents
                or restored in source.parents):
            _fail()
        pin = Path(trusted_pin_file)
        if (not pin.is_absolute() or pin.is_relative_to(source)
                or pin.is_relative_to(restored)):
            _fail()
        for root in (source, restored):
            result = verify_runtime(
                root, trusted_manifest_pin_file=pin,
                require_trusted_pin=True,
            )
            if (result.get("verified") is not True or
                    result.get("trusted_manifest_pin_verified") is not True or
                    result.get("capture_ready") is not False):
                _fail()
        first, count, total = _inventory(source)
        second, restored_count, restored_total = _inventory(restored)
        if (first != second or count != restored_count
                or total != restored_total):
            _fail()
    except (OSError, RuntimeError, TypeError, ValueError):
        _fail()
    return {
        "source_and_restored_match": True,
        "trusted_manifest_pin_verified_twice": True,
        "files": count,
        "total_bytes": total,
        "capture_ready": False,
        "drive_upload_authenticated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_source_runtime", type=Path)
    parser.add_argument("absolute_drive_restored_runtime", type=Path)
    parser.add_argument("--trusted-manifest-pin-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_archive_readback(
            args.absolute_source_runtime,
            args.absolute_drive_restored_runtime,
            args.trusted_manifest_pin_file,
        )
    except (ArchiveReadbackError, OSError, ValueError):
        print("VH_MAP02_RUNTIME_ARCHIVE_READBACK_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_RUNTIME_ARCHIVE_READBACK_PASS files=%d bytes=%d "
          "trusted_pin_verified_twice=1 drive_upload_authenticated=0 "
          "capture_ready=0" % (result["files"], result["total_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
