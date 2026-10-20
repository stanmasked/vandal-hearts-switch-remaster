#!/usr/bin/env python3
"""MAP02 v193: attest the native synthetic PS-X EXE across ten PCSX runs.

The pinned native workflow records the private guest executable's SHA-256
immediately before and after each of ten actual subprocess invocations.
This verifier matches each receipt to that same original EXE and the
previous v192 native process exit and log proof. Nothing private is printed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import stat

from .check_map02_v190_native_log_stability import sample_file
from .check_map02_v192_native_process_exits import verify_exits

EXE_NAME = "V183_RAM_CORRECT.EXE"
MANIFEST = "v193-native-exe-receipts.txt"
LINE = re.compile(r"mode=([0-9]) before=([0-9a-f]{64}) after=([0-9a-f]{64})")
PASS_MARKER = (
    "VH193_NATIVE_GUEST_EXE_IDENTITY_PASS modes=10 guest_exe_hashes=20 "
    "exe_digest_unchanged=1 native_exit_receipts=10 log_hashes=10 "
    "original_retail=0"
)


def private_receipts(directory: Path) -> tuple[str, ...]:
    """Read exactly the private manifest with no symlink or read-time swap."""
    path = directory / MANIFEST
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 10 <= before.st_size <= 2048:
        raise ValueError("native EXE receipt manifest is not a bounded regular file")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("native EXE receipt manifest requires O_NOFOLLOW")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        attrs = lambda st: (
            st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns,
        )
        if attrs(opened) != attrs(before):
            raise ValueError("native EXE manifest changed while opening")
        with os.fdopen(fd, "rb", closefd=False) as source:
            payload = source.read(2049)
        after_read = os.fstat(fd)
    finally:
        os.close(fd)
    if any(attrs(x) != attrs(before) for x in (after_read, path.lstat())):
        raise ValueError("native EXE manifest changed during read")
    if len(payload) != before.st_size:
        raise ValueError("native EXE manifest size changed during read")
    try:
        return tuple(payload.decode("ascii").splitlines())
    except UnicodeError as exc:
        raise ValueError("non-ASCII native EXE receipt") from exc


def audit_executable(directory: Path) -> tuple[int, int, int]:
    """Bind the same SHA-256 guest binary to all ten true native exits."""
    exe = directory / EXE_NAME
    before_exe = sample_file(exe)
    receipts = private_receipts(directory)
    if len(receipts) != 10:
        raise ValueError("missing or surplus native EXE receipts")
    for expected_mode, row in enumerate(receipts):
        parsed = LINE.fullmatch(row)
        if parsed is None or int(parsed.group(1)) != expected_mode:
            raise ValueError("misordered, forged, duplicate or hidden native EXE receipt")
        before_digest, after_digest = parsed.group(2), parsed.group(3)
        if before_digest != before_exe[0] or after_digest != before_exe[0]:
            raise ValueError(f"mode {expected_mode}: synthetic guest EXE digest differs")
    if sample_file(exe) != before_exe or private_receipts(directory) != receipts:
        raise ValueError("private guest executable or receipts changed before exit audit")
    if verify_exits(directory) != (10, 9, 10):
        raise ValueError("missing native PCSX exit and log hash lineage")
    if sample_file(exe) != before_exe or private_receipts(directory) != receipts:
        raise ValueError("private guest executable or receipts changed after exit audit")
    return (10, 20, 10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    options = parser.parse_args()
    if audit_executable(options.verify_dir) != (10, 20, 10):
        raise ValueError("native synthetic EXE identity audit failed")
    print(PASS_MARKER)


if __name__ == "__main__":
    main()
