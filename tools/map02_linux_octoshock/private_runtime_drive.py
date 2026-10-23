#!/usr/bin/env python3
"""Owner-local MAP02 runtime upload + independent Google Drive byte readback.

Requires two already authenticated, folder-scoped rclone Google Drive remotes.
Never configures OAuth, prints credentials/paths/checksums, or uploads game media.
This is NOT executed by public CI against any real Drive account.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Callable

from tools.map02_linux_octoshock.archive_owner_runtime import _root, _inventory
from tools.map02_linux_octoshock.private_runtime_tar import (
    _hash_file, _outside, _pin, restore_runtime,
)
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime

FOLDER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{15,128}\Z")
REMOTE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,40}\Z")
SESSION_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{7,62}\Z")
MAX_STDOUT = 262144


class PrivateDriveError(ValueError):
    """Generic fail-closed error; never prints private paths or tokens."""


def _fail() -> None:
    raise PrivateDriveError("private Google Drive archive upload/readback rejected")


def _call_rclone(arguments: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["rclone", *arguments], capture_output=True, text=True,
            timeout=1800, check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        _fail()
    if proc.returncode or len(proc.stdout) > MAX_STDOUT:
        _fail()
    return proc.stdout


def _remote_name(remote: str) -> str:
    if not isinstance(remote, str) or REMOTE_PATTERN.fullmatch(remote) is None:
        _fail()
    return remote


def _check_remote(remote: str, folder_id: str,
                  invoke: Callable[[list[str]], str]) -> None:
    # Capture output; never emit even "redacted" config to stdout or a report.
    details = invoke(["config", "redacted", remote])
    if len(details) > 16384:
        _fail()
    config = {}
    for line in details.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            config[key.strip().lower()] = value.strip()
    if config.get("type") != "drive" or config.get("root_folder_id") != folder_id:
        _fail()
    if f"[{remote}]" not in details:
        _fail()
    # Environment overrides can silently redirect uploads to a different root.
    for name in os.environ:
        if (name.startswith("RCLONE_CONFIG_") or
                name.startswith("RCLONE_DRIVE_ROOT_FOLDER_ID")):
            _fail()
    invoke(["lsf", "--files-only", remote + ":"])


def _existing_names(remote: str, invoke: Callable[[list[str]], str]) -> set[str]:
    names = invoke(["lsf", "--files-only", remote + ":"]).splitlines()
    if any("/" in n or "\\" in n for n in names):
        _fail()
    return set(names)


def _stat_remote(remote_path: str, filename: str, size: int,
                 invoke: Callable[[list[str]], str]) -> str:
    raw = invoke(["lsjson", "--stat", remote_path])
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        _fail()
    if (not isinstance(data, dict) or data.get("IsDir") is not False
            or data.get("Name") != filename or data.get("Size") != size):
        _fail()
    object_id = data.get("ID")
    if (not isinstance(object_id, str) or not 8 <= len(object_id) <= 256
            or not re.fullmatch(r"[A-Za-z0-9_-]+", object_id)):
        _fail()
    return object_id


def _require_file(path_value: Path, source: Path, *, mode: int | None = None) -> Path:
    path = _outside(path_value, source)
    if not path.is_file() or path.is_symlink():
        _fail()
    info = path.stat()
    if info.st_uid != os.geteuid() or (
            mode is not None and stat.S_IMODE(info.st_mode) != mode):
        _fail()
    return path


def _folder_map(path: Path, root: Path) -> tuple[str, str]:
    """Read true private folder IDs from an outside-Git owner-only file."""
    owner_file = _require_file(path, root, mode=0o600)
    if owner_file.stat().st_size > 2048:
        _fail()
    try:
        data = json.loads(owner_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        _fail()
    if not isinstance(data, dict) or set(data) != {
            "builds_folder_id", "manifests_folder_id"}:
        _fail()
    builds_id = data["builds_folder_id"]
    manifests_id = data["manifests_folder_id"]
    if (not isinstance(builds_id, str)
            or not isinstance(manifests_id, str)
            or FOLDER_ID_PATTERN.fullmatch(builds_id) is None
            or FOLDER_ID_PATTERN.fullmatch(manifests_id) is None
            or builds_id == manifests_id):
        _fail()
    return builds_id, manifests_id


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _seal_payload(source: Path, target: Path) -> str:
    """Create an owner-only, distinct, full-byte snapshot before any upload."""
    if target.exists() or target.is_symlink() or source.is_symlink():
        _fail()
    baseline = _hash_file(source)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, flags)
    dest_fd = None
    try:
        original = os.fstat(source_fd)
        if not stat.S_ISREG(original.st_mode) or original.st_uid != os.geteuid():
            _fail()
        dest_fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
            getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        with os.fdopen(source_fd, "rb", closefd=False) as incoming:
            with os.fdopen(dest_fd, "wb", closefd=False) as outgoing:
                while True:
                    chunk = incoming.read(1024 * 1024)
                    if not chunk:
                        break
                    outgoing.write(chunk)
        after = os.fstat(source_fd)
        if ((original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            _fail()
    finally:
        if dest_fd is not None:
            os.close(dest_fd)
        os.close(source_fd)
    if _hash_file(target) != baseline or _hash_file(source) != baseline:
        _fail()
    return baseline


def archive_to_private_drive(
    runtime: Path, owner_manifest_pin: Path, tar: Path, tar_pin: Path,
    private_readback_folder: Path, builds_remote: str, manifests_remote: str,
    session: str, private_folder_map: Path, *,
    invoke: Callable[[list[str]], str] = _call_rclone,
) -> dict[str, object]:
    """Archive previously pinned runtime; confirm exact remote-byte readback.

    Produces a local verified receipt and uploads/re-downloads that receipt to
    the folder-scoped manifest remote. A test double for invoke is synthetic
    only; actual external execution requires an authenticated rclone.
    """
    try:
        source = _root(runtime)
        builds = _remote_name(builds_remote)
        manifests = _remote_name(manifests_remote)
        if builds == manifests or SESSION_PATTERN.fullmatch(session) is None:
            _fail()
        staging = _outside(private_readback_folder, source, nonexistent=True)
        builds_id, manifests_id = _folder_map(private_folder_map, source)
        manifest_file = source / "map02-owner-runtime-manifest.json"
        pin = _require_file(owner_manifest_pin, source, mode=0o600)
        archive = _require_file(tar, source, mode=0o600)
        archive_pin = _require_file(tar_pin, source, mode=0o600)
        if len({str(staging), str(archive), str(archive_pin), str(pin)}) != 4:
            _fail()
        result = verify_runtime(source, trusted_manifest_pin_file=pin,
                                require_trusted_pin=True)
        if result.get("verified") is not True or result.get("capture_ready") is not False:
            _fail()
        files, count, total = _inventory(source)
        if not files or count == 0 or _hash_file(archive) != _pin(archive_pin):
            _fail()
        if _sha_bytes(manifest_file.read_bytes()) != _pin(pin):
            _fail()
        for name in files:
            lower = name.lower()
            if (lower.endswith((".cue", ".iso", ".chd", ".bk2", ".sav",
                                ".bin", ".rom", ".img", ".pbp", ".srm",
                                ".m3u", ".ccd", ".sub", ".mdf"))
                    or lower in {"vandalhearts.bin", "vandalhearts.bk2"}):
                _fail()

        # Reject malicious or contaminated tar BEFORE uploading even one byte.
        # A matching locally regenerated tar hash is not sufficient.
        staging.mkdir(mode=0o700)
        preflight_parent = staging / "preflight"
        preflight_parent.mkdir(mode=0o700)
        preflight_result = restore_runtime(
            source, pin, archive, archive_pin, preflight_parent / "runtime",
        )
        if (preflight_result["files"] != count or
                preflight_result["bytes"] != total):
            _fail()
        stem = "map02-runtime-" + session
        originals = [
            (builds, stem + ".tar", archive),
            (manifests, stem + ".tar.sha256", archive_pin),
            (manifests, stem + ".manifest.json", manifest_file),
            (manifests, stem + ".manifest.sha256", pin),
        ]
        # Seal all upload sources in a separate owner-only directory. Never
        # hand mutable build-output files directly to a remote transport.
        sealed_dir = staging / "sealed-for-upload"
        sealed_dir.mkdir(mode=0o700)
        payloads = []
        for remote, name, original in originals:
            sealed = sealed_dir / name
            expected_sha = _seal_payload(original, sealed)
            payloads.append((remote, name, original, sealed, expected_sha))
        if (_hash_file(sealed_dir / (stem + ".tar")) != _pin(archive_pin)
                or _hash_file(sealed_dir / (stem + ".manifest.json")) != _pin(pin)):
            _fail()
        # Validate the actual sealed tar snapshot as well, before *any*
        # cloud operation. The earlier source tar preflight is insufficient
        # if mutable originals change in between checks.
        sealed_preflight = staging / "sealed-preflight"
        sealed_preflight.mkdir(mode=0o700)
        check = restore_runtime(
            source, pin, sealed_dir / (stem + ".tar"),
            archive_pin, sealed_preflight / "runtime",
        )
        if check["files"] != count or check["bytes"] != total:
            _fail()
        _check_remote(builds, builds_id, invoke)
        _check_remote(manifests, manifests_id, invoke)
        existing_builds = _existing_names(builds, invoke)
        existing_manifests = _existing_names(manifests, invoke)
        if any(name in (existing_builds if remote == builds else existing_manifests)
               for remote, name, _, _, _ in payloads):
            _fail()
        staged_files = staging / "downloaded"
        staged_files.mkdir(mode=0o700)
        restored = staging / "restored"
        restored.mkdir(mode=0o700)
        metadata: list[dict[str, object]] = []
        for remote, name, original, sealed, expected_sha in payloads:
            if (_hash_file(sealed) != expected_sha
                    or _hash_file(original) != expected_sha):
                _fail()
            target = remote + ":" + name
            invoke(["copyto", "--immutable", "--no-traverse", str(sealed), target])
            object_id = _stat_remote(target, name, sealed.stat().st_size, invoke)
            # Download actual remote bytes and compare against the sealed
            # snapshot, not mutable original build output.
            download = staged_files / name
            invoke(["copyto", "--immutable", target, str(download)])
            downloaded = _require_file(download, source)
            if (_hash_file(downloaded) != expected_sha
                    or downloaded.stat().st_size != sealed.stat().st_size):
                _fail()
            if original == pin or original == archive_pin:
                os.chmod(downloaded, 0o600)
            metadata.append({
                "folder_id": (builds_id if remote == builds
                              else manifests_id),
                "name": name,
                "google_drive_id": object_id,
                "sha256": expected_sha,
                "bytes": downloaded.stat().st_size,
                "readback_verified": True,
            })
        # No success receipt if any owner-source or staged file changed
        # after preflight. The upload itself always used sealed bytes.
        if any(_hash_file(original) != expected_sha
               or _hash_file(sealed) != expected_sha
               for _, _, original, sealed, expected_sha in payloads):
            _fail()
        restored_result = restore_runtime(
            source, pin, staged_files / (stem + ".tar"),
            archive_pin, restored / "runtime",
        )
        if restored_result["files"] != count or restored_result["bytes"] != total:
            _fail()
        receipt = {
            "schema": "vh.map02.owner-runtime-private-drive-readback.v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "session": session,
            "source_verified_against_owner_pin": True,
            "remote_type": "drive",
            "runtime_file_count": count,
            "runtime_total_bytes": total,
            "objects": metadata,
            "full_restored_tree_compared": True,
            "original_game_media_used": False,
            "capture_ready": False,
        }
        receipt_file = staging / (stem + ".receipt.json")
        fd = os.open(receipt_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write((json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
        receipt_name = stem + ".receipt.json"
        if receipt_name in existing_manifests:
            _fail()
        receipt_target = manifests + ":" + receipt_name
        invoke(["copyto", "--immutable", "--no-traverse", str(receipt_file),
                receipt_target])
        receipt_id = _stat_remote(
            receipt_target, receipt_name, receipt_file.stat().st_size, invoke
        )
        receipt_download = staged_files / receipt_name
        invoke(["copyto", "--immutable", receipt_target, str(receipt_download)])
        if _hash_file(_require_file(receipt_download, source)) != _hash_file(receipt_file):
            _fail()
        return {
            "schema": receipt["schema"],
            "remote_receipt_id": receipt_id,
            "objects_read_back": len(metadata) + 1,
            "files": count,
            "bytes": total,
            "drive_download_bytes_verified": True,
            "capture_ready": False,
        }
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError):
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("owner_manifest_pin", type=Path)
    parser.add_argument("packed_tar", type=Path)
    parser.add_argument("tar_sha256_pin", type=Path)
    parser.add_argument("new_private_readback_dir", type=Path)
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--private-folder-map", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = archive_to_private_drive(
            args.runtime, args.owner_manifest_pin,
            args.packed_tar, args.tar_sha256_pin, args.new_private_readback_dir,
            args.builds_remote, args.manifests_remote, args.session,
            args.private_folder_map,
        )
    except PrivateDriveError:
        print("VH_MAP02_STAGE537_PRIVATE_DRIVE_READBACK_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_STAGE537_PRIVATE_DRIVE_READBACK_PASS "
          "downloaded_objects=%d runtime_files=%d "
          "reconstructed_bytes=%d original_game=0 capture_ready=0" %
          (report["objects_read_back"], report["files"], report["bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
