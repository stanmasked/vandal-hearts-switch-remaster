#!/usr/bin/env python3
"""Read-only readiness check for an authenticated owner-private MAP02 backup.

No files are written. Uses already configured owner-local rclone remotes and
a separately trusted owner manifest. Fictional CI tests never invoke OAuth.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import stat

from tools.map02_linux_octoshock.archive_owner_runtime import _inventory, _root
from tools.map02_linux_octoshock.private_runtime_drive import (
    _call_rclone, _check_remote, _existing_names, _folder_map,
    _remote_name, forbidden_original_media_path, SESSION_PATTERN,
)
from tools.map02_linux_octoshock.private_runtime_tar import _outside, _hash_file, _pin
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime
from tools.map02_linux_octoshock.owner_persistent_host import (
    MINIMUM_PUBLISH_BYTES, verify_persistent_private_host,
    snapshot_private_path_identity, require_unchanged_persistent_host,
)


class OwnerPreflightError(ValueError):
    pass


def _fail() -> None:
    raise OwnerPreflightError("owner-private MAP02 backup preflight rejected")


def verify_owner_backup_readiness(
    runtime: Path, trusted_manifest_pin: Path, private_folder_map: Path,
    new_session_root: Path, new_receipt_pin: Path,
    builds_remote: str, manifests_remote: str, session: str, *,
    invoke=_call_rclone,
    disk_usage=None,
) -> dict[str, object]:
    """Require safe space, trust, remote scope and unique artifact names."""
    try:
        source = _root(runtime)
        builds = _remote_name(builds_remote)
        manifests = _remote_name(manifests_remote)
        if (builds == manifests or not isinstance(session, str)
                or SESSION_PATTERN.fullmatch(session) is None):
            _fail()
        root = _outside(new_session_root, source, nonexistent=True)
        receipt = _outside(new_receipt_pin, source, nonexistent=True)
        pin = _outside(trusted_manifest_pin, source)
        config = _outside(private_folder_map, source)
        if (len({str(root), str(receipt), str(pin), str(config)}) != 4
                or receipt.is_relative_to(root) or pin.is_relative_to(root)
                or config.is_relative_to(root)):
            _fail()
        # Pin the local trust anchor and runtime manifest before any remote
        # inspection. Recheck both after all network reads so a preflight cannot
        # pass on mixed snapshots if a local file changes mid-check.
        trusted_pin_value = _pin(pin)
        manifest_path = source / "map02-owner-runtime-manifest.json"
        manifest_digest = _hash_file(manifest_path)
        verified = verify_runtime(
            source, trusted_manifest_pin_file=pin,
            require_trusted_pin=True,
        )
        if (verified.get("verified") is not True
                or verified.get("trusted_manifest_pin_verified") is not True
                or verified.get("capture_ready") is not False
                or _pin(pin) != trusted_pin_value
                or _hash_file(manifest_path) != manifest_digest):
            _fail()
        entries, count, total = _inventory(source)
        if (not entries or count <= 0 or total <= 0
                or any(forbidden_original_media_path(name) for name in entries)):
            _fail()
        # At least 512 MiB or 10x unpacked bytes, whichever is larger.
        # Tar, sealed tar, downloaded copies and safe-restored trees coexist.
        required = max(512 * 1024 * 1024, total * 10)
        usage_fn = shutil.disk_usage if disk_usage is None else disk_usage
        if usage_fn(root.parent).free < required:
            _fail()
        builds_id, manifests_id = _folder_map(config, source)

        # On the real owner path, preflight is also a persistent-storage gate.
        # Synthetic CI deliberately cannot assert properties of the owner host.
        real_transport = invoke is _call_rclone
        guarded_paths = list(dict.fromkeys((
            source, pin.parent, config.parent, root.parent, receipt.parent,
        )))
        host_identity = None
        if real_transport:
            verify_persistent_private_host(
                guarded_paths,
                minimum_free_bytes=max(MINIMUM_PUBLISH_BYTES, required),
            )
            host_identity = snapshot_private_path_identity(guarded_paths)

        _check_remote(builds, builds_id, invoke)
        _check_remote(manifests, manifests_id, invoke)
        names_in_builds = _existing_names(builds, invoke)
        names_in_manifests = _existing_names(manifests, invoke)
        stem = "map02-runtime-" + session
        if (stem + ".tar" in names_in_builds
                or any(stem + ext in names_in_manifests for ext in (
                    ".tar.sha256", ".manifest.json",
                    ".manifest.sha256", ".receipt.json"))):
            _fail()

        # Reject mixed local/remote snapshots: re-read the folder mapping,
        # trusted pin, runtime manifest and full inventory after all remote
        # queries. Also ensure another process did not reserve output paths.
        verified_after = verify_runtime(
            source, trusted_manifest_pin_file=pin,
            require_trusted_pin=True,
        )
        entries_after, count_after, total_after = _inventory(source)
        if (verified_after.get("verified") is not True
                or verified_after.get("trusted_manifest_pin_verified") is not True
                or verified_after.get("capture_ready") is not False
                or _pin(pin) != trusted_pin_value
                or _hash_file(manifest_path) != manifest_digest
                or _folder_map(config, source) != (builds_id, manifests_id)
                or entries_after != entries or count_after != count
                or total_after != total
                or root.exists() or root.is_symlink()
                or receipt.exists() or receipt.is_symlink()):
            _fail()
        if real_transport:
            require_unchanged_persistent_host(
                guarded_paths, host_identity,
                minimum_free_bytes=max(MINIMUM_PUBLISH_BYTES, required),
            )
        return {
            "runtime_files": count,
            "runtime_bytes": total,
            "required_free_bytes": required,
            "owner_manifest_pin_verified": True,
            "drive_remotes_checked": 2,
            "cloud_names_available": True,
            "writes_performed": False,
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
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        result = verify_owner_backup_readiness(
            args.runtime, args.trusted_manifest_pin, args.private_folder_map,
            args.new_session_root, args.new_owner_receipt_pin,
            args.builds_remote, args.manifests_remote, args.session,
        )
    except OwnerPreflightError:
        print("VH_MAP02_STAGE542_OWNER_PREFLIGHT_REJECTED capture_ready=0")
        return 1
    print(
        "VH_MAP02_STAGE542_OWNER_PREFLIGHT_PASS "
        "files=%d minimum_free_bytes=%d drive_remotes=2 "
        "drive_upload=0 original_game=0 capture_ready=0" %
        (result["runtime_files"], result["required_free_bytes"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
