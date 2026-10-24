"""Stage550: full persistent owner pipeline tests, entirely fictional cloud."""
from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from tools.map02_linux_octoshock import owner_persistent_backup as pipeline
from tools.map02_linux_octoshock.owner_persistent_backup import (
    OwnerPersistentBackupError, publish_existing_trusted_runtime,
)


class PersistentOwnerPipelineTests(unittest.TestCase):
    def setUp(self):
        Stage537TransportTests.setUp(self)
        self.work = self.base / "durable-owner-work"
        self.trust = self.base / "external-owner-trust"
        self.work.mkdir(mode=0o700)
        self.trust.mkdir(mode=0o700)
        self.session = "owner550001"

    def execute(self, *, session=None):
        return publish_existing_trusted_runtime(
            self.source, self.pin, self.private_map,
            self.work, self.trust,
            "vh_builds", "vh_manifests",
            self.session if session is None else session,
            invoke=self.transport,
        )

    def test_full_three_source_free_readbacks_with_invented_drive(self):
        result = self.execute()
        self.assertEqual(result["runtime_files"], 7)
        self.assertTrue(result["all_three_five_object_readbacks_verified"])
        self.assertTrue(result["sealed_owner_admission_verified"])
        self.assertFalse(result["authentic_owner_backup_claim_permitted"])
        self.assertFalse(result["capture_ready"])
        self.assertEqual(result["cold_map02_launches"], 0)
        self.assertEqual(self.transport.uploads, 5)
        for item in ("archive.sha256", "receipt.sha256", "admission.json",
                     "admission.sha256"):
            self.assertTrue((self.trust / (self.session + "-" + item)).is_file())
        self.assertTrue((self.work / (self.session +
            "-preboot-readback/restored/runtime/EmuHawk.exe")).is_file())
        self.assertTrue(self.source.is_dir())  # the originals were not deleted

    def test_missing_independently_trusted_manifest_fails_before_upload(self):
        self.pin.unlink()
        with self.assertRaises(OwnerPersistentBackupError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_mismatching_independent_manifest_rejected_before_upload(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        with self.assertRaises(OwnerPersistentBackupError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_all_outputs_reserved_before_any_upload(self):
        previous = self.trust / (self.session + "-admission.sha256")
        previous.write_text("0" * 64 + "\n", encoding="ascii")
        previous.chmod(0o600)
        with self.assertRaises(OwnerPersistentBackupError):
            self.execute()
        self.assertEqual(self.transport.uploads, 0)
        self.assertFalse((self.work / (self.session + "-transfer")).exists())
        self.assertEqual(previous.read_text(), "0" * 64 + "\n")

    def test_nested_trust_and_work_folders_rejected(self):
        inner = self.work / "nested-trust"
        inner.mkdir(mode=0o700)
        with self.assertRaises(OwnerPersistentBackupError):
            publish_existing_trusted_runtime(
                self.source, self.pin, self.private_map,
                self.work, inner, "vh_builds", "vh_manifests",
                self.session, invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)

    def test_symlinked_work_root_refused(self):
        alias = self.base / "alias"
        alias.symlink_to(self.work, target_is_directory=True)
        with self.assertRaises(OwnerPersistentBackupError):
            publish_existing_trusted_runtime(
                self.source, self.pin, self.private_map,
                alias, self.trust, "vh_builds", "vh_manifests",
                self.session, invoke=self.transport,
            )
        self.assertEqual(self.transport.uploads, 0)

    def test_fake_rclone_never_promoted_to_real_backup(self):
        result = self.execute()
        self.assertTrue(result["all_three_five_object_readbacks_verified"])
        self.assertFalse(result["real_scoped_rclone_subprocess_used"])
        self.assertFalse(result["authentic_owner_backup_claim_permitted"])

    def test_interruption_after_first_admission_is_not_final_success(self):
        def fail_final_gate(*a, **k):
            raise RuntimeError("fictional final independent restore failed")
        with patch.object(pipeline, "audit_capture_backup_gate",
                          side_effect=fail_final_gate):
            with self.assertRaises(OwnerPersistentBackupError):
                self.execute()
        self.assertEqual(self.transport.uploads, 5)
        self.assertTrue((self.trust / (self.session + "-admission.json")).exists())
        self.assertFalse((self.work / (self.session + "-preboot-readback")).exists())

    def test_reuse_of_session_refused_without_any_new_upload(self):
        self.execute()
        count = self.transport.uploads
        with self.assertRaises(OwnerPersistentBackupError):
            self.execute()
        self.assertEqual(self.transport.uploads, count)

    def test_prepare_never_generates_external_sha_pin(self):
        with patch.object(pipeline, "build_and_stage", return_value={
            "game_media_used": False, "psx_capture_ready": False,
        }) as build:
            self.assertFalse((self.trust / "owner-sha.sha256").exists())
            record = pipeline.build_and_stage(self.base / "private-new-runtime")
            self.assertEqual(record["game_media_used"], False)
            build.assert_called_once()
            self.assertEqual(list(self.trust.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
