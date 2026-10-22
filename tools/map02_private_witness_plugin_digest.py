#!/usr/bin/env python3
"""Owner-local hash pin for the installed experimental BizHawk 2.11 DLL.

Only inspects the caller-supplied local DLL. Never prints names, digests,
file bytes, process IDs or PlayStation content. A successful hash match is
not proof that BizHawk has loaded the plugin, let alone original game media.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

MAX_CORE_DLL_BYTES = 16 * 1024 * 1024


def require_pinned_core_witness_dll(path: Path, expected_sha256: str) -> None:
    """Fail closed when local plugin differs from an independently pinned hash.

    Callers also enforce that this file is directly under the matching
    EmuHawk.exe installation's ExternalTools folder. The stat checks prevent
    accepting a change during this single pass; they cannot prevent a future
    modification, hence callers must recheck around emulator execution.
    """
    if (not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None):
        raise ValueError("private core DLL digest pin is not exactly 64 hex digits")
    plugin = Path(path)
    if not plugin.is_absolute() or plugin.is_symlink():
        raise ValueError("private core DLL must be a direct absolute local file")
    try:
        before = plugin.stat()
        if (not stat.S_ISREG(before.st_mode)
                or before.st_size <= 0
                or before.st_size > MAX_CORE_DLL_BYTES):
            raise ValueError("private core DLL size or type is not supported")
        hasher = hashlib.sha256()
        with plugin.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                    before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
                raise ValueError("private core DLL changed before hashing")
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                hasher.update(block)
            finished = os.fstat(handle.fileno())
        after = plugin.stat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("private core DLL changed during hashing")
        if (finished.st_dev, finished.st_ino, finished.st_size, finished.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError("private core DLL changed while read")
        if hasher.hexdigest() != expected_sha256.lower():
            raise ValueError("private installed core DLL differs from pinned build")
    except OSError as exc:
        raise ValueError("private installed core DLL cannot be verified") from exc
