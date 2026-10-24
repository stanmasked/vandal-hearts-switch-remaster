#!/usr/bin/env python3
"""Owner-private, no-game-media MAP02 runtime tar pack and safe restore.

Never uploads/downloads anything. The restore input MUST be a separately
downloaded copy of the private Drive archive with a retained local digest.
No original disc, BIOS, BK2, gameplay images or per-file digests are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile

from tools.map02_linux_octoshock.archive_owner_runtime import (
    ArchiveReadbackError, _inventory, _root, verify_archive_readback, MAX_ENTRIES,
)
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime

PREFIX = "runtime"
CHUNK = 1024 * 1024


class PrivateTarError(ValueError):
    pass


def _fail() -> None:
    raise PrivateTarError("owner-private archive integrity or privacy gate rejected")


def _outside(path_value: Path, root: Path, *, nonexistent: bool = False) -> Path:
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink():
        _fail()
    if path.parent.resolve(strict=True) != path.parent:
        _fail()
    for parent in (path.parent, *path.parent.parents):
        if (parent / ".git").exists() or (parent / ".git").is_symlink():
            _fail()
    if path == root or path.is_relative_to(root):
        _fail()
    if nonexistent and (path.exists() or path.is_symlink()):
        _fail()
    parent = path.parent.stat()
    if (not stat.S_ISDIR(parent.st_mode) or
            stat.S_IMODE(parent.st_mode) != 0o700 or
            parent.st_uid != os.geteuid()):
        _fail()
    return path


def _trusted_runtime(root: Path, pin: Path) -> None:
    result = verify_runtime(
        root, trusted_manifest_pin_file=pin, require_trusted_pin=True
    )
    if (result.get("verified") is not True or
            result.get("trusted_manifest_pin_verified") is not True
            or result.get("capture_ready") is not False):
        _fail()


def _hash_file(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid():
            _fail()
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            for chunk in iter(lambda: stream.read(CHUNK), b""):
                digest.update(chunk)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if identity(before) != identity(after) or identity(after) != identity(path.stat()):
            _fail()
        return digest.hexdigest()
    finally:
        os.close(fd)


def _pin(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size != 65):
            _fail()
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(66)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            _fail()
        try:
            value = data[:-1].decode("ascii")
        except UnicodeError:
            _fail()
        if (len(data) != 65 or data[-1:] != b"\n" or len(value) != 64
                or any(x not in "0123456789abcdef" for x in value)):
            _fail()
        return value
    finally:
        os.close(fd)


def _create_private(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags, 0o600)


def _info(name: str, mode: int, *, size: int = 0, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.mode = mode
    info.size = size
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = ""
    return info


def pack_runtime(source_value: Path, trusted_pin: Path,
                 tar_value: Path, tar_pin_value: Path) -> dict:
    """Write an exclusive 0600, uncompressed tar plus separate 0600 SHA256."""
    try:
        source = _root(source_value)
        tar = _outside(tar_value, source, nonexistent=True)
        tar_pin = _outside(tar_pin_value, source, nonexistent=True)
        if tar == tar_pin:
            _fail()
        _trusted_runtime(source, trusted_pin)
        expected, count, total = _inventory(source)
        try:
            fd = _create_private(tar)
            with os.fdopen(fd, "wb") as output:
                with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as stream:
                    stream.addfile(_info(PREFIX, 0o700, directory=True))
                    ordering = sorted(expected.items(), key=lambda row: (
                        row[0].count("/"), 0 if row[1][0] == "directory" else 1, row[0],
                    ))
                    for name, meta in ordering:
                        if meta[0] == "directory":
                            stream.addfile(_info(PREFIX + "/" + name, meta[1], directory=True))
                        else:
                            absolute = source / name
                            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                            input_fd = os.open(absolute, flags)
                            with os.fdopen(input_fd, "rb") as input_stream:
                                if os.fstat(input_stream.fileno()).st_size != meta[2]:
                                    _fail()
                                stream.addfile(
                                    _info(PREFIX + "/" + name, meta[1], size=meta[2]),
                                    input_stream,
                                )
            if _inventory(source)[0] != expected:
                _fail()
            _trusted_runtime(source, trusted_pin)
            tar_sha = _hash_file(tar)
            pin_fd = _create_private(tar_pin)
            with os.fdopen(pin_fd, "wb") as pin_output:
                pin_output.write((tar_sha + "\n").encode("ascii"))
        except Exception:
            if tar.exists():
                tar.unlink()
            if tar_pin.exists():
                tar_pin.unlink()
            raise
    except (OSError, ValueError, RuntimeError, tarfile.TarError):
        _fail()
    return {"files": count, "bytes": total, "drive_upload_authenticated": False}


def _checked_members(stream: tarfile.TarFile, expected: dict) -> list:
    members = stream.getmembers()
    if len(members) != len(expected) + 1 or len(members) > MAX_ENTRIES + 1:
        _fail()
    seen = set()
    for member in members:
        name = member.name
        if (not isinstance(name, str) or not name
                or "\\" in name or "//" in name):
            _fail()
        parts = PurePosixPath(name).parts
        if (name != "/".join(parts) or not parts or parts[0] != PREFIX
                or any(part in (".", "..") for part in parts)):
            _fail()
        if name in seen:
            _fail()
        seen.add(name)
        if name == PREFIX:
            if not member.isdir() or member.mode != 0o700 or member.size != 0:
                _fail()
            continue
        relative = "/".join(parts[1:])
        if relative not in expected:
            _fail()
        meta = expected[relative]
        if member.mode != meta[1]:
            _fail()
        if meta[0] == "directory":
            if not member.isdir() or member.size != 0:
                _fail()
        else:
            if not member.isfile() or member.size != meta[2]:
                _fail()
    if PREFIX not in seen:
        _fail()
    return members


def restore_runtime(source_value: Path, trusted_pin: Path, tar_value: Path,
                    tar_pin_value: Path, destination_value: Path) -> dict:
    """Verify downloaded tar and every entry BEFORE safe non-privileged extraction."""
    try:
        source = _root(source_value)
        destination = _outside(destination_value, source, nonexistent=True)
        tar = _outside(tar_value, source)
        pin = _outside(tar_pin_value, source)
        if len({str(destination), str(tar), str(pin)}) != 3:
            _fail()
        if not tar.is_file() or tar.is_symlink() or not pin.is_file():
            _fail()
        _trusted_runtime(source, trusted_pin)
        expected, count, total = _inventory(source)
        if _hash_file(tar) != _pin(pin):
            _fail()
        with tarfile.open(tar, mode="r:") as stream:
            members = _checked_members(stream, expected)
            # Compare full payload SHA256 before creating even the target root.
            for member in members:
                if member.isfile():
                    relative = member.name[len(PREFIX) + 1:]
                    fileobj = stream.extractfile(member)
                    if fileobj is None:
                        _fail()
                    digest = hashlib.sha256()
                    with fileobj:
                        for chunk in iter(lambda: fileobj.read(CHUNK), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != expected[relative][3]:
                        _fail()
            if _hash_file(tar) != _pin(pin):
                _fail()
            created = False
            try:
                destination.mkdir(mode=0o700)
                created = True
                # Never call tarfile.extractall or allow archive-supplied links.
                for member in members:
                    if member.name == PREFIX:
                        continue
                    relative = member.name[len(PREFIX) + 1:]
                    path = destination / relative
                    if member.isdir():
                        path.mkdir(mode=0o700)
                        path.chmod(member.mode)
                    else:
                        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        fd = _create_private(path)
                        with os.fdopen(fd, "wb") as output:
                            with stream.extractfile(member) as payload:
                                if payload is None:
                                    _fail()
                                shutil.copyfileobj(payload, output, length=CHUNK)
                        path.chmod(member.mode)
                if _hash_file(tar) != _pin(pin):
                    _fail()
                verified = verify_archive_readback(source, destination, trusted_pin)
            except Exception:
                if created:
                    shutil.rmtree(destination)
                raise
    except (OSError, ValueError, RuntimeError, tarfile.TarError):
        _fail()
    return {
        "files": verified["files"], "bytes": verified["total_bytes"],
        "trusted_manifest_pin_verified_twice": True,
        "drive_upload_authenticated": False, "capture_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("source", type=Path)
    pack.add_argument("archive_tar", type=Path)
    pack.add_argument("archive_sha256_file", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("source", type=Path)
    restore.add_argument("downloaded_archive_tar", type=Path)
    restore.add_argument("retained_archive_sha256_file", type=Path)
    restore.add_argument("new_restored_runtime", type=Path)
    for subcommand in (pack, restore):
        subcommand.add_argument("--trusted-manifest-pin-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "pack":
            result = pack_runtime(
                args.source, args.trusted_manifest_pin_file,
                args.archive_tar, args.archive_sha256_file
            )
        else:
            result = restore_runtime(
                args.source, args.trusted_manifest_pin_file,
                args.downloaded_archive_tar, args.retained_archive_sha256_file,
                args.new_restored_runtime
            )
    except (PrivateTarError, ArchiveReadbackError, OSError, ValueError):
        print("VH_MAP02_OWNER_PRIVATE_TAR_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_OWNER_PRIVATE_TAR_PASS files=%d bytes=%d "
          "trusted_restore=%d drive_upload_authenticated=0 capture_ready=0" %
          (result["files"], result["bytes"], args.cmd == "restore"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
