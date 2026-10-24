"""Stage542 read-only owner-preflight checks against fictional Drive transport."""
from __future__ import annotations

from pathlib import Path
import shutil
import unittest

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock.owner_session_preflight import (
    OwnerPreflightError, verify_owner_backup_readiness,
)
from tools.map02_linux_octoshock.owner_drive_session import (
    PrivateOwnerSessionError, complete_owner_archive_session,
)


class OwnerReadinessTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.new_root = self.base / "owner-stage542-new-session"
        self.new_receipt = self.base / "owner-stage542-new-receipt.sha256"

    def preflight(self, *, disk_usage=shutil.disk_usage):
        return verify_owner_backup_readiness(
            self.source, self.pin, self.private_map,
            self.new_root, self.new_receipt,
            "vh_builds", "vh_manifests", "owner542001",
            invoke=self.transport, disk_usage=disk_usage,
        )

    def test_successful_preflight_performs_no_writes(self):
        result = self.preflight()
        self.assertEqual(result["runtime_files"], 7)
        self.assertEqual(result["drive_remotes_checked"], 2)
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["capture_ready"])
        self.assertGreater(result["required_free_bytes"], 0)
        self.assertFalse(self.new_root.exists())
        self.assertFalse(self.new_receipt.exists())
        self.assertEqual(self.transport.uploads, 0)

    def test_insufficient_space_rejected_without_writes(self):
        class LowDisk:
            free = 0
        with self.assertRaises(OwnerPreflightError):
            self.preflight(disk_usage=lambda _: LowDisk())
        self.assertFalse(self.new_root.exists())
        self.assertEqual(self.transport.uploads, 0)

    def test_corrupted_owner_manifest_pin_refused(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(OwnerPreflightError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)

    def test_cloud_receipt_name_collision_refused(self):
        self.transport.remote["vh_manifests"][
            "map02-runtime-owner542001.receipt.json"] = b"prior"
        with self.assertRaises(OwnerPreflightError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)

    def test_wrong_drive_folder_scope_refused(self):
        self.transport.folder_ids["vh_builds"] = "fictionalWrongRoot00001"
        with self.assertRaises(OwnerPreflightError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)

    def test_original_game_image_rejected(self):
        folder = self.source / "nested"
        folder.mkdir(mode=0o700)
        (folder / "original.BIN").write_bytes(b"fictional")
        with self.assertRaises(OwnerPreflightError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)

    def test_existing_session_folder_refused(self):
        self.new_root.mkdir(mode=0o700)
        with self.assertRaises(OwnerPreflightError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)

    def test_folder_map_change_during_remote_checks_rejected(self):
        from unittest.mock import patch
        import tools.map02_linux_octoshock.owner_session_preflight as module

        original = module._folder_map
        calls = 0

        def changed_mapping(path, root):
            nonlocal calls
            calls += 1
            result = original(path, root)
            if calls == 1:
                return result
            return ("fictionalReplacementBuildsRoot", result[1])

        with patch.object(module, "_folder_map", side_effect=changed_mapping):
            with self.assertRaises(OwnerPreflightError):
                self.preflight()
        self.assertEqual(calls, 2)
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.new_root.exists())
        self.assertFalse(self.new_receipt.exists())

    def test_trusted_pin_change_during_remote_checks_rejected(self):
        changed = False

        def mutating_transport(argv):
            nonlocal changed
            result = self.transport(argv)
            if not changed and argv[0] == "lsf":
                self.pin.write_text("0" * 64 + "\n", encoding="ascii")
                self.pin.chmod(0o600)
                changed = True
            return result

        with self.assertRaises(OwnerPreflightError):
            verify_owner_backup_readiness(
                self.source, self.pin, self.private_map,
                self.new_root, self.new_receipt,
                "vh_builds", "vh_manifests", "owner542001",
                invoke=mutating_transport, disk_usage=shutil.disk_usage,
            )
        self.assertTrue(changed)
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.new_root.exists())
        self.assertFalse(self.new_receipt.exists())

    def test_runtime_manifest_change_during_remote_checks_rejected(self):
        changed = False
        manifest = self.source / "map02-owner-runtime-manifest.json"

        def mutating_transport(argv):
            nonlocal changed
            result = self.transport(argv)
            if not changed and argv[0] == "lsf":
                manifest.write_bytes(manifest.read_bytes() + b" ")
                changed = True
            return result

        with self.assertRaises(OwnerPreflightError):
            verify_owner_backup_readiness(
                self.source, self.pin, self.private_map,
                self.new_root, self.new_receipt,
                "vh_builds", "vh_manifests", "owner542001",
                invoke=mutating_transport, disk_usage=shutil.disk_usage,
            )
        self.assertTrue(changed)
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.new_root.exists())
        self.assertFalse(self.new_receipt.exists())

    def test_full_session_also_requires_preflight_space_gate(self):
        from unittest.mock import patch
        class LowDisk:
            free = 0
        with patch(
            "tools.map02_linux_octoshock.owner_session_preflight.shutil.disk_usage",
            return_value=LowDisk(),
        ):
            with self.assertRaises(PrivateOwnerSessionError):
                complete_owner_archive_session(
                    self.source, self.pin, self.private_map,
                    self.new_root, self.new_receipt,
                    "vh_builds", "vh_manifests", "owner542001",
                    invoke=self.transport,
                )
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse(self.new_root.exists())


if __name__ == "__main__":
    unittest.main()
