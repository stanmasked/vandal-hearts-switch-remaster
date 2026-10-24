#!/usr/bin/env python3
"""Stage545: independently admit a cloud backup after losing source runtime.

Requires three independently retained owner SHA-256 references. Fake CI
transport can test the mechanism but never proves genuine Drive retention.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Callable

from tools.map02_linux_octoshock.private_runtime_drive import _call_rclone
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    _private_input, audit_independent_readback,
)
from tools.map02_linux_octoshock.private_runtime_tar import _outside, _pin


class OwnerArchiveAdmissionError(ValueError):
    pass


def _fail() -> None:
    raise OwnerArchiveAdmissionError("owner-private cloud archive admission refused")


def admit_independent_owner_archive(
    private_folder_map: Path,
    independently_trusted_manifest_sha: Path,
    independently_trusted_archive_sha: Path,
    independently_trusted_receipt_sha: Path,
    fresh_readback_root: Path,
    new_private_proof_file: Path,
    builds_remote: str,
    manifests_remote: str,
    session: str,
    *,
    invoke: Callable[[list[str]], str] = _call_rclone,
) -> dict[str, object]:
    """Download and restore all five Drive objects before issuing a proof."""
    created = False
    proof = None
    try:
        manifest = _private_input(independently_trusted_manifest_sha)
        archive = _private_input(independently_trusted_archive_sha)
        receipt = _private_input(independently_trusted_receipt_sha)
        folder_map = _private_input(private_folder_map)
        root = _outside(fresh_readback_root, manifest, nonexistent=True)
        proof = _outside(new_private_proof_file, manifest, nonexistent=True)
        values = {str(manifest), str(archive), str(receipt),
                  str(folder_map), str(root), str(proof)}
        if len(values) != 6 or proof.is_relative_to(root):
            _fail()
        expected = {
            "owner_manifest_sha256": _pin(manifest),
            "owner_archive_sha256": _pin(archive),
            "owner_receipt_sha256": _pin(receipt),
        }
        audit = audit_independent_readback(
            folder_map, manifest, archive, receipt, root,
            builds_remote, manifests_remote, session, invoke=invoke,
        )
        if (audit.get("files", 0) < 1 or audit.get("bytes", 0) < 1
                or audit.get("objects_read_back") != 5
                or audit.get("independent_receipt_pin_verified") is not True
                or audit.get("original_runtime_required") is not False
                or audit.get("capture_ready") is not False):
            _fail()
        if (expected["owner_manifest_sha256"] != _pin(manifest)
                or expected["owner_archive_sha256"] != _pin(archive)
                or expected["owner_receipt_sha256"] != _pin(receipt)):
            _fail()
        default_transport = invoke is _call_rclone
        report = {
            "schema": "vh.map02.private-owner-archive-admission.v1",
            "checked_utc": datetime.now(timezone.utc).isoformat(),
            "session": session,
            "runtime_files": audit["files"],
            "runtime_bytes": audit["bytes"],
            "downloaded_remote_objects": 5,
            "source_runtime_not_required": True,
            "owner_pins": expected,
            "default_rclone_subprocess_used": default_transport,
            "fake_transport_injected": not default_transport,
            "owner_private_cloud_sharing_independently_audited": False,
            "original_ps1_media_executed": False,
            "authentic_map02_cold_runs_verified": False,
            "capture_ready": False,
        }
        fd = os.open(proof, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        created = True
        with os.fdopen(fd, "wb") as output:
            output.write((json.dumps(report, sort_keys=True, indent=2) + "\n").encode())
            output.flush()
            os.fsync(output.fileno())
        if (proof.is_symlink() or stat.S_IMODE(proof.stat().st_mode) != 0o600
                or expected["owner_manifest_sha256"] != _pin(manifest)
                or expected["owner_archive_sha256"] != _pin(archive)
                or expected["owner_receipt_sha256"] != _pin(receipt)):
            _fail()
        return report
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        if created and proof is not None:
            try:
                proof.unlink()
            except OSError:
                pass
        _fail()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-folder-map", required=True, type=Path)
    parser.add_argument("--owner-manifest-pin", required=True, type=Path)
    parser.add_argument("--owner-archive-pin", required=True, type=Path)
    parser.add_argument("--owner-receipt-pin", required=True, type=Path)
    parser.add_argument("--new-readback-root", required=True, type=Path)
    parser.add_argument("--new-private-proof-file", required=True, type=Path)
    parser.add_argument("--builds-remote", required=True)
    parser.add_argument("--manifests-remote", required=True)
    parser.add_argument("--session", required=True)
    a = parser.parse_args()
    try:
        report = admit_independent_owner_archive(
            a.private_folder_map, a.owner_manifest_pin, a.owner_archive_pin,
            a.owner_receipt_pin, a.new_readback_root, a.new_private_proof_file,
            a.builds_remote, a.manifests_remote, a.session,
        )
        if report["default_rclone_subprocess_used"] is not True:
            _fail()
    except OwnerArchiveAdmissionError:
        print("VH_MAP02_STAGE545_OWNER_CLOUD_ADMISSION_REJECTED capture_ready=0")
        return 1
    print("VH_MAP02_STAGE545_OWNER_CLOUD_ADMISSION_PASS "
          "files=%d remote_objects=5 cold_map02=0 capture_ready=0" %
          report["runtime_files"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
