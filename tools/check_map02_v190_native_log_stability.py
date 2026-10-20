#!/usr/bin/env python3
"""MAP02 v190: prove the ten private native PCSX logs remain byte-identical.

Read file content, inode identity and modification metadata immediately before
and after v189's 159 in-memory adversarial replays. Reject any replacement or
modification of input evidence, including same-byte inode swaps. The records
stay private; no digests, paths or transcript bytes are printed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat

from .check_map02_v189_adversarial_native_logs import audit_replay

PASS_MARKER = (
    "VH190_NATIVE_LOG_STABILITY_PASS modes=10 snapshots=21 mutations=159 "
    "sha256_unchanged=10 inode_unchanged=10 metadata_unchanged=10 "
    "original_retail=0"
)
MAX_LOG_SIZE = 2_000_000

def identity(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)

def sample_file(path: Path) -> tuple[str, tuple[int, int, int, int, int, int]]:
    """Capture an O_NOFOLLOW file descriptor's SHA-256 and stable identity."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= MAX_LOG_SIZE:
        raise ValueError("native witness must be a regular, bounded file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("native log audit requires O_NOFOLLOW support")
    flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        fd_before = os.fstat(fd)
        if not stat.S_ISREG(fd_before.st_mode) or identity(fd_before) != identity(before):
            raise ValueError("native log changed between path check and opening")
        with os.fdopen(fd, "rb", closefd=False) as source:
            data = source.read(MAX_LOG_SIZE + 1)
        fd_after = os.fstat(fd)
    finally:
        os.close(fd)
    after = path.lstat()
    if len(data) != fd_before.st_size or len(data) > MAX_LOG_SIZE:
        raise ValueError("native log truncated or expanded during digest read")
    if identity(before) != identity(fd_after) or identity(before) != identity(after):
        raise ValueError("native log metadata or inode changed during digest read")
    return (hashlib.sha256(data).hexdigest(), identity(before))

def snapshot_directory(directory: Path) -> tuple[tuple[str, tuple[int, ...]], ...]:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("private native witness directory must not be a symlink")
    out = []
    for mode in range(10):
        filename = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
        out.append(sample_file(directory / filename))
    # The ten independent emulator invocations must not alias one inode:
    # a hard link could otherwise make two labels share one mutable log.
    inodes = [(item[1][0], item[1][1]) for item in out]
    if len(set(inodes)) != 10:
        raise ValueError("native witness files share an inode across modes")
    return tuple(out)

def audit_stability(directory: Path) -> tuple[int, int, int]:
    """Reject even an otherwise well-formed log if evidence changes mid-audit."""
    original = snapshot_directory(directory)
    runs, snapshots, mutations = audit_replay(directory)
    after = snapshot_directory(directory)
    if original != after:
        raise ValueError("private native log hash, inode or metadata changed during replay")
    if (runs, snapshots, mutations) != (10, 21, 159):
        raise ValueError("incomplete native 159-mutation proof")
    return (runs, snapshots, mutations)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    args = parser.parse_args()
    audit_stability(args.verify_dir)
    print(PASS_MARKER)

if __name__ == "__main__":
    main()
