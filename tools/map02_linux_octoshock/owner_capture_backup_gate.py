#!/usr/bin/env python3
"""Stage548: independently recheck sealed owner Drive backup before MAP02 capture.

Real owner CLI uses configured, scoped rclone (never public CI credentials).
Fake transport is useful only for synthetic test mechanics, not real proof.
No original disc, BIOS, BK2, gameplay screenshot or secret is read.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from tools.map02_linux_octoshock.owner_archive_admission import (
    OwnerArchiveAdmissionError, verify_sealed_owner_admission,
)
from tools.map02_linux_octoshock.private_runtime_drive import _call_rclone
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    _private_input, audit_independent_readback,
)
from tools.map02_linux_octoshock.private_runtime_tar import _hash_file, _pin


class OwnerCaptureBackupGateError(ValueError):
    pass


def _fail() -> None:
    raise OwnerCaptureBackupGateError("owner backup must be independently restored before capture")


def audit_capture_backup_gate(
    private_folder_map: Path,
    owner_manifest_pin: Path, owner_archive_pin: Path, owner_receipt_pin: Path,
    previous_admission_proof: Path, previous_admission_proof_pin: Path,
    fresh_restore_root: Path, builds_remote: str, manifests_remote: str,
    session: str, *,
    invoke: Callable[[list[str]], str] = _call_rclone,
) -> dict[str, object]:
    """Verify independently sealed past admission AND fresh live remote bytes."""
    try:
        real_transport = invoke is _call_rclone
        signed = verify_sealed_owner_admission(
            previous_admission_proof, previous_admission_proof_pin,
            require_real_transport=real_transport,
        )
        record_file = _private_input(previous_admission_proof)
        record_pin = _private_input(previous_admission_proof_pin)
        owner_manifest = _private_input(owner_manifest_pin)
        owner_tar = _private_input(owner_archive_pin)
        owner_receipt = _private_input(owner_receipt_pin)
        baseline_proof = _hash_file(record_file)
        baseline_pin = _pin(record_pin)
        previous = json.loads(record_file.read_text(encoding="utf-8"))
        if (not isinstance(previous, dict)
                or previous.get("session") != session
                or previous.get("owner_pins") != {
                    "owner_manifest_sha256": _pin(owner_manifest),
                    "owner_archive_sha256": _pin(owner_tar),
                    "owner_receipt_sha256": _pin(owner_receipt),
                }
                or previous.get("default_rclone_subprocess_used") is not real_transport
                or signed["fake_transport_recorded"] is real_transport):
            _fail()
        # A second independent cold download, not the previous local readback.
        fresh = audit_independent_readback(
            private_folder_map, owner_manifest, owner_tar, owner_receipt,
            fresh_restore_root, builds_remote, manifests_remote, session,
            invoke=invoke,
        )
        if (fresh.get("files") != previous.get("runtime_files")
                or fresh.get("bytes") != previous.get("runtime_bytes")
                or fresh.get("objects_read_back") != 5
                or fresh.get("independent_receipt_pin_verified") is not True
                or fresh.get("original_runtime_required") is not False
                or fresh.get("capture_ready") is not False
                or _hash_file(record_file) != baseline_proof
                or _pin(record_pin) != baseline_pin
                or _pin(owner_manifest) != previous["owner_pins"]["owner_manifest_sha256"]
                or _pin(owner_tar) != previous["owner_pins"]["owner_archive_sha256"]
                or _pin(owner_receipt) != previous["owner_pins"]["owner_receipt_sha256"]):
            _fail()
        return {
            "schema": "vh.map02.owner-live-backup-gate.v1",
            "session": session,
            "runtime_files": fresh["files"],
            "runtime_bytes": fresh["bytes"],
            "fresh_remote_objects_verified": 5,
            "previous_admission_seal_verified": True,
            "actual_rclone_path_used": real_transport,
            "synthetic_transport_used": not real_transport,
            "owner_backup_proven_against_trusted_pins": real_transport,
            "game_media_executed": False,
            "cold_launches_verified": 0,
            "capture_ready": False,
        }
    except (OSError, ValueError, TypeError, RuntimeError, KeyError, UnicodeError):
        _fail()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--private-folder-map", required=True, type=Path)
    p.add_argument("--owner-manifest-pin", required=True, type=Path)
    p.add_argument("--owner-archive-pin", required=True, type=Path)
    p.add_argument("--owner-receipt-pin", required=True, type=Path)
    p.add_argument("--admission-proof", required=True, type=Path)
    p.add_argument("--admission-proof-pin", required=True, type=Path)
    p.add_argument("--new-restored-root", required=True, type=Path)
    p.add_argument("--builds-remote", required=True)
    p.add_argument("--manifests-remote", required=True)
    p.add_argument("--session", required=True)
    args = p.parse_args()
    try:
        result = audit_capture_backup_gate(
            args.private_folder_map, args.owner_manifest_pin,
            args.owner_archive_pin, args.owner_receipt_pin,
            args.admission_proof, args.admission_proof_pin,
            args.new_restored_root, args.builds_remote, args.manifests_remote,
            args.session,
        )
        if result["owner_backup_proven_against_trusted_pins"] is not True:
            _fail()
    except OwnerCaptureBackupGateError:
        print("VH_MAP02_STAGE548_OWNER_BACKUP_GATE_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_STAGE548_OWNER_BACKUP_GATE_PASS "
          "files=%d fresh_objects=5 rclone_real=1 cold_launches=0 capture_ready=0" %
          result["runtime_files"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
