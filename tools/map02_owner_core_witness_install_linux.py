#!/usr/bin/env python3
"""Install a verified, game-free MAP02 External Tool into a private BizHawk Linux tree.

This is a one-way install: it refuses to replace an existing External Tool.
It verifies the source DLL against an independently supplied SHA-256 before
writing, keeps the installed file owner-only, and never touches game assets.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat

SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}\Z")
NATIVE_NAMES = {"liboctoshock.dll.so", "liboctoshock.so", "octoshock.dll"}


def _reject_git(path: Path) -> None:
    for current in (path, *path.parents):
        marker = current / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("BizHawk root and plugin source must be outside Git")


def _regular_absolute(path: Path, label: str) -> Path:
    source = Path(path)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise ValueError(label + " must be an absolute regular nonsymlink file")
    resolved = source.resolve(strict=True)
    if not stat.S_ISREG(resolved.stat().st_mode):
        raise ValueError(label + " must be regular")
    _reject_git(resolved)
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("plugin source changed from a regular file")
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(handle.fileno())
    current = path.stat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)):
        raise ValueError("plugin source changed while hashing")
    return digest.hexdigest()


def install(bizhawk_root: Path, source_dll: Path, expected_sha256: str) -> dict:
    root = Path(bizhawk_root)
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir()):
        raise ValueError("BizHawk root must be an absolute ordinary directory")
    root = root.resolve(strict=True)
    _reject_git(root)
    if not (root / "EmuHawk.exe").is_file() or not (root / "EmuHawkMono.sh").is_file():
        raise ValueError("BizHawk root does not match the official Linux release layout")
    if not (root / "dll" / "BizHawk.Emulation.Cores.dll").is_file():
        raise ValueError("official BizHawk core assembly is missing")
    native = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
              and p.name in NATIVE_NAMES]
    if not native:
        raise ValueError("official Octoshock native module is missing")
    if not isinstance(expected_sha256, str) or not SHA256_HEX.fullmatch(expected_sha256):
        raise ValueError("expected plugin SHA256 is malformed")
    source = _regular_absolute(source_dll, "plugin artifact")
    if source.name != "VhMap02CoreWitness.dll":
        raise ValueError("plugin artifact filename is not the expected External Tool")
    if _sha256(source) != expected_sha256.lower():
        raise ValueError("plugin artifact differs from the independently pinned SHA256")

    external = root / "ExternalTools"
    if external.is_symlink():
        raise ValueError("ExternalTools folder must not be a symlink")
    if external.exists() and not external.is_dir():
        raise ValueError("ExternalTools path is not a directory")
    if not external.exists():
        external.mkdir(mode=0o755)
    target = external / "VhMap02CoreWitness.dll"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(target, flags, 0o600)
    try:
        with source.open("rb") as input_file:
            while True:
                block = input_file.read(1024 * 1024)
                if not block:
                    break
                view = memoryview(block)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise OSError("short write while installing plugin")
                    view = view[written:]
        os.fsync(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("installed plugin is not a regular file")
    except BaseException:
        try:
            os.unlink(target)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    if _sha256(target) != expected_sha256.lower():
        try:
            target.unlink()
        except OSError:
            pass
        raise ValueError("installed plugin failed its post-write SHA256 check")
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        raise ValueError("installed plugin permissions are not owner-only")
    return {
        "schema": "vh.map02.linux-external-tool-install.v1",
        "verified_source_sha256": True,
        "installed_owner_only": True,
        "refused_existing_destination": True,
        "game_assets_read_or_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_bizhawk_linux_root", type=Path)
    parser.add_argument("absolute_plugin_artifact", type=Path)
    parser.add_argument("--expected-plugin-sha256", required=True)
    args = parser.parse_args()
    try:
        install(args.absolute_bizhawk_linux_root, args.absolute_plugin_artifact,
                args.expected_plugin_sha256)
    except (OSError, ValueError, RuntimeError, TypeError):
        parser.error("private Linux External Tool installation rejected")
    print("VH_MAP02_LINUX_PLUGIN_INSTALL_OK installed=1 owner_only=1 game_assets=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
