"""Stage550: full persistent owner pipeline tests, entirely fictional cloud."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from test_map02_linux_octoshock_private_drive import Stage537TransportTests
from test_map02_linux_octoshock_archive_readback import private_mock_runtime
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

    def preflight(self, *, session=None):
        return pipeline.preflight_existing_trusted_runtime(
            self.source, self.pin, self.private_map,
            self.work, self.trust, "vh_builds", "vh_manifests",
            self.session if session is None else session,
            invoke=self.transport,
        )

    def test_stage600_readonly_preflight_all_seven_outputs_and_remotes(self):
        before_work = list(self.work.iterdir())
        before_trust = list(self.trust.iterdir())
        result = self.preflight()
        self.assertEqual(result["schema"], "vh.map02.owner-persistent-preflight.v1")
        self.assertEqual(result["runtime_files"], 7)
        self.assertEqual(result["output_paths_available"], 7)
        self.assertEqual(result["drive_remotes_checked"], 2)
        self.assertTrue(result["trusted_manifest_pin_verified"])
        self.assertFalse(result["persistent_host_checked"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["remote_upload_performed"])
        self.assertFalse(result["owner_backup_proven"])
        self.assertFalse(result["capture_ready"])
        self.assertEqual(list(self.work.iterdir()), before_work)
        self.assertEqual(list(self.trust.iterdir()), before_trust)
        self.assertEqual(self.transport.uploads, 0)
        # A successful read-only snapshot does NOT reserve the names.
        publish = self.execute()
        self.assertTrue(publish["all_three_five_object_readbacks_verified"])
        self.assertEqual(self.transport.uploads, 5)

    def test_stage600_preflight_blocks_every_preexisting_output_path(self):
        names = (
            (self.work, self.session + "-transfer"),
            (self.work, self.session + "-admission-readback"),
            (self.work, self.session + "-preboot-readback"),
            (self.trust, self.session + "-archive.sha256"),
            (self.trust, self.session + "-receipt.sha256"),
            (self.trust, self.session + "-admission.json"),
            (self.trust, self.session + "-admission.sha256"),
        )
        for parent, filename in names:
            with self.subTest(output=filename):
                target = parent / filename
                target.write_text("existing owner evidence", encoding="ascii")
                with self.assertRaises(OwnerPersistentBackupError):
                    self.preflight()
                self.assertEqual(
                    target.read_text(encoding="ascii"), "existing owner evidence",
                )
                self.assertEqual(self.transport.uploads, 0)
                target.unlink()
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_stage600_preflight_rejects_bad_trust_before_remote_access(self):
        self.pin.write_text("0" * 64 + "\n", encoding="ascii")
        previous = self.transport.uploads
        with self.assertRaises(OwnerPersistentBackupError):
            self.preflight()
        self.assertEqual(self.transport.uploads, previous)
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_stage600_preflight_rejects_remote_name_collision(self):
        self.transport.remote["vh_builds"][
            "map02-runtime-" + self.session + ".tar"
        ] = b"fictional existing cloud artifact"
        with self.assertRaises(OwnerPersistentBackupError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_stage600_preflight_rejects_quarantine_without_remote_mutation(self):
        quarantine = self.trust / ".map02-pin-cleanup-stage600"
        quarantine.mkdir(mode=0o700)
        payload = quarantine / "payload"
        payload.write_text("forensic data", encoding="ascii")
        payload.chmod(0o600)
        with self.assertRaises(OwnerPersistentBackupError):
            self.preflight()
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(payload.read_text(encoding="ascii"), "forensic data")
        self.assertEqual(list(self.trust.iterdir()), [quarantine])

    def test_stage600_preflight_blocks_new_reservation_during_remote_reads(self):
        late = self.trust / (self.session + "-admission.sha256")
        real_readiness = pipeline.verify_owner_backup_readiness

        def inject_after_readiness(*args, **kwargs):
            checked = real_readiness(*args, **kwargs)
            late.write_text("new concurrent reservation", encoding="ascii")
            return checked

        with patch.object(
            pipeline, "verify_owner_backup_readiness",
            side_effect=inject_after_readiness,
        ):
            with self.assertRaises(OwnerPersistentBackupError):
                self.preflight()
        self.assertEqual(late.read_text(encoding="ascii"), "new concurrent reservation")
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.work.iterdir()), [])

    def test_stage600_preflight_real_host_gate_before_remote_reads(self):
        # Force only this module's classification to real. No OAuth or host
        # interrogation is performed: mock the persistent-host boundary.
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(
                pipeline, "verify_persistent_private_host",
                side_effect=ValueError("fictional temporary storage"),
            ) as verify:
                with self.assertRaises(OwnerPersistentBackupError):
                    self.preflight()
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.trust.iterdir()), [])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_stage600_preflight_real_host_identity_recheck_after_remote_reads(self):
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(pipeline, "verify_persistent_private_host"):
                with patch.object(
                    pipeline, "snapshot_private_path_identity",
                    return_value=(("fictional", 1, 2, 3, 4),),
                ):
                    with patch.object(
                        pipeline, "require_unchanged_persistent_host",
                        side_effect=ValueError("fictional mount changed"),
                    ) as recheck:
                        with self.assertRaises(OwnerPersistentBackupError):
                            self.preflight()
        self.assertEqual(recheck.call_count, 1)
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.trust.iterdir()), [])
        self.assertEqual(list(self.work.iterdir()), [])

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

    def test_real_transport_gates_all_trust_input_parents_before_upload(self):
        # Patch only this module's real-transport identity to activate
        # the owner-host gate. The fake cloud must not be invoked.
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(
                pipeline, "verify_persistent_private_host",
                side_effect=ValueError("fictional ephemeral source pin mount"),
            ) as check:
                with self.assertRaises(OwnerPersistentBackupError):
                    self.execute()
        expected = [self.source, self.work, self.trust, self.base]
        self.assertEqual(check.call_args.args[0], expected)
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_real_transport_rejects_ephemeral_folder_map_before_upload(self):
        external = self.base / "config-vault"
        external.mkdir(mode=0o700)
        folder_map = external / "folder-map.json"
        folder_map.write_bytes(self.private_map.read_bytes())
        folder_map.chmod(0o600)
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(
                pipeline, "verify_persistent_private_host",
                side_effect=ValueError("fictional config vault is temporary"),
            ) as check:
                with self.assertRaises(OwnerPersistentBackupError):
                    publish_existing_trusted_runtime(
                        self.source, self.pin, folder_map, self.work,
                        self.trust, "vh_builds", "vh_manifests",
                        self.session, invoke=self.transport,
                    )
        self.assertIn(external, check.call_args.args[0])
        self.assertEqual(self.transport.uploads, 0)

    def test_real_transport_recheck_rejects_changed_host_before_upload(self):
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(pipeline, "verify_persistent_private_host"):
                with patch.object(pipeline, "snapshot_private_path_identity",
                                  return_value=(("fictional", 1, 2, 3, 4),)):
                    with patch.object(
                        pipeline, "require_unchanged_persistent_host",
                        side_effect=ValueError("fictional directory was swapped"),
                    ) as recheck:
                        with self.assertRaises(OwnerPersistentBackupError):
                            self.execute()
        self.assertEqual(recheck.call_count, 1)
        self.assertEqual(self.transport.uploads, 0)
        self.assertEqual(list(self.work.iterdir()), [])
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_real_transport_recheck_after_transfer_rejects_before_admission(self):
        with patch.object(pipeline, "_call_rclone", self.transport):
            with patch.object(pipeline, "verify_persistent_private_host"):
                with patch.object(pipeline, "snapshot_private_path_identity",
                                  return_value=(("fictional", 1, 2, 3, 4),)):
                    with patch.object(
                        pipeline, "require_unchanged_persistent_host",
                        side_effect=[{}, ValueError("fictional device changed")],
                    ) as recheck:
                        with self.assertRaises(OwnerPersistentBackupError):
                            self.execute()
        self.assertEqual(recheck.call_count, 2)
        self.assertEqual(self.transport.uploads, 5)
        self.assertFalse((self.trust / (self.session + "-admission.json")).exists())

    def test_prepare_recheck_denies_success_after_host_replacement(self):
        with patch("sys.argv", [
            "owner_persistent_backup", "prepare", "--new-runtime-root",
            str(self.base / "future-runtime"),
        ]):
            with patch.object(pipeline, "verify_persistent_private_host"):
                with patch.object(pipeline, "snapshot_private_path_identity",
                                  return_value=(("fictional", 1, 2, 3, 4),)):
                    with patch.object(pipeline, "build_and_stage", return_value={
                        "game_media_used": False, "psx_capture_ready": False,
                    }) as build:
                        with patch.object(
                            pipeline, "require_unchanged_persistent_host",
                            side_effect=ValueError("fictional parent inode changed"),
                        ):
                            self.assertEqual(pipeline.main(), 1)
        build.assert_called_once()

    def _prepare_with_invented_runtime(self, *, corrupt=False, omit=False):
        promoted = self.base / "stage599-promoted-no-media-runtime"

        def build_installed_runtime(root, *, keep_workdir=False):
            self.assertEqual(Path(root), promoted)
            if not omit:
                private_mock_runtime(promoted)
                if corrupt:
                    (promoted / "EmuHawk.exe").write_bytes(b"tampered promoted file")
            return {"game_media_used": False, "psx_capture_ready": False}

        with patch("sys.argv", [
            "owner_persistent_backup", "prepare", "--new-runtime-root",
            str(promoted),
        ]), patch.object(
            pipeline, "verify_persistent_private_host",
        ), patch.object(
            pipeline, "snapshot_private_path_identity",
            return_value=(("synthetic", 1, 2, 3, 4),),
        ), patch.object(
            pipeline, "require_unchanged_persistent_host",
        ) as recheck, patch.object(
            pipeline, "build_and_stage",
            side_effect=build_installed_runtime,
        ) as build:
            result = pipeline.main()
        build.assert_called_once()
        return result, promoted, recheck.call_count

    def test_prepare_independently_verifies_promoted_no_media_runtime(self):
        result, root, rechecks = self._prepare_with_invented_runtime()
        self.assertEqual(result, 0)
        self.assertTrue(root.is_dir())
        self.assertEqual(rechecks, 2)
        self.assertFalse((self.trust / "owner-sha.sha256").exists())
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_prepare_rejects_corrupt_file_after_promotion(self):
        result, root, rechecks = self._prepare_with_invented_runtime(corrupt=True)
        self.assertEqual(result, 1)
        self.assertTrue(root.is_dir())  # preserve failed runtime for investigation
        self.assertEqual(rechecks, 1)
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_prepare_rejects_missing_runtime_after_reported_build_success(self):
        result, root, rechecks = self._prepare_with_invented_runtime(omit=True)
        self.assertEqual(result, 1)
        self.assertFalse(root.exists())
        self.assertEqual(rechecks, 1)
        self.assertEqual(list(self.trust.iterdir()), [])

    def test_prepare_rejects_host_change_after_independent_verification(self):
        promoted = self.base / "stage599-verified-host-replacement"

        def build_installed_runtime(root, *, keep_workdir=False):
            private_mock_runtime(promoted)
            return {"game_media_used": False, "psx_capture_ready": False}

        with patch("sys.argv", [
            "owner_persistent_backup", "prepare", "--new-runtime-root",
            str(promoted),
        ]), patch.object(
            pipeline, "verify_persistent_private_host",
        ), patch.object(
            pipeline, "snapshot_private_path_identity",
            return_value=(("synthetic", 1, 2, 3, 4),),
        ), patch.object(
            pipeline, "require_unchanged_persistent_host",
            side_effect=[{}, ValueError("fictional host swapped after verification")],
        ) as recheck, patch.object(
            pipeline, "build_and_stage", side_effect=build_installed_runtime,
        ):
            self.assertEqual(pipeline.main(), 1)
        self.assertEqual(recheck.call_count, 2)
        self.assertEqual(list(self.trust.iterdir()), [])

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
