#!/usr/bin/env python3
"""Fail-closed, standard-library-only pre-execution integrity check for MAP02 kit.

This checks against the local files.json receipts. It detects accidental or
unilateral modification and rejects injected extra files/symlinks before
importing any packaged diagnostic code. The manifest itself is NOT signed:
authenticate the ZIP with an independently published SHA-256 before use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

SCHEMA = "vh.map02.intel-mac.offline-evidence-kit.v1"
PUBLIC = "upstream/platform/pc/src/pc_raster.c"
PUBLIC_GIT_BLOB = "ba8a05d161ad778c0b75e452ff0a11ed163c65cd"
ROOT_FILES = {"README.md", "run-selfcheck.sh", "verify-kit.py", "files.json"}
MAX_FILES = 180
MAX_SINGLE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 6 * 1024 * 1024


def safe_name(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    p = PurePosixPath(name)
    if p.is_absolute() or p.as_posix() != name or ".." in p.parts:
        return False
    if name in ROOT_FILES or name == PUBLIC:
        return True
    if len(p.parts) < 2:
        return False
    if p.parts[0] == "source":
        return p.suffix == ".h"
    if p.parts[0] == "tools":
        return p.suffix == ".py"
    if p.parts[0] == "tests":
        return p.suffix == ".py" or name == "tests/test_map02_vram4_frame.c"
    return False


def scan(root: Path) -> dict:
    """Enumerate no-follow regular files; reject extra files and symlink dirs."""
    result = {}
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                relative = prefix + entry.name
                if entry.is_symlink():
                    raise ValueError("a symlink is not permitted in kit")
                if entry.is_dir(follow_symlinks=False):
                    # Only structural parents of the approved source roots.
                    if not (
                        relative in ("tools", "tests", "source", "upstream",
                                     "upstream/platform", "upstream/platform/pc",
                                     "upstream/platform/pc/src")
                    ):
                        raise ValueError("unexpected kit directory")
                    pending.append((Path(entry.path), relative + "/"))
                    continue
                if not safe_name(relative):
                    raise ValueError("unexpected kit member")
                info = entry.stat(follow_symlinks=False)
                if (not stat.S_ISREG(info.st_mode)
                        or info.st_size < 0 or info.st_size > MAX_SINGLE_BYTES):
                    raise ValueError("kit member is not a bounded regular file")
                result[relative] = Path(entry.path)
                if len(result) > MAX_FILES + len(ROOT_FILES):
                    raise ValueError("kit member count exceeded")
    return result


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def verify(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("kit root is not a regular directory")
    files = scan(root)
    if "files.json" not in files:
        raise ValueError("kit manifest absent")
    raw = files["files.json"].read_bytes()
    if len(raw) > MAX_SINGLE_BYTES or b"\0" in raw:
        raise ValueError("kit manifest encoding invalid")
    manifest = json.loads(raw.decode("utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "files", "public_pc_raster_git_blob_sha1",
        "retail_assets_included", "original_gpu_vram_included",
        "private_machine_paths_included", "macos_catalina_runtime_proven",
    }:
        raise ValueError("kit manifest fields invalid")
    if (
        manifest["schema"] != SCHEMA
        or manifest["public_pc_raster_git_blob_sha1"] != PUBLIC_GIT_BLOB
        or any(manifest[k] is not False for k in (
            "retail_assets_included", "original_gpu_vram_included",
            "private_machine_paths_included", "macos_catalina_runtime_proven",
        ))
    ):
        raise ValueError("kit provenance constraints changed")
    receipts = manifest["files"]
    if not isinstance(receipts, dict) or not 15 <= len(receipts) <= MAX_FILES:
        raise ValueError("kit digest list invalid")
    if not {"README.md", "run-selfcheck.sh", "verify-kit.py", PUBLIC}.issubset(receipts):
        raise ValueError("kit entrypoints or public source missing from manifest")
    if set(files) != set(receipts) | {"files.json"}:
        raise ValueError("kit file set differs from manifest")
    total = len(raw)
    public_blob = None
    for name, expected in receipts.items():
        if (
            not safe_name(name)
            or not isinstance(expected, str)
            or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
        ):
            raise ValueError("kit digest member invalid")
        data = files[name].read_bytes()
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("kit payload exceeds source limits")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("kit member digest mismatch")
        if name == PUBLIC:
            public_blob = _git_blob_sha1(data)
    if public_blob != PUBLIC_GIT_BLOB:
        raise ValueError("pinned public PC source changed")

    return {
        "schema": "vh.map02.intel-mac.offline-preexec-verify.v1",
        "file_digests_verified": len(receipts),
        "public_pc_source_git_blob_verified": True,
        "no_unlisted_files_or_symlinks": True,
        "retail_assets_read": False,
        "private_user_data_read": False,
        "kit_signature_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        # Avoid emitting caller-private paths or source bytes.
        parser.error("offline kit integrity verification failed")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
