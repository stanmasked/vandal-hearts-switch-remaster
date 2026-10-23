"""Stage541: fictional owner-only Drive end-to-end session (never real OAuth)."""
from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_drive_session import (
    PrivateOwnerSessionError, complete_owner_archive_session,
)
from tools.map02_linux_octoshock.private_runtime_reaudit import (
    audit_independent_readback,
)


class OwnerDriveSessionTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.full_session = self.base / "private-owner-full-session"
        self.receipt_pin = self.base / "private-trust-receipt.sha256"
        self.archive_pin = self.base / "private-trust-archive.sha256"

    def execute(self, *, session="owner541001"):
        return complete_owner_archive_session(
            self.source, self.pin, self.private_map, self.full_session,
            self.receipt_pin, "vh_builds", "vh_manifests", session,
            independent_archive_pin_output=self.archive_pin,
            invoke=self.transport,
        )

    def test_successful_complete_fictional_backup_and_independent_restore(self):
        result = self.execute()
        self.assertEqual(result["runtime_files"], 7)
        self.assertTrue(result["full_private_restore_audited"])
        self.assertFalse(result["authenticated_owner_rclone_invoked"])
        self.assertEqual(result["cloud_objects_retrieved"], 5)
        self.assertFalse(result["capture_ready"])
        self.assertTrue(self.receipt_pin.exists())
        self.assertEqual(self.receipt_pin.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.archive_pin.is_file())
        self.assertEqual(self.archive_pin.stat().st_mode & 0o777, 0o600)
        self.assertTrue(result["owner_archive_pin_written"])
        self.assertEqual(self.transport.uploads, 5)
        self.assertTrue(
            (self.full_session / "independent-reaudit/new-copy/restored/runtime/EmuHawk.exe").is_file()
        )
        # Delete original installed runtime and still restore again from
        # same fictional cloud using *independently retained* local pins.
        shutil.rmtree(self.source)
        shutil.rmtree(self.full_session)
        report = audit_independent_readback(
            self.private_map, self.pin, self.archive_pin, self.receipt_pin,
            self.base / "new-audit-after-loss", "vh_builds",
            "vh_manifests", "owner541001",
            invoke=self.transport,
        )
        self.assertFalse(report["original_runtime_required"])
        self.assertFalse(self.full_session.exists())
        self.assertEqual(report["objects_read_back"], 5)

    def test_existing_independent_archive_pin_rejected_before_transfer(self):
        self.archive_pin.write_text("0" * 64 + "\n", encoding="ascii")
        self.archive_pin.chmod(0o600)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())
        self.assertEqual(self.archive_pin.read_text(), "0" * 64 + "\n")

    def test_archive_pin_inside_session_root_rejected_early(self):
        self.archive_pin = self.full_session / "untrusted-tar.sha256"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_duplicate_pin_output_rejected_early(self):
        self.archive_pin = self.receipt_pin
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_missing_manifest_owner_pin_does_not_upload(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_bad_folder_scope_refused(self):
        self.transport.folder_ids["vh_builds"] = "fakeFolderWrongOwner"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_mutated_remote_download_never_claims_success(self):
        self.transport.corrupt_download = True
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertFalse(self.receipt_pin.exists())
        self.assertFalse(self.archive_pin.exists())

    def test_bad_session_rejected_early(self):
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute(session="../etc")
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.full_session.exists())

    def test_previous_session_directory_rejected(self):
        self.full_session.mkdir(mode=0o700)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_previous_owner_receipt_pin_rejected(self):
        self.receipt_pin.write_text("0" * 64 + "\n", encoding="ascii")
        self.receipt_pin.chmod(0o600)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_collision_with_existing_archive_object_refuses_overwrite(self):
        self.transport.remote["vh_builds"]["map02-runtime-owner541001.tar"] = b"old"
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_insecure_trust_folder_refused(self):
        self.base.chmod(0o755)
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)

    def test_owner_runtime_game_file_rejected(self):
        (self.source / "private-bios.BIN").write_bytes(b"not a real BIOS")
        with self.assertRaises(PrivateOwnerSessionError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)


if __name__ == "__main__":
    unittest.main()
