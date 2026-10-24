"""Stage545 independent admission test uses only fictional in-memory Drive."""
from __future__ import annotations

import json
import shutil
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_drive_session import complete_owner_archive_session
from tools.map02_linux_octoshock.owner_archive_admission import (
    OwnerArchiveAdmissionError, admit_independent_owner_archive,
)


class OwnerArchiveAdmissionTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.session_root = self.base / "ephemeral-owner-session"
        self.receipt = self.base / "trusted-receipt.sha256"
        self.archive = self.base / "trusted-archive.sha256"
        self.proof = self.base / "new-private-admission.json"
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
            self.session, invoke=self.transport,
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
        self.assertEqual(json.loads(self.proof.read_text())["owner_pins"][
            "owner_archive_sha256"], self.archive.read_text().strip())
        self.assertTrue((self.readback / "restored/runtime/EmuHawk.exe").is_file())

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
