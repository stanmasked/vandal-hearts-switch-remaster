#!/usr/bin/env python3
"""Offline owner-local integrity check for the staged MAP02 Linux runtime.

Reads only the caller's local no-media runtime directory. It never consumes
disc, BIOS, BK2, screenshots or captures, and never emits private paths/hashes.
A verified build is NOT proof of PSX power-on or MAP02 gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

SCHEMA = "vh.map02.owner-local-runtime.v1"
BIZHAWK_ARCHIVE_SHA256 = "cdaf9650d880bae660d63a388430f630b8d8a96b1ba59ebf0e0195a645c3bab8"
UPSTREAM_COMMIT = "427556b5ef3ac437eba754d90c5e7e9096c9a8df"
UPSTREAM_TREE = "24f43550ff70776a86a2d7b64d09993dd09021d9"
NATIVE_NAME = "liboctoshock.dll.so"
HASH = re.compile(r"[0-9a-f]{64}\Z")


class RuntimeVerificationError(ValueError):
    pass


def _fail() -> None:
    raise RuntimeVerificationError("staged runtime integrity or privacy invariant failed")


def _file(root: Path, relative: str, *, mode: int | None = None) -> Path:
    if not isinstance(relative, str) or not relative:
        _fail()
    candidate = Path(relative)
    if candidate.is_absolute() or "." in candidate.parts or ".." in candidate.parts:
        _fail()
    path = root / candidate
    current = path
    while current != root:
        if current.is_symlink():
            _fail()
        current = current.parent
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        _fail()
    if mode is not None and stat.S_IMODE(path.stat().st_mode) != mode:
        _fail()
    return path


def _bytes(root: Path, relative: str, *, maximum: int | None = None,
           mode: int | None = None) -> bytes:
    path = _file(root, relative, mode=mode)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or (
                maximum is not None and before.st_size > maximum):
            _fail()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read()
        after = os.fstat(fd)
        now = path.stat()
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(now):
            _fail()
        if maximum is not None and len(data) > maximum:
            _fail()
        return data
    finally:
        os.close(fd)


def _sha(root: Path, relative: str, digest: str) -> None:
    if not isinstance(digest, str) or HASH.fullmatch(digest) is None:
        _fail()
    path = _file(root, relative)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            _fail()
        calculated = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                calculated.update(block)
        after = os.fstat(fd)
        current = path.stat()
        fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if fields(before) != fields(after) or fields(after) != fields(current):
            _fail()
        if calculated.hexdigest() != digest:
            _fail()
    finally:
        os.close(fd)


def verify_runtime(root_value: Path) -> dict[str, object]:
    raw = Path(root_value)
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        _fail()
    root = raw.resolve(strict=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        _fail()
    try:
        manifest = json.loads(_bytes(
            root, "map02-owner-runtime-manifest.json", maximum=65536, mode=0o600
        ))
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            _fail()
        for field in ("game_media_used", "bios_used", "bk2_used", "game_loaded",
                      "psx_capture_ready"):
            if manifest.get(field) is not False:
                _fail()
        source = manifest["source"]
        official = manifest["official_bizhawk"]
        native = manifest["native_octoshock"]
        plugin = manifest["experimental_witness_plugin"]
        smoke = manifest["smoke_tests"]
        if (source["commit"] != UPSTREAM_COMMIT or
            source["octoshock_tree"] != UPSTREAM_TREE or
            source["source_file_count"] != 41 or
            official["version"] != "2.11" or
            official["archive_sha256"] != BIZHAWK_ARCHIVE_SHA256 or
            native["filename"] != NATIVE_NAME or
            native["managed_exports_verified"] != 32 or
            plugin["filename"] != "ExternalTools/VhMap02CoreWitness.dll"):
            _fail()
        for field in ("native_abi", "official_managed_binding_synthetic_firmware",
                      "emuhawk_no_media_startup"):
            if smoke.get(field) != "pass":
                _fail()
        _file(root, "EmuHawk.exe")
        _file(root, "EmuHawkMono.sh")
        cores = sorted(
            x.relative_to(root).as_posix() for x in root.rglob("BizHawk.Emulation.Cores.dll")
            if x.is_file()
        )
        if not cores:
            _fail()
        for core in cores:
            _sha(root, core, official["core_assembly_sha256"])
        expected_native = sorted((Path(c).parent / NATIVE_NAME).as_posix() for c in cores)
        declared = native["installed_relative_paths"]
        if not isinstance(declared, list) or declared != expected_native:
            _fail()
        for name in declared:
            _sha(root, name, native["sha256"])
        present_native = sorted(
            x.relative_to(root).as_posix() for x in root.rglob(NATIVE_NAME)
            if x.is_file()
        )
        if present_native != expected_native:
            _fail()
        _sha(root, plugin["filename"], plugin["sha256"])
        for digest in (official["core_assembly_sha256"], native["sha256"], plugin["sha256"]):
            if not isinstance(digest, str) or HASH.fullmatch(digest) is None:
                _fail()
        pins = (
            "export VH_MAP02_CORE_EXPECTED_CORE_ASSEMBLY_SHA256=" + official["core_assembly_sha256"] + "\n"
            "export VH_MAP02_CORE_EXPECTED_NATIVE_MODULE_SHA256=" + native["sha256"] + "\n"
            "export VH_MAP02_PRIVATE_WITNESS_DLL_SHA256=" + plugin["sha256"] + "\n"
            "export VH_MAP02_CORE_EXPECTED_DLL_SHA256=" + plugin["sha256"] + "\n"
        ).encode("ascii")
        if _bytes(root, "map02-owner-runtime-pins.env", maximum=1024, mode=0o600) != pins:
            _fail()
    except (KeyError, TypeError, AttributeError, UnicodeError, ValueError, OSError):
        _fail()
    return {"schema": SCHEMA, "verified": True, "capture_ready": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_owner_runtime", type=Path)
    args = parser.parse_args()
    try:
        verify_runtime(args.absolute_owner_runtime)
    except (RuntimeVerificationError, OSError, ValueError):
        print("VH_MAP02_OWNER_RUNTIME_VERIFY_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_OWNER_RUNTIME_VERIFY_PASS no_media_assertions=1 hashes=3 capture_ready=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
