#!/usr/bin/env python3
"""Re-audit a persistent private Drive MAP02 runtime WITHOUT the original source tree.

Uses three independently retained local owner SHA256 pins: the owner runtime
manifest, the tar archive and the initial verified transfer receipt. Every
remote byte is downloaded anew; cloud receipts alone are never trust anchors.
Neither a successful re-audit nor a no-media runtime proves MAP02 gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
from typing import Callable

from tools.map02_linux_octoshock.archive_owner_runtime import _inventory
from tools.map02_linux_octoshock.private_runtime_drive import (
    PrivateDriveError, _call_rclone, _check_remote, _folder_map,
    _remote_name, _stat_remote, SESSION_PATTERN, forbidden_original_media_path,
)
from tools.map02_linux_octoshock.private_runtime_tar import (
    _hash_file, _pin, _outside, _create_private, PREFIX,
)
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime

HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9_-]{8,256}\Z")
MAX_ITEMS = 50000
MAX_BYTES = 2 * 1024**3
MAX_SINGLE = 1024**3


class IndependentAuditError(ValueError):
    pass


def _fail() -> None:
    raise IndependentAuditError("independent private Drive archive audit rejected")


def _private_input(path: Path) -> Path:
    candidate = Path(path)
    if (not candidate.is_absolute() or candidate.is_symlink() or
            not candidate.is_file()):
        _fail()
    # A mode-0600 file alone is insufficient: never read owner trust pins
    # through an alias/symlink parent or from a public Git worktree.
    # Enforce that the immediate containing directory is owner-private.
    if candidate.parent.resolve(strict=True) != candidate.parent:
        _fail()
    for ancestor in (candidate.parent, *candidate.parent.parents):
        git = ancestor / ".git"
        if git.exists() or git.is_symlink():
            _fail()
    folder = candidate.parent.stat()
    info = candidate.stat()
    if (not stat.S_ISDIR(folder.st_mode)
            or folder.st_uid != os.geteuid()
            or stat.S_IMODE(folder.st_mode) != 0o700
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600):
        _fail()
    return candidate


def _receipt(payload: bytes, session: str,
             builds_id: str, manifests_id: str) -> tuple[dict, list[dict]]:
    if len(payload) > 32768:
        _fail()
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeError):
        _fail()
    if (not isinstance(obj, dict)
            or obj.get("schema") != "vh.map02.owner-runtime-private-drive-readback.v1"
            or obj.get("session") != session
            or obj.get("source_verified_against_owner_pin") is not True
            or obj.get("full_restored_tree_compared") is not True
            or obj.get("original_game_media_used") is not False
            or obj.get("capture_ready") is not False
            or obj.get("remote_type") != "drive"
            or not isinstance(obj.get("objects"), list)
            or len(obj["objects"]) != 4):
        _fail()
    count = obj.get("runtime_file_count")
    total = obj.get("runtime_total_bytes")
    if (type(count) is not int or not 1 <= count <= MAX_ITEMS or
            type(total) is not int or not 0 < total <= MAX_BYTES):
        _fail()
    expected = {
        "map02-runtime-" + session + ".tar": builds_id,
        "map02-runtime-" + session + ".tar.sha256": manifests_id,
        "map02-runtime-" + session + ".manifest.json": manifests_id,
        "map02-runtime-" + session + ".manifest.sha256": manifests_id,
    }
    seen = set()
    for item in obj["objects"]:
        if not isinstance(item, dict):
            _fail()
        name = item.get("name")
        if (not isinstance(name, str) or name in seen or
                name not in expected or item.get("folder_id") != expected[name]
                or item.get("readback_verified") is not True):
            _fail()
        seen.add(name)
        digest = item.get("sha256")
        number = item.get("bytes")
        object_id = item.get("google_drive_id")
        if (not isinstance(digest, str) or HASH.fullmatch(digest) is None
                or type(number) is not int or not 0 < number <= MAX_BYTES
                or not isinstance(object_id, str) or
                ID.fullmatch(object_id) is None):
            _fail()
    if seen != set(expected):
        _fail()
    return obj, obj["objects"]


def _safe_restore(archive_path: Path, target: Path) -> None:
    """Avoid extractall: reject links, traversal, oversized payloads."""
    created = False
    try:
        with tarfile.open(archive_path, "r:") as tf:
            members = tf.getmembers()
            if not 2 <= len(members) <= MAX_ITEMS + 1:
                _fail()
            paths = set()
            folders: list[tuple[Path, int]] = []
            bytes_in_tar = 0
            for member in members:
                name = member.name
                if (not isinstance(name, str) or not name
                        or "\\" in name or "//" in name
                        or name.startswith("/")):
                    _fail()
                parts = name.split("/")
                if (parts[0] != PREFIX or
                        any(part in (".", "..", "") for part in parts)
                        or name in paths):
                    _fail()
                paths.add(name)
                # Re-enforce no-game-media constraints even when the receipt,
                # manifest and tar hashes were all pinned elsewhere.
                if name != PREFIX and forbidden_original_media_path(name):
                    _fail()
                if name == PREFIX:
                    if not member.isdir() or member.mode != 0o700:
                        _fail()
                    continue
                if not (member.isdir() or member.isfile()):
                    _fail()
                if member.mode < 0o400 or member.mode > 0o777:
                    _fail()
                if member.isfile():
                    if member.size < 0 or member.size > MAX_SINGLE:
                        _fail()
                    bytes_in_tar += member.size
                    if bytes_in_tar > MAX_BYTES:
                        _fail()
                elif member.size != 0:
                    _fail()
            if PREFIX not in paths:
                _fail()
            target.mkdir(mode=0o700)
            created = True
            for member in members:
                if member.name == PREFIX:
                    continue
                path = target.joinpath(*member.name.split("/")[1:])
                if member.isdir():
                    # Delay final modes until after all children are written.
                    path.mkdir(mode=0o700)
                    folders.append((path, member.mode))
                else:
                    if not path.parent.is_dir() or path.exists() or path.is_symlink():
                        _fail()
                    fd = _create_private(path)
                    with os.fdopen(fd, "wb") as output:
                        with tf.extractfile(member) as input_stream:
                            if input_stream is None:
                                _fail()
                            remaining = member.size
                            while remaining:
                                chunk = input_stream.read(min(1024 * 1024, remaining))
                                if not chunk:
                                    _fail()
                                output.write(chunk)
                                remaining -= len(chunk)
                    path.chmod(member.mode)
            for path, mode in sorted(folders, key=lambda item: len(item[0].parts),
                                     reverse=True):
                path.chmod(mode)
    except Exception:
        if created:
            shutil.rmtree(target)
        raise


def audit_independent_readback(
    private_folder_map: Path, owner_manifest_sha: Path,
    trusted_archive_sha: Path, trusted_receipt_sha: Path,
    fresh_readback_root: Path, builds_remote: str, manifests_remote: str,
    session: str, *,
    invoke: Callable[[list[str]], str] = _call_rclone,
) -> dict[str, object]:
    """Download all five Drive objects independently; no original runtime required."""
    try:
        if not isinstance(session, str) or SESSION_PATTERN.fullmatch(session) is None:
            _fail()
        builds = _remote_name(builds_remote)
        manifests = _remote_name(manifests_remote)
        if builds == manifests:
            _fail()
        root = Path(fresh_readback_root)
        if not root.is_absolute() or root.is_symlink() or root.exists():
            _fail()
        # _outside checks parent is 0700 owner-private and outside Git.
        owner_pin = _private_input(owner_manifest_sha)
        root = _outside(root, owner_pin, nonexistent=True)
        tar_pin = _private_input(trusted_archive_sha)
        receipt_pin = _private_input(trusted_receipt_sha)
        folder_map = _private_input(private_folder_map)
        if len({str(owner_pin), str(tar_pin), str(receipt_pin),
                str(folder_map), str(root)}) != 5:
            _fail()
        builds_id, manifests_id = _folder_map(folder_map, root)
        owner_pin_value = _pin(owner_pin)
        tar_pin_value = _pin(tar_pin)
        receipt_pin_value = _pin(receipt_pin)
        _check_remote(builds, builds_id, invoke)
        _check_remote(manifests, manifests_id, invoke)
        stem = "map02-runtime-" + session
        receipt_name = stem + ".receipt.json"
        receipt_path = manifests + ":" + receipt_name
        _check_remote(manifests, manifests_id, invoke)
        receipt_size = _read_remote_size(receipt_path, invoke)
        _check_remote(manifests, manifests_id, invoke)
        receipt_stat = _stat_remote(
            receipt_path, receipt_name, receipt_size, invoke,
        )
        if not receipt_stat:
            _fail()
        _check_remote(manifests, manifests_id, invoke)
        root.mkdir(mode=0o700)
        downloaded = root / "downloaded"
        downloaded.mkdir(mode=0o700)
        receipt_file = downloaded / receipt_name
        invoke(["copyto", "--immutable", receipt_path, str(receipt_file)])
        _check_remote(manifests, manifests_id, invoke)
        if _stat_remote(
            receipt_path, receipt_name, receipt_size, invoke,
        ) != receipt_stat:
            _fail()
        _check_remote(manifests, manifests_id, invoke)
        receipt_file.chmod(0o600)
        if _hash_file(receipt_file) != receipt_pin_value:
            _fail()
        receipt, objects = _receipt(
            receipt_file.read_bytes(), session, builds_id, manifests_id
        )
        for item in objects:
            name = item["name"]
            remote = builds if item["folder_id"] == builds_id else manifests
            expected_folder_id = builds_id if remote == builds else manifests_id
            path = remote + ":" + name
            _check_remote(remote, expected_folder_id, invoke)
            if _stat_remote(path, name, item["bytes"], invoke) != item["google_drive_id"]:
                _fail()
            _check_remote(remote, expected_folder_id, invoke)
            output = downloaded / name
            invoke(["copyto", "--immutable", path, str(output)])
            _check_remote(remote, expected_folder_id, invoke)
            if _stat_remote(path, name, item["bytes"], invoke) != item["google_drive_id"]:
                _fail()
            _check_remote(remote, expected_folder_id, invoke)
            output.chmod(0o600)
            if (_hash_file(output) != item["sha256"] or
                    output.stat().st_size != item["bytes"]):
                _fail()
        archive = downloaded / (stem + ".tar")
        manifest = downloaded / (stem + ".manifest.json")
        manifest_pin = downloaded / (stem + ".manifest.sha256")
        tar_remote_pin = downloaded / (stem + ".tar.sha256")
        if (_hash_file(archive) != tar_pin_value
                or _hash_file(manifest) != owner_pin_value
                or _pin(manifest_pin) != owner_pin_value
                or _pin(tar_remote_pin) != tar_pin_value):
            _fail()
        # Recheck independent anchors and remote scope before extracting any
        # archive bytes. Use the pin values captured before remote inspection;
        # never let a pin file changed during readback redefine what is trusted.
        _check_remote(builds, builds_id, invoke)
        _check_remote(manifests, manifests_id, invoke)
        if (_folder_map(folder_map, root) != (builds_id, manifests_id)
                or _pin(owner_pin) != owner_pin_value
                or _pin(tar_pin) != tar_pin_value
                or _pin(receipt_pin) != receipt_pin_value):
            _fail()
        # The trust anchor is local, outside Drive; the cloud receipt must
        # not be treated as independent truth.
        restored = root / "restored"
        restored.mkdir(mode=0o700)
        runtime = restored / "runtime"
        _safe_restore(archive, runtime)
        result = verify_runtime(runtime, trusted_manifest_pin_file=owner_pin,
                                require_trusted_pin=True)
        if (result.get("verified") is not True or
                result.get("capture_ready") is not False or
                _hash_file(runtime / "map02-owner-runtime-manifest.json")
                != _pin(owner_pin)):
            _fail()
        records, count, total = _inventory(runtime)
        if (count != receipt["runtime_file_count"]
                or total != receipt["runtime_total_bytes"]):
            _fail()
        # Reconfirm scope and all independent local anchors after the full
        # source-free restore. A changed Drive root or trust pin cannot earn
        # a successful independent-readback report.
        _check_remote(builds, builds_id, invoke)
        _check_remote(manifests, manifests_id, invoke)
        if (_folder_map(folder_map, root) != (builds_id, manifests_id)
                or _pin(owner_pin) != owner_pin_value
                or _pin(tar_pin) != tar_pin_value
                or _pin(receipt_pin) != receipt_pin_value):
            _fail()
        # Re-audit receipt immutability after extraction.
        if _hash_file(receipt_file) != receipt_pin_value:
            _fail()
        return {
            "files": count, "bytes": total, "objects_read_back": 5,
            "independent_receipt_pin_verified": True,
            "original_runtime_required": False,
            "capture_ready": False,
        }
    except (OSError, ValueError, RuntimeError, TypeError, tarfile.TarError):
        _fail()


def _read_remote_size(path: str, invoke: Callable[[list[str]], str]) -> int:
    try:
        obj = json.loads(invoke(["lsjson", "--stat", path]))
    except (ValueError, TypeError):
        _fail()
    if (not isinstance(obj, dict) or obj.get("IsDir") is not False
            or type(obj.get("Size")) is not int
            or not 1 <= obj["Size"] <= 32768):
        _fail()
    return obj["Size"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-folder-map", required=True, type=Path)
    parser.add_argument("--owner-manifest-pin", required=True, type=Path)
    parser.add_argument("--trusted-archive-pin", required=True, type=Path)
    parser.add_argument("--trusted-receipt-pin", required=True, type=Path)
    parser.add_argument("--new-readback-root", required=True, type=Path)
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        report = audit_independent_readback(
            args.private_folder_map, args.owner_manifest_pin,
            args.trusted_archive_pin, args.trusted_receipt_pin,
            args.new_readback_root, args.builds_remote,
            args.manifests_remote, args.session,
        )
    except IndependentAuditError:
        print("VH_MAP02_STAGE539_INDEPENDENT_READBACK_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_STAGE539_INDEPENDENT_READBACK_PASS "
          "files=%d bytes=%d cloud_objects=5 original_runtime_required=0 "
          "capture_ready=0" % (report["files"], report["bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
