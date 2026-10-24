"""Stage548: owner-live backup gate tested against fake Drive only."""
from __future__ import annotations

import json
import shutil
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_archive_admission import admit_independent_owner_archive
from tools.map02_linux_octoshock.owner_drive_session import complete_owner_archive_session
from tools.map02_linux_octoshock.owner_capture_backup_gate import (
    OwnerCaptureBackupGateError, audit_capture_backup_gate,
)


class OwnerCaptureBackupGateTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.session = "owner548001"
        self.session_root = self.base / "owner-transfer-disposable"
        self.receipt = self.base / "owner-receipt.sha256"
        self.archive = self.base / "owner-tar.sha256"
        self.first_restore = self.base / "previous-owner-admission-readback"
        self.proof = self.base / "sealed-owner-admission.json"
        self.proof_pin = self.base / "sealed-owner-admission.sha256"
        self.next_restore = self.base / "fresh-pre-capture-readback"
        transfer = complete_owner_archive_session(
            self.source, self.pin, self.private_map, self.session_root,
            self.receipt, "vh_builds", "vh_manifests", self.session,
            independent_archive_pin_output=self.archive, invoke=self.transport,
        )
        self.assertTrue(transfer["owner_archive_pin_written"])
        shutil.rmtree(self.source)
        shutil.rmtree(self.session_root)
        admission = admit_independent_owner_archive(
            self.private_map, self.pin, self.archive, self.receipt,
            self.first_restore, self.proof,
            "vh_builds", "vh_manifests", self.session,
            independent_proof_pin_output=self.proof_pin,
            invoke=self.transport,
        )
        self.assertTrue(admission["independent_proof_sha_pin_created"])
        shutil.rmtree(self.first_restore)

    def check(self, *, session=None):
        return audit_capture_backup_gate(
            self.private_map, self.pin, self.archive, self.receipt,
            self.proof, self.proof_pin, self.next_restore,
            "vh_builds", "vh_manifests",
            self.session if session is None else session,
            invoke=self.transport,
        )

    def test_source_free_second_restore_synthetic_gate_never_capture_ready(self):
        report = self.check()
        self.assertTrue(report["previous_admission_seal_verified"])
        self.assertEqual(report["runtime_files"], 7)
        self.assertTrue(report["synthetic_transport_used"])
        self.assertFalse(report["owner_backup_proven_against_trusted_pins"])
        self.assertFalse(report["capture_ready"])
        self.assertEqual(report["cold_launches_verified"], 0)
        self.assertTrue((self.next_restore / "restored/runtime/EmuHawk.exe").is_file())

    def test_tampered_prior_admission_proof_refused_before_cloud_readback(self):
        self.proof.write_text(self.proof.read_text() + "forged", encoding="utf-8")
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check()
        self.assertFalse(self.next_restore.exists())

    def test_wrong_prior_session_refused(self):
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check(session="wrong548001")
        self.assertFalse(self.next_restore.exists())

    def test_changed_owner_tar_pin_refused(self):
        self.archive.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check()
        self.assertFalse(self.next_restore.exists())

    def test_cloud_archive_corrupted_since_admission_refused(self):
        self.transport.remote["vh_builds"][
            "map02-runtime-owner548001.tar"] += b"CHANGED"
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check()

    def test_cloud_receipt_corrupted_since_admission_refused(self):
        self.transport.remote["vh_manifests"][
            "map02-runtime-owner548001.receipt.json"] += b"CHANGED"
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check()

    def test_previous_readback_not_accepted_as_fresh(self):
        self.next_restore.mkdir(mode=0o700)
        with self.assertRaises(OwnerCaptureBackupGateError):
            self.check()


if __name__ == "__main__":
    unittest.main()
