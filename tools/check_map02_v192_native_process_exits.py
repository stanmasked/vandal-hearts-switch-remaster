#!/usr/bin/env python3
"""MAP02 v192 — bind native PCSX subprocess exit codes to exact private logs.

Require exactly ten sequential mode/return-code/SHA-256 lines written by
the pinned PCSX native shell immediately after each actual subprocess exits.
The manifest and native log bytes stay private; the verifier prints only an
aggregate result. The original retail game is not executed here.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat

from .check_map02_v190_native_log_stability import snapshot_directory
from .check_map02_v191_native_phase_markers import audit_directory as audit_phase_directory

MANIFEST = "v192-native-exits.txt"
LINE = re.compile(r"mode=([0-9]) exit=([0-9]+) sha256=([0-9a-f]{64})")
MARKER = (
    "VH192_NATIVE_PROCESS_EXIT_RECEIPTS_PASS modes=10 positive_exit=0 "
    "negative_exits=9 native_exit=86 sha256_matches=10 "
    "phase_passes=22 mutations=159 original_retail=0"
)

def verified_manifest(directory: Path) -> list[str]:
    """Open a bounded regular manifest without following symbolic links."""
    path = directory / MANIFEST
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > 2048 or before.st_size < 10:
        raise ValueError("missing, linked, or oversized private exit manifest")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("O_NOFOLLOW is required to read private native exit receipts")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ):
            raise ValueError("native exit receipt replaced before open")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(2049)
        closed = os.fstat(fd)
    finally:
        os.close(fd)
    after = path.lstat()
    if any(
        (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns
        ) for st in (opened, closed, after)
    ):
        raise ValueError("native exit receipt changed during read")
    if len(data) != before.st_size or len(data) > 2048:
        raise ValueError("inconsistent native exit receipt length")
    try:
        return data.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("non-ASCII private exit receipt") from error

def verify_exits(directory: Path) -> tuple[int, int, int]:
    """Cross-check process exit/status evidence against actual log bytes."""
    original_logs = snapshot_directory(directory)
    rows = verified_manifest(directory)
    if len(rows) != 10:
        raise ValueError("expected exactly ten native process-exit receipts")
    seen = set()
    for expected_mode, row in enumerate(rows):
        match = LINE.fullmatch(row)
        if not match:
            raise ValueError("malformed or hidden native process-exit receipt")
        mode = int(match.group(1))
        exit_code = int(match.group(2))
        digest = match.group(3)
        if mode != expected_mode or mode in seen:
            raise ValueError("duplicate, missing or reordered native process-exit receipt")
        seen.add(mode)
        expected_exit = 0 if mode == 0 else 86
        if exit_code != expected_exit:
            raise ValueError(f"mode {mode}: native exit does not match RAM refusal")
        name = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
        source_path = directory / name
        source_bytes = source_path.read_bytes()
        if digest != hashlib.sha256(source_bytes).hexdigest():
            raise ValueError(f"mode {mode}: native exit SHA-256 differs from actual log")
    if snapshot_directory(directory) != original_logs:
        raise ValueError("native log identity changed during exit-receipt check")
    if verified_manifest(directory) != rows:
        raise ValueError("exit receipts mutated during native phase recheck")
    modes, snaps, faults, phases = audit_phase_directory(directory)
    if (modes, snaps, faults, phases) != (10, 21, 159, 22):
        raise ValueError("cannot attest exits without genuine PS1 phase evidence")
    if snapshot_directory(directory) != original_logs or verified_manifest(directory) != rows:
        raise ValueError("native process exit or source logs changed after phase verification")
    return (10, 9, 10)

def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--verify-dir", type=Path, required=True)
    args = cli.parse_args()
    assert verify_exits(args.verify_dir) == (10, 9, 10)
    print(MARKER)

if __name__ == "__main__":
    main()
