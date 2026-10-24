#!/usr/bin/env python3
"""Stage550: private persistent owner-host build and full Drive backup pipeline.

PREPARE builds an original-game-free runtime, NEVER generates a trusted SHA.
PUBLISH requires an independently owner-established runtime-manifest SHA
and invokes three independent cloud readbacks through existing audited tools.
Public CI uses only a fictional in-memory Drive transport; no media/OAuth.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
from typing import Callable

from tools.map02_linux_octoshock.build_and_stage_owner import build_and_stage
from tools.map02_linux_octoshock.owner_drive_session import complete_owner_archive_session
from tools.map02_linux_octoshock.owner_archive_admission import (
    admit_independent_owner_archive, verify_sealed_owner_admission,
)
from tools.map02_linux_octoshock.owner_capture_backup_gate import audit_capture_backup_gate
from tools.map02_linux_octoshock.private_runtime_drive import (
    _call_rclone, SESSION_PATTERN,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import _private_input
from tools.map02_linux_octoshock.private_runtime_tar import _outside
from tools.map02_linux_octoshock.archive_owner_runtime import _root
from tools.map02_linux_octoshock.verify_owner_runtime import verify_runtime
from tools.map02_linux_octoshock.owner_persistent_host import (
    MINIMUM_PREPARE_BYTES, MINIMUM_PUBLISH_BYTES,
    verify_persistent_private_host, snapshot_private_path_identity,
    require_unchanged_persistent_host,
)


class OwnerPersistentBackupError(ValueError):
    """Redacted owner-side failure; do not print secrets or private paths."""


def _fail() -> None:
    raise OwnerPersistentBackupError(
        "owner-private persistent runtime backup pipeline rejected"
    )


def _private_parent(value: Path, runtime: Path) -> Path:
    """Require a pre-existing private ordinary directory outside Git/runtime."""
    try:
        candidate = _outside(value, runtime)
        info = candidate.stat()
        if (candidate.is_symlink() or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            _fail()
        return candidate
    except (OSError, ValueError):
        _fail()


def publish_existing_trusted_runtime(
    runtime: Path,
    independently_trusted_manifest_pin: Path,
    private_folder_map: Path,
    private_work_parent: Path,
    private_trust_parent: Path,
    builds_remote: str,
    manifests_remote: str,
    session: str,
    *,
    invoke: Callable[[list[str]], str] = _call_rclone,
) -> dict[str, object]:
    """One owner-local operation: upload, admit and independently re-download.

    This requires a separately established trusted manifest pin and leaves
    it unchanged. Outputs stay on persistent owner-private storage even
    when a subsequent stage fails; previous attempt outputs are not reused.
    """
    try:
        source = _root(runtime)
        manifest_pin = _private_input(independently_trusted_manifest_pin)
        folder_map = _private_input(private_folder_map)
        work = _private_parent(private_work_parent, source)
        trust = _private_parent(private_trust_parent, source)
        if (not isinstance(session, str)
                or SESSION_PATTERN.fullmatch(session) is None
                or work == trust
                or work.is_relative_to(trust)
                or trust.is_relative_to(work)
                or manifest_pin.is_relative_to(work)
                or folder_map.is_relative_to(work)):
            _fail()
        paths = {
            "transfer": work / (session + "-transfer"),
            "admission_readback": work / (session + "-admission-readback"),
            "preboot_readback": work / (session + "-preboot-readback"),
            "archive_pin": trust / (session + "-archive.sha256"),
            "receipt_pin": trust / (session + "-receipt.sha256"),
            "admission_proof": trust / (session + "-admission.json"),
            "admission_pin": trust / (session + "-admission.sha256"),
        }
        if (len(set(paths.values())) != len(paths)
                or any(p.exists() or p.is_symlink() for p in paths.values())
                or any(p == manifest_pin or p == folder_map for p in paths.values())):
            _fail()
        # Real owner must ALSO keep the original independently trusted SHA
        # and private Drive-folder mapping on persistent local storage.
        # Checking only the new output folder would leave these vital
        # inputs vulnerable to the same ephemeral runner disappearance.
        # Fake in-memory cloud tests never claim this proves a real host.
        real_host = invoke is _call_rclone
        guarded_paths = list(dict.fromkeys((
            source, work, trust, manifest_pin.parent, folder_map.parent,
        )))
        initial_host_identity = None
        if real_host:
            verify_persistent_private_host(
                guarded_paths, minimum_free_bytes=MINIMUM_PUBLISH_BYTES,
            )
            initial_host_identity = snapshot_private_path_identity(guarded_paths)

        def recheck_owner_host() -> None:
            if real_host:
                require_unchanged_persistent_host(
                    guarded_paths, initial_host_identity,
                    minimum_free_bytes=MINIMUM_PUBLISH_BYTES,
                )

        checked = verify_runtime(
            source, trusted_manifest_pin_file=manifest_pin,
            require_trusted_pin=True,
        )
        if (checked.get("verified") is not True
                or checked.get("trusted_manifest_pin_verified") is not True
                or checked.get("capture_ready") is not False):
            _fail()
        # Recheck after digest verification, immediately before cloud writes.
        recheck_owner_host()

        uploaded = complete_owner_archive_session(
            source, manifest_pin, folder_map, paths["transfer"],
            paths["receipt_pin"], builds_remote, manifests_remote, session,
            independent_archive_pin_output=paths["archive_pin"], invoke=invoke,
        )
        if (uploaded.get("owner_archive_pin_written") is not True
                or uploaded.get("owner_receipt_pin_created") is not True
                or uploaded.get("full_private_restore_audited") is not True
                or uploaded.get("cloud_objects_retrieved") != 5):
            _fail()
        # A changed mount/directory may never be promoted to owner evidence.
        recheck_owner_host()
        admission = admit_independent_owner_archive(
            folder_map, manifest_pin, paths["archive_pin"],
            paths["receipt_pin"], paths["admission_readback"],
            paths["admission_proof"], builds_remote, manifests_remote, session,
            independent_proof_pin_output=paths["admission_pin"], invoke=invoke,
        )
        # A previously produced seal and a newly checked seal are separate
        # checks. A fake transport must not become "real" here.
        sealed = verify_sealed_owner_admission(
            paths["admission_proof"], paths["admission_pin"],
            require_real_transport=real_host,
        )
        recheck_owner_host()
        fresh = audit_capture_backup_gate(
            folder_map, manifest_pin, paths["archive_pin"],
            paths["receipt_pin"], paths["admission_proof"],
            paths["admission_pin"], paths["preboot_readback"],
            builds_remote, manifests_remote, session, invoke=invoke,
        )
        recheck_owner_host()
        if (admission.get("runtime_files") != uploaded.get("runtime_files")
                or admission.get("runtime_bytes") != uploaded.get("runtime_bytes")
                or fresh.get("runtime_files") != admission.get("runtime_files")
                or fresh.get("runtime_bytes") != admission.get("runtime_bytes")
                or fresh.get("fresh_remote_objects_verified") != 5
                or sealed.get("sealed_proof_sha_verified") is not True
                or fresh.get("capture_ready") is not False):
            _fail()
        real = invoke is _call_rclone
        if (uploaded.get("authenticated_owner_rclone_invoked") is not real
                or admission.get("default_rclone_subprocess_used") is not real
                or fresh.get("owner_backup_proven_against_trusted_pins") is not real):
            _fail()
        return {
            "schema": "vh.map02.owner-persistent-backup.v1",
            "runtime_files": fresh["runtime_files"],
            "runtime_bytes": fresh["runtime_bytes"],
            "all_three_five_object_readbacks_verified": True,
            "sealed_owner_admission_verified": True,
            "independently_supplied_manifest_sha_required": True,
            "real_scoped_rclone_subprocess_used": real,
            "authentic_owner_backup_claim_permitted": real,
            "game_media_loaded": False,
            "cold_map02_launches": 0,
            "capture_ready": False,
        }
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, UnicodeError):
        _fail()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare", help="Build no-game-media runtime; do not create SHA trust pin")
    prep.add_argument("--new-runtime-root", required=True, type=Path)
    prep.add_argument("--keep-private-workdir", action="store_true")
    pub = sub.add_parser("publish", help="Back up pre-trusted runtime with fresh independent audits")
    pub.add_argument("--runtime", required=True, type=Path)
    pub.add_argument("--independently-trusted-manifest-pin", required=True, type=Path)
    pub.add_argument("--private-folder-map", required=True, type=Path)
    pub.add_argument("--private-work-parent", required=True, type=Path)
    pub.add_argument("--private-trust-parent", required=True, type=Path)
    pub.add_argument("--builds-remote", required=True)
    pub.add_argument("--manifests-remote", required=True)
    pub.add_argument("--session", required=True)
    a = p.parse_args()
    try:
        if a.action == "prepare":
            parent_paths = [a.new_runtime_root.parent]
            verify_persistent_private_host(
                parent_paths, minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            )
            host_identity = snapshot_private_path_identity(parent_paths)
            record = build_and_stage(
                a.new_runtime_root, keep_workdir=a.keep_private_workdir,
            )
            # Long native builds may outlive or move across host mounts.
            # A changed parent cannot earn a successful prepare marker.
            require_unchanged_persistent_host(
                parent_paths, host_identity,
                minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            )
            if (record.get("game_media_used") is not False
                    or record.get("psx_capture_ready") is not False):
                _fail()
            print("VH_MAP02_STAGE550_PREPARE_PASS "
                  "manifest_independently_trusted=0 media_used=0 capture_ready=0")
        else:
            result = publish_existing_trusted_runtime(
                a.runtime, a.independently_trusted_manifest_pin,
                a.private_folder_map, a.private_work_parent,
                a.private_trust_parent, a.builds_remote,
                a.manifests_remote, a.session,
            )
            if result["authentic_owner_backup_claim_permitted"] is not True:
                _fail()
            print("VH_MAP02_STAGE550_PUBLISH_PASS "
                  "files=%d readbacks=3x5 real_rclone=1 "
                  "game_media=0 cold_launches=0 capture_ready=0" %
                  result["runtime_files"])
    except (OSError, ValueError, RuntimeError, TypeError, KeyError):
        print("VH_MAP02_STAGE550_OWNER_PIPELINE_REJECTED capture_ready=0")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
