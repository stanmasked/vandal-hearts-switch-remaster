"""Stage545 independent admission test uses only fictional in-memory Drive."""
from __future__ import annotations

import json
import shutil
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_drive_session import complete_owner_archive_session
from tools.map02_linux_octoshock.owner_archive_admission import (
    OwnerArchiveAdmissionError, admit_independent_owner_archive,
    verify_sealed_owner_admission,
)


class OwnerArchiveAdmissionTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.session_root = self.base / "ephemeral-owner-session"
        self.receipt = self.base / "trusted-receipt.sha256"
        self.archive = self.base / "trusted-archive.sha256"
        self.proof = self.base / "new-private-admission.json"
        self.proof_pin = self.base / "new-private-admission.sha256"
        self.readback = self.base / "fresh-cloud-audit"
        self.session = "owner545001"
        result = complete_owner_archive_session(
            self.source, self.pin, self.private_map, self.session_root,
            self.receipt, "vh_builds", "vh_manifests", self.session,
            independent_archive_pin_output=self.archive,
            invoke=self.transport,
        )
        self.assertTrue(result["owner_archive_pin_written"])
        shutil.rmtree(self.source)
        shutil.rmtree(self.session_root)

    def run_admission(self):
        return admit_independent_owner_archive(
            self.private_map, self.pin, self.archive, self.receipt,
            self.readback, self.proof, "vh_builds", "vh_manifests",
            self.session, independent_proof_pin_output=self.proof_pin,
            invoke=self.transport,
        )

    def test_restore_after_source_and_disposable_session_are_lost(self):
        report = self.run_admission()
        self.assertEqual(report["runtime_files"], 7)
        self.assertEqual(report["downloaded_remote_objects"], 5)
        self.assertTrue(report["fake_transport_injected"])
        self.assertFalse(report["default_rclone_subprocess_used"])
        self.assertFalse(report["authentic_map02_cold_runs_verified"])
        self.assertFalse(report["capture_ready"])
        self.assertTrue(self.proof.is_file())
        self.assertEqual(self.proof.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.proof_pin.stat().st_mode & 0o777, 0o600)
        check = verify_sealed_owner_admission(self.proof, self.proof_pin)
        self.assertTrue(check["sealed_proof_sha_verified"])
        self.assertTrue(check["fake_transport_recorded"])
        self.assertFalse(check["original_gameplay_verified"])
        self.assertEqual(json.loads(self.proof.read_text())["owner_pins"][
            "owner_archive_sha256"], self.archive.read_text().strip())
        self.assertTrue((self.readback / "restored/runtime/EmuHawk.exe").is_file())

    def test_modified_proof_rejected_against_independent_sha(self):
        self.run_admission()
        self.proof.write_text(self.proof.read_text() + "FORGED", encoding="utf-8")
        with self.assertRaises(OwnerArchiveAdmissionError):
            verify_sealed_owner_admission(self.proof, self.proof_pin)

    def test_modified_proof_pin_rejected(self):
        self.run_admission()
        self.proof_pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(OwnerArchiveAdmissionError):
            verify_sealed_owner_admission(self.proof, self.proof_pin)

    def test_fake_transport_not_promotable_to_real(self):
        self.run_admission()
        with self.assertRaises(OwnerArchiveAdmissionError):
            verify_sealed_owner_admission(
                self.proof, self.proof_pin, require_real_transport=True,
            )

    def test_existing_proof_pin_refused_without_overwrite(self):
        self.proof_pin.write_text("0" * 64 + "\n", encoding="ascii")
        self.proof_pin.chmod(0o600)
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())
        self.assertEqual(self.proof_pin.read_text(), "0" * 64 + "\n")

    def test_pin_inside_readback_refused_early(self):
        self.proof_pin = self.readback / "inadmissible.sha256"
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.readback.exists())
        self.assertFalse(self.proof.exists())

    def test_identical_report_and_pin_refused_early(self):
        self.proof_pin = self.proof
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())

    def test_corrupted_cloud_archive_rejects_without_proof(self):
        self.transport.remote["vh_builds"]["map02-runtime-owner545001.tar"] += b"forged"
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())

    def test_corrupted_cloud_receipt_rejects_without_proof(self):
        self.transport.remote["vh_manifests"]["map02-runtime-owner545001.receipt.json"] += b"forged"
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())

    def test_tampered_offline_archive_pin_rejects_without_proof(self):
        self.archive.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())

    def test_wrong_remote_scope_refuses_without_proof(self):
        self.transport.folder_ids["vh_manifests"] = "fictionalWrongFolder00001"
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())

    def test_prior_proof_not_overwritten(self):
        self.proof.write_text("older-provenance-record", encoding="ascii")
        self.proof.chmod(0o600)
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertEqual(self.proof.read_text(), "older-provenance-record")

    def test_proof_inside_disposable_readback_rejected(self):
        self.proof = self.readback / "inadmissible.json"
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.readback.exists())

    def test_reused_readback_directory_rejected(self):
        self.readback.mkdir(mode=0o700)
        with self.assertRaises(OwnerArchiveAdmissionError):
            self.run_admission()
        self.assertFalse(self.proof.exists())


if __name__ == "__main__":
    unittest.main()
