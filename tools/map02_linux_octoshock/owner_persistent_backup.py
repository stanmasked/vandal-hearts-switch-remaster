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
from tools.map02_linux_octoshock.owner_drive_session import (
    complete_owner_archive_session, _reject_unresolved_pin_quarantine,
)
from tools.map02_linux_octoshock.owner_session_preflight import (
    verify_owner_backup_readiness,
)
from tools.map02_linux_octoshock.owner_archive_admission import (
    admit_independent_owner_archive, verify_sealed_owner_admission,
)
from tools.map02_linux_octoshock.owner_capture_backup_gate import audit_capture_backup_gate
from tools.map02_linux_octoshock.private_runtime_drive import (
    _call_rclone, SESSION_PATTERN,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import _private_input
from tools.map02_linux_octoshock.private_runtime_tar import _outside, _pin, _hash_file
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


def _owner_publication_plan(
    runtime: Path,
    independently_trusted_manifest_pin: Path,
    private_folder_map: Path,
    private_work_parent: Path,
    private_trust_parent: Path,
    session: str,
) -> tuple[Path, Path, Path, Path, Path, dict[str, Path]]:
    """Share exact output reservations between read-only preflight and publish."""
    source = _root(runtime)
    manifest_pin = _private_input(independently_trusted_manifest_pin)
    folder_map = _private_input(private_folder_map)
    work = _private_parent(private_work_parent, source)
    trust = _private_parent(private_trust_parent, source)
    if (not isinstance(session, str)
            or SESSION_PATTERN.fullmatch(session) is None
            or work == trust or work.is_relative_to(trust)
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
    return source, manifest_pin, folder_map, work, trust, paths


def preflight_existing_trusted_runtime(
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
    """Read-only owner-host readiness and all-seven-output reservation check.

    Does not create lock files, trust pins, an output tree or cloud objects.
    A successful preflight is a snapshot, NOT a claim of a successful publish:
    publish must independently revalidate all paths and remote scope.
    """
    try:
        source, pin, folder_map, work, trust, paths = _owner_publication_plan(
            runtime, independently_trusted_manifest_pin, private_folder_map,
            private_work_parent, private_trust_parent, session,
        )
        guarded = list(dict.fromkeys((
            source, work, trust, pin.parent, folder_map.parent,
        )))
        real_host = invoke is _call_rclone
        identity = None
        if real_host:
            verify_persistent_private_host(
                guarded, minimum_free_bytes=MINIMUM_PUBLISH_BYTES,
            )
            identity = snapshot_private_path_identity(guarded)
        _reject_unresolved_pin_quarantine(
            paths["receipt_pin"], paths["archive_pin"],
        )
        readiness = verify_owner_backup_readiness(
            source, pin, folder_map, paths["transfer"],
            paths["receipt_pin"], builds_remote, manifests_remote, session,
            invoke=invoke,
        )
        if (readiness.get("owner_manifest_pin_verified") is not True
                or readiness.get("cloud_names_available") is not True
                or readiness.get("drive_remotes_checked") != 2
                or readiness.get("writes_performed") is not False
                or readiness.get("capture_ready") is not False):
            _fail()
        # The detailed session preflight sees only the transfer and receipt
        # paths; the complete owner pipeline needs five more free outputs.
        # Recheck all seven after remote reads to detect late reservations.
        _reject_unresolved_pin_quarantine(
            paths["receipt_pin"], paths["archive_pin"],
        )
        if any(p.exists() or p.is_symlink() for p in paths.values()):
            _fail()
        if real_host:
            require_unchanged_persistent_host(
                guarded, identity, minimum_free_bytes=MINIMUM_PUBLISH_BYTES,
            )
        return {
            "schema": "vh.map02.owner-persistent-preflight.v1",
            "runtime_files": readiness["runtime_files"],
            "runtime_bytes": readiness["runtime_bytes"],
            "output_paths_available": 7,
            "drive_remotes_checked": 2,
            "trusted_manifest_pin_verified": True,
            "persistent_host_checked": real_host,
            "writes_performed": False,
            "remote_upload_performed": False,
            "owner_backup_proven": False,
            "capture_ready": False,
        }
    except (OSError, ValueError, RuntimeError, TypeError, KeyError,
            UnicodeError, AttributeError):
        _fail()


def _reference_snapshot(path: Path, *, sha_pin: bool) -> tuple[object, ...]:
    """Read an owner-private trusted reference and bind it to the same inode.

    The snapshot is kept in memory only. No trust digest or private pathname is
    printed or uploaded. Checking both data and inode metadata rejects an
    identically re-created SHA pin as well as a modified digest.
    """
    try:
        checked = _private_input(path)
        before = checked.lstat()
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1):
            _fail()
        value = _pin(checked) if sha_pin else _hash_file(checked)
        after = checked.lstat()
        def identity(item):
            return (item.st_dev, item.st_ino, item.st_uid,
                    stat.S_IMODE(item.st_mode), item.st_nlink,
                    item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after):
            _fail()
        return (identity(after), value)
    except (OSError, ValueError, TypeError, AttributeError):
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
        source, manifest_pin, folder_map, work, trust, paths = (
            _owner_publication_plan(
                runtime, independently_trusted_manifest_pin,
                private_folder_map, private_work_parent, private_trust_parent,
                session,
            )
        )
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
        # An independently supplied trusted pin and the private Drive scope
        # mapping must remain byte-for-byte and inode-identical across all
        # three cloud downloads; never silently trust a replacement file.
        baseline = {
            "manifest": _reference_snapshot(manifest_pin, sha_pin=True),
            "folder_map": _reference_snapshot(folder_map, sha_pin=False),
        }
        pinned_outputs: dict[str, tuple[object, ...]] = {}

        def confirm_references() -> None:
            for key, (item, is_pin) in {
                "manifest": (manifest_pin, True),
                "folder_map": (folder_map, False),
                "archive": (paths["archive_pin"], True),
                "receipt": (paths["receipt_pin"], True),
                "admission_pin": (paths["admission_pin"], True),
                "admission_proof": (paths["admission_proof"], False),
            }.items():
                expected = baseline.get(key, pinned_outputs.get(key))
                if expected is not None and (
                        _reference_snapshot(item, sha_pin=is_pin) != expected):
                    _fail()

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
        # Verify trusted owner inputs after potentially lengthy runtime
        # checks, before the first remote transfer.
        confirm_references()
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
        # Pin the newly written archive and receipt before admission. An
        # older independent owner digest must never be silently replaced
        # between the first upload and the second cloud readback.
        confirm_references()
        pinned_outputs["archive"] = _reference_snapshot(
            paths["archive_pin"], sha_pin=True,
        )
        pinned_outputs["receipt"] = _reference_snapshot(
            paths["receipt_pin"], sha_pin=True,
        )
        recheck_owner_host()
        admission = admit_independent_owner_archive(
            folder_map, manifest_pin, paths["archive_pin"],
            paths["receipt_pin"], paths["admission_readback"],
            paths["admission_proof"], builds_remote, manifests_remote, session,
            independent_proof_pin_output=paths["admission_pin"], invoke=invoke,
        )
        # The independent admission just produced two more owner-side
        # references. Bind these to their original names, device and inode.
        confirm_references()
        pinned_outputs["admission_proof"] = _reference_snapshot(
            paths["admission_proof"], sha_pin=False,
        )
        pinned_outputs["admission_pin"] = _reference_snapshot(
            paths["admission_pin"], sha_pin=True,
        )
        # A previously produced seal and a newly checked seal are separate
        # checks. A fake transport must not become "real" here.
        sealed = verify_sealed_owner_admission(
            paths["admission_proof"], paths["admission_pin"],
            require_real_transport=real_host,
        )
        confirm_references()
        recheck_owner_host()
        fresh = audit_capture_backup_gate(
            folder_map, manifest_pin, paths["archive_pin"],
            paths["receipt_pin"], paths["admission_proof"],
            paths["admission_pin"], paths["preboot_readback"],
            builds_remote, manifests_remote, session, invoke=invoke,
        )
        # Final source-free download may take minutes. Reject any changed
        # identity/value for all four owner SHA pins or the sealed admission
        # report, even if bytes were restored successfully before replacement.
        confirm_references()
        sealed_after = verify_sealed_owner_admission(
            paths["admission_proof"], paths["admission_pin"],
            require_real_transport=real_host,
        )
        recheck_owner_host()
        if (admission.get("runtime_files") != uploaded.get("runtime_files")
                or admission.get("runtime_bytes") != uploaded.get("runtime_bytes")
                or fresh.get("runtime_files") != admission.get("runtime_files")
                or fresh.get("runtime_bytes") != admission.get("runtime_bytes")
                or fresh.get("fresh_remote_objects_verified") != 5
                or sealed.get("sealed_proof_sha_verified") is not True
                or sealed_after.get("sealed_proof_sha_verified") is not True
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
    dry = sub.add_parser("preflight", help="Read-only private owner-host and Drive scope checks")
    for command in (pub, dry):
        command.add_argument("--runtime", required=True, type=Path)
        command.add_argument("--independently-trusted-manifest-pin", required=True, type=Path)
        command.add_argument("--private-folder-map", required=True, type=Path)
        command.add_argument("--private-work-parent", required=True, type=Path)
        command.add_argument("--private-trust-parent", required=True, type=Path)
        command.add_argument("--builds-remote", required=True)
        command.add_argument("--manifests-remote", required=True)
        command.add_argument("--session", required=True)
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
            # Stage599: the build validated its temporary stage before
            # promotion. Independently verify the *promoted* runtime on the
            # owner-persistent destination, not just its build-time manifest.
            # No external owner trust pin is minted by this preparation step.
            installed = verify_runtime(
                a.new_runtime_root, require_trusted_pin=False,
            )
            if (installed.get("verified") is not True
                    or installed.get("trusted_manifest_pin_verified") is not False
                    or installed.get("capture_ready") is not False):
                _fail()
            # Verification can take time; refuse an altered storage mount
            # after reading all installed components.
            require_unchanged_persistent_host(
                parent_paths, host_identity,
                minimum_free_bytes=MINIMUM_PREPARE_BYTES,
            )
            print("VH_MAP02_STAGE550_PREPARE_PASS "
                  "installed_runtime_verified=1 "
                  "manifest_independently_trusted=0 media_used=0 capture_ready=0")
        elif a.action == "preflight":
            result = preflight_existing_trusted_runtime(
                a.runtime, a.independently_trusted_manifest_pin,
                a.private_folder_map, a.private_work_parent,
                a.private_trust_parent, a.builds_remote,
                a.manifests_remote, a.session,
            )
            if (result.get("writes_performed") is not False
                    or result.get("remote_upload_performed") is not False
                    or result.get("owner_backup_proven") is not False):
                _fail()
            print("VH_MAP02_STAGE600_PREFLIGHT_PASS "
                  "outputs_available=7 drive_remotes=2 "
                  "writes=0 owner_backup_proven=0 capture_ready=0")
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
