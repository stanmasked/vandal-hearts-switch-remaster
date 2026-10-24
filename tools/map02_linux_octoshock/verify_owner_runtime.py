#!/usr/bin/env python3
"""Offline owner-local integrity check for the staged MAP02 Linux runtime.

Reads only the caller's local no-media runtime directory. It never consumes
disc, BIOS, BK2, screenshots or captures, and never emits private paths/hashes.
A verified build is NOT proof of PSX power-on or MAP02 gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path

SCHEMA = "vh.map02.owner-local-runtime.v2"
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


def _read_external_manifest_pin(pin_value: Path, runtime_root: Path) -> str:
    """Read a pre-established owner-private trust anchor outside the runtime.

    This function does NOT create or authenticate the trusted value. The owner
    must store and independently verify the pin in the private evidence archive
    before replay. Never disclose the hash or its path in public output.
    """
    path = Path(pin_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        _fail()
    if path.is_relative_to(runtime_root):
        _fail()
    parent = path.parent
    # The trust anchor must live in an owner-only directory. Resolving before
    # opening rejects symlinked ancestors; opening the directory itself and
    # using dir_fd keeps the final file lookup anchored to that same inode.
    if parent.resolve(strict=True) != parent:
        _fail()
    parent_before = parent.lstat()
    if (not stat.S_ISDIR(parent_before.st_mode)
            or parent_before.st_uid != os.geteuid()
            or stat.S_IMODE(parent_before.st_mode) != 0o700):
        _fail()
    parent_flags = (os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0))
    parent_fd = os.open(parent, parent_flags)
    try:
        opened_parent = os.fstat(parent_fd)

        def parent_identity(info: os.stat_result) -> tuple[int, ...]:
            return (
                info.st_dev, info.st_ino, info.st_uid,
                stat.S_IMODE(info.st_mode), info.st_nlink,
                info.st_mtime_ns, info.st_ctime_ns,
            )

        if (not stat.S_ISDIR(opened_parent.st_mode)
                or parent_identity(opened_parent) != parent_identity(parent_before)):
            _fail()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_size != 65
                    or stat.S_IMODE(before.st_mode) != 0o600
                    or before.st_uid != os.geteuid()
                    or before.st_nlink != 1):
                _fail()
            with os.fdopen(fd, "rb", closefd=False) as stream:
                content = stream.read(66)
            after = os.fstat(fd)
            # Do not follow the final path if it was replaced by a symlink
            # while the open descriptor still refers to the trusted inode.
            now = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)

            def file_identity(info: os.stat_result) -> tuple[int, ...]:
                return (
                    info.st_dev, info.st_ino, info.st_uid,
                    stat.S_IMODE(info.st_mode), info.st_nlink,
                    info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                )

            if (file_identity(before) != file_identity(after)
                    or file_identity(after) != file_identity(now)):
                _fail()
            parent_after = os.fstat(parent_fd)
            parent_path_after = parent.lstat()
            if (parent_identity(parent_after) != parent_identity(opened_parent)
                    or parent_identity(parent_path_after) != parent_identity(opened_parent)):
                _fail()
            if len(content) != 65 or not content.endswith(b"\n"):
                _fail()
            digest = content[:-1].decode("ascii")
            if HASH.fullmatch(digest) is None:
                _fail()
            return digest
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)

def verify_runtime(root_value: Path, *,
                   trusted_manifest_pin_file: Path | None = None,
                   require_trusted_pin: bool = False) -> dict[str, object]:
    raw = Path(root_value)
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        _fail()
    root = raw.resolve(strict=True)
    if stat.S_IMODE(root.stat().st_mode) != 0o700:
        _fail()
    if type(require_trusted_pin) is not bool:
        _fail()
    if require_trusted_pin and trusted_manifest_pin_file is None:
        _fail()
    try:
        manifest_bytes = _bytes(
            root, "map02-owner-runtime-manifest.json", maximum=65536, mode=0o600
        )
        if trusted_manifest_pin_file is not None:
            trusted = _read_external_manifest_pin(trusted_manifest_pin_file, root)
            observed = hashlib.sha256(manifest_bytes).hexdigest()
            if not hmac.compare_digest(observed, trusted):
                _fail()
        manifest = json.loads(manifest_bytes)
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
        _sha(root, "EmuHawk.exe", official["emuhawk_exe_sha256"])
        _sha(root, "EmuHawkMono.sh", official["emuhawk_mono_launcher_sha256"])
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
    return {
        "schema": SCHEMA, "verified": True, "capture_ready": False,
        "trusted_manifest_pin_verified": trusted_manifest_pin_file is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_owner_runtime", type=Path)
    parser.add_argument("--trusted-manifest-pin-file", type=Path,
                        help="Existing owner-private mode-0600 SHA-256 line, outside runtime")
    parser.add_argument("--require-trusted-pin", action="store_true",
                        help="Fail closed without independently supplied manifest digest")
    args = parser.parse_args()
    try:
        verify_runtime(
            args.absolute_owner_runtime,
            trusted_manifest_pin_file=args.trusted_manifest_pin_file,
            require_trusted_pin=args.require_trusted_pin,
        )
    except (RuntimeVerificationError, OSError, ValueError):
        print("VH_MAP02_OWNER_RUNTIME_VERIFY_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_OWNER_RUNTIME_VERIFY_PASS no_media_assertions=1 hashes=5 "
          "trusted_manifest_pin_verified=%d capture_ready=0" %
          (args.trusted_manifest_pin_file is not None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
