#!/usr/bin/env python3
"""Stage541 owner-private one-command backup session for an EXISTING pinned runtime.

No PS1 disc, BIOS, BK2, captures, OAuth secrets or actual owner files enter CI.
The CLI uses actual rclone only when executed in an owner-private environment.
It NEVER generates its own manifest trust anchor: the owner must independently
establish and retain the trusted manifest SHA-256 before running this command.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

from tools.map02_linux_octoshock.archive_owner_runtime import _root
from tools.map02_linux_octoshock.private_runtime_drive import (
    _call_rclone, _remote_name, archive_to_private_drive,
    SESSION_PATTERN,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    audit_independent_readback,
)
from tools.map02_linux_octoshock.private_runtime_tar import (
    _hash_file, _outside, _pin, pack_runtime,
)
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime
from tools.map02_linux_octoshock.owner_session_preflight import verify_owner_backup_readiness


class PrivateOwnerSessionError(ValueError):
    pass


def _fail() -> None:
    raise PrivateOwnerSessionError("owner-private archive session not verified")


def complete_owner_archive_session(
    runtime: Path,
    trusted_manifest_pin: Path,
    private_folder_map: Path,
    owner_session_root: Path,
    independently_retained_receipt_pin: Path,
    builds_remote: str,
    manifests_remote: str,
    session: str,
    *,
    independent_archive_pin_output: Path | None = None,
    invoke=_call_rclone,
) -> dict[str, object]:
    """Pack, upload, download and source-free re-audit in one fail-closed run.

    The pre-existing trusted manifest pin MUST have been established through
    an independent owner-controlled process. A CI-created pin is not valid
    evidence of independent owner provenance.
    """
    try:
        source = _root(runtime)
        builds = _remote_name(builds_remote)
        manifests = _remote_name(manifests_remote)
        if (builds == manifests or not isinstance(session, str)
                or SESSION_PATTERN.fullmatch(session) is None):
            _fail()

        root = _outside(owner_session_root, source, nonexistent=True)
        receipt_pin = _outside(
            independently_retained_receipt_pin, source, nonexistent=True,
        )
        manifest_pin = _outside(trusted_manifest_pin, source)
        folder_map = _outside(private_folder_map, source)
        tar_pin_out = None
        if independent_archive_pin_output is not None:
            tar_pin_out = _outside(
                independent_archive_pin_output, source, nonexistent=True,
            )
        distinct = {str(root), str(receipt_pin), str(manifest_pin),
                    str(folder_map)}
        if tar_pin_out is not None:
            distinct.add(str(tar_pin_out))
        if (len(distinct) != (5 if tar_pin_out is not None else 4) or
                receipt_pin == root or receipt_pin.is_relative_to(root) or
                manifest_pin.is_relative_to(root) or folder_map.is_relative_to(root)
                or (tar_pin_out is not None and
                    (tar_pin_out == root or tar_pin_out.is_relative_to(root)))):
            _fail()
        for p in (manifest_pin, folder_map):
            if (not p.is_file() or p.is_symlink()
                    or stat.S_IMODE(p.stat().st_mode) != 0o600):
                _fail()

        check = verify_runtime(
            source, trusted_manifest_pin_file=manifest_pin,
            require_trusted_pin=True,
        )
        if (check.get("verified") is not True
                or check.get("trusted_manifest_pin_verified") is not True
                or check.get("capture_ready") is not False):
            _fail()

        readiness = verify_owner_backup_readiness(
            source, manifest_pin, folder_map, root, receipt_pin,
            builds, manifests, session, invoke=invoke,
        )
        if (readiness["writes_performed"] is not False
                or readiness["cloud_names_available"] is not True
                or readiness["capture_ready"] is not False):
            _fail()

        # No dangerous partial overwrite / resume. An interrupted session
        # remains private, is not called a success and requires fresh naming.
        root.mkdir(mode=0o700)
        archive_folder = root / "archive"
        upload_folder = root / "upload"
        audit_folder = root / "independent-reaudit"
        for folder in (archive_folder, upload_folder, audit_folder):
            folder.mkdir(mode=0o700)
        stem = "map02-runtime-" + session
        tar = archive_folder / (stem + ".tar")
        tar_digest = archive_folder / (stem + ".tar.sha256")
        packed = pack_runtime(source, manifest_pin, tar, tar_digest)
        if (packed["files"] <= 0 or packed["bytes"] <= 0
                or packed.get("drive_upload_authenticated") is not False):
            _fail()
        uploaded = archive_to_private_drive(
            source, manifest_pin, tar, tar_digest, upload_folder / "new-copy",
            builds, manifests, session, folder_map,
            owner_receipt_pin_output=receipt_pin, invoke=invoke,
        )
        if (not uploaded["drive_download_bytes_verified"]
                or not uploaded["owner_receipt_pin_written"]
                or uploaded["objects_read_back"] != 5
                or uploaded["capture_ready"] is not False):
            _fail()
        receipt_sha = _pin(receipt_pin)
        independent = audit_independent_readback(
            folder_map, manifest_pin, tar_digest, receipt_pin,
            audit_folder / "new-copy", builds, manifests, session,
            invoke=invoke,
        )
        if (_pin(receipt_pin) != receipt_sha
                or independent["files"] != packed["files"]
                or independent["bytes"] != packed["bytes"]
                or independent["objects_read_back"] != 5
                or not independent["independent_receipt_pin_verified"]
                or independent["original_runtime_required"] is not False
                or independent["capture_ready"] is not False):
            _fail()
        # Stage544: preserve the third trust reference OUTSIDE the disposable
        # session. Export only after a complete source-free cloud re-audit.
        # Incomplete uploads must never produce an endorsed owner archive pin.
        if tar_pin_out is not None:
            digest = _pin(tar_digest)
            if _hash_file(tar) != digest:
                _fail()
            fd = os.open(tar_pin_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write((digest + "\n").encode("ascii"))
            if _pin(tar_pin_out) != digest or _hash_file(tar) != digest:
                _fail()
        return {
            "runtime_files": independent["files"],
            "runtime_bytes": independent["bytes"],
            "cloud_objects_retrieved": 5,
            "full_private_restore_audited": True,
            # A synthetic CI transport is NEVER owner cloud evidence.
            "authenticated_owner_rclone_invoked": invoke is _call_rclone,
            "trusted_owner_manifest_pin_required": True,
            "owner_receipt_pin_created": True,
            "owner_archive_pin_written": tar_pin_out is not None,
            "original_game_media_used": False,
            "capture_ready": False,
        }
    except (OSError, ValueError, RuntimeError, TypeError, KeyError):
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--trusted-manifest-pin", required=True, type=Path)
    parser.add_argument("--private-folder-map", required=True, type=Path)
    parser.add_argument("--new-session-root", required=True, type=Path)
    parser.add_argument("--new-owner-receipt-pin", required=True, type=Path)
    parser.add_argument("--new-owner-archive-pin", required=True, type=Path,
                        help="separate 0600 pin outside the disposable session")
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        result = complete_owner_archive_session(
            args.runtime, args.trusted_manifest_pin, args.private_folder_map,
            args.new_session_root, args.new_owner_receipt_pin,
            args.builds_remote, args.manifests_remote, args.session,
            independent_archive_pin_output=args.new_owner_archive_pin,
        )
    except PrivateOwnerSessionError:
        print("VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_REJECTED capture_ready=0")
        return 1
    if (not result["authenticated_owner_rclone_invoked"]
            or not result["owner_archive_pin_written"]):
        print("VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_REJECTED capture_ready=0")
        return 1
    print(
        "VH_MAP02_STAGE541_OWNER_DRIVE_SESSION_PASS "
        "runtime_files=%d runtime_bytes=%d verified_objects=5 "
        "real_rclone_invoked=1 original_game_media=0 capture_ready=0" %
        (result["runtime_files"], result["runtime_bytes"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
