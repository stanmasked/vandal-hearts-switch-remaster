"""Asset-free final source/GTE/GPU/CD/observed-process SHA witness tests.

The expensive source/GTE compiled witness is stubbed by the reused GPU
fixture; the kernel process executable verifier is explicitly mocked HERE
only. Real native VRAM join and 12-sector raw disc CRC/SHA checks execute.
No retail bytes are ever used or uploaded.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
import zlib

from tests.test_publish_map02_window_scoped_witness import (
    FinalWindowScopedWitnessTests,
)
from tests.test_check_map02_owned_disc_extent import (
    OwnedMap02DiscExtentTests,
)
from tools.publish_map02_cd_bound_witness import (
    MANIFEST, SCHEMA, _validate, publish_original_cd_witness,
    verify_published_original_cd_witness,
)
from tools.publish_map02_window_scoped_witness import (
    MANIFEST as GPU_FINAL,
    publish_window_scoped_witness,
)
from tools.verify_map02_window_scoped_join import (
    CD_READ, verify_window_scoped_join,
)
from tools.map02_verified_process_launch import RECEIPT


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class OriginalCdBoundFinalWitnessTests(unittest.TestCase):
    def setUp(self):
        gpu = FinalWindowScopedWitnessTests(
            methodName="test_publish_recheck_all_four_streams_and_source_bound_sha")
        gpu.setUp()
        self.addCleanup(gpu.doCleanups)
        cd = OwnedMap02DiscExtentTests(
            methodName="test_private_original_map02_extent_with_12_real_sector_frames")
        cd.setUp()
        self.addCleanup(cd.doCleanups)
        self.gpu, self.cd = gpu, cd
        self.source, self.native, self.scoped = gpu.source, gpu.native, gpu.scoped
        self.image, self.upstream = cd.image, cd.upstream
        self.handoff = self.native.parent / "observed-handoff"
        self.handoff.mkdir(mode=0o700)
        self.binary = self.handoff / "synthetic-verified-pc"
        self.binary.write_bytes(b"synthetic pc executable fingerprint only")
        self.binary.chmod(0o700)

        crc = 0
        with self.image.open("rb") as fd:
            for lba in range(0x1bcc, 0x1bcc + 12):
                fd.seek(lba * 2352 + 24)
                crc = zlib.crc32(fd.read(2048), crc)
        self.cd_receipt = {
            "schema": "vh.map02.original-cd-read.v1",
            "capture_session": "bc" * 16,
            "source": "original-CdRead-and-ContinueLoadingCdFile",
            "cdf": "CDF_M_MAP02_PRS",
            "lba": 0x1bcc, "sectors": 12, "bytes": 24576,
            "raw_user_crc32": f"{crc:08x}",
            "returned_user_crc32": f"{crc:08x}",
            "loader_completed": True,
        }
        self.stage_cd()
        publish_window_scoped_witness(
            self.source, self.native, self.scoped, frame=7)
        window = verify_window_scoped_join(
            self.native, self.scoped, target_frame=7)
        self.process_meta = {
            "gpu_draw_frame": 7,
            "game_image_fd_observed": True,
            "capture_session_sha256": window["capture_session_sha256"],
            "native_window_all_files_sha256":
                window["all_native_window_file_bytes_sha256"],
        }
        self.stage_process()
        process_patch = patch(
            "tools.publish_map02_cd_bound_witness.verify_observed_process",
            side_effect=self.process_report)
        process_patch.start()
        self.addCleanup(process_patch.stop)

    def stage_cd(self):
        target = self.scoped / CD_READ
        target.write_bytes(
            (json.dumps(self.cd_receipt, sort_keys=True,
                        separators=(",", ":")) + "\n").encode())
        target.chmod(0o600)

    def stage_process(self):
        target = self.handoff / RECEIPT
        target.write_bytes(
            (json.dumps(self.process_meta, sort_keys=True) + "\n").encode())
        target.chmod(0o600)

    def process_report(self, *args, **kwargs):
        return {"private_process_receipt_sha256":
                    sha((self.handoff / RECEIPT).read_bytes()),
                "game_image_fd_observed": True}

    def publish(self):
        return publish_original_cd_witness(
            self.source, self.native, self.scoped, self.handoff,
            self.image, self.upstream, self.binary, frame=7)

    def verify(self):
        return verify_published_original_cd_witness(
            self.source, self.native, self.scoped, self.handoff,
            self.image, self.upstream, self.binary, frame=7)

    def test_publishes_private_sealed_source_gpu_cd_and_kernel_evidence(self):
        result = self.publish()
        target = self.source / MANIFEST
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertTrue(result["same_process_original_cd_and_gpu_source_bound"])
        self.assertFalse(result["original_map02_rendering_proven"])
        payload = json.loads(target.read_bytes())
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["verified_gpu_gte_witness_sha256"],
                         sha((self.source / GPU_FINAL).read_bytes()))
        self.assertEqual(payload["observed_process_receipt_sha256"],
                         sha((self.handoff / RECEIPT).read_bytes()))
        self.assertEqual(payload["original_cd_read_receipt_sha256"],
                         sha((self.scoped / CD_READ).read_bytes()))
        self.assertEqual(payload["owned_disc_image_sha256"],
                         sha(self.image.read_bytes()))
        self.assertEqual(payload["capture_session_sha256"],
                         self.process_meta["capture_session_sha256"])
        self.assertEqual(self.verify(), result)
        self.assertFalse(list(self.source.glob(".*.tmp")))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.publish()

    def test_disallows_no_actual_cd_read_or_uncompleted_original_loader(self):
        (self.scoped / CD_READ).unlink()
        with self.assertRaisesRegex(ValueError, "missing actual"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.stage_cd()
        self.cd_receipt["loader_completed"] = False
        self.stage_cd()
        with self.assertRaises(ValueError):
            self.publish()

    def test_detects_same_run_process_nonce_mismatch(self):
        self.process_meta["capture_session_sha256"] = "b" * 64
        self.stage_process()
        with self.assertRaisesRegex(ValueError, "same-run"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())

    def test_refuses_unobserved_cd_file_opened_status(self):
        self.process_meta["game_image_fd_observed"] = False
        self.stage_process()
        with self.assertRaisesRegex(ValueError, "same-run"):
            self.publish()

    def test_cd_payload_changed_while_vram_and_source_unchanged(self):
        self.cd_receipt["raw_user_crc32"] = "deadbeef"
        self.cd_receipt["returned_user_crc32"] = "deadbeef"
        self.stage_cd()
        with self.assertRaisesRegex(ValueError, "payload differs"):
            self.publish()
        self.assertFalse((self.source / MANIFEST).exists())

    def test_changed_owned_disc_after_original_cd_witness_is_detected(self):
        self.publish()
        with self.image.open("r+b") as fd:
            fd.seek(0x1bcc * 2352 + 24)
            fd.write(b"changed!")
        with self.assertRaises(ValueError):
            self.verify()

    def test_corrupted_process_and_old_gpu_manifests_are_rejected(self):
        self.publish()
        p = self.handoff / RECEIPT
        p.write_bytes(p.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.verify()
        self.stage_process()
        with self.source.joinpath(GPU_FINAL).open("ab") as fd:
            fd.write(b"\n")
        with self.assertRaises(ValueError):
            self.verify()

    def test_final_audit_rejects_identical_bytes_source_or_process_inode_swap(self):
        for folder, filename in (
                (self.source, GPU_FINAL), (self.handoff, RECEIPT)):
            with self.subTest(file=filename):
                target = folder / filename
                backup = folder.parent / ("original-" + folder.name + "-" + filename)
                original = target.read_bytes()
                initial_inode = target.stat().st_ino

                def same_bytes_swap(*args, **kwargs):
                    target.replace(backup)
                    target.write_bytes(original)
                    target.chmod(0o600)
                    self.assertNotEqual(initial_inode, target.stat().st_ino)
                    return self.process_report(*args, **kwargs)

                try:
                    with patch(
                            "tools.publish_map02_cd_bound_witness.verify_observed_process",
                            side_effect=same_bytes_swap):
                        with self.assertRaisesRegex(
                                ValueError, "evidence identity changed during final CD audit"):
                            self.publish()
                finally:
                    if backup.exists():
                        target.unlink(missing_ok=True)
                        backup.replace(target)
                self.assertFalse((self.source / MANIFEST).exists())
                self.assertEqual(initial_inode, target.stat().st_ino)

    def test_final_manifest_recheck_rejects_identical_bytes_inode_swap(self):
        self.publish()
        target = self.source / MANIFEST
        original = target.read_bytes()
        saved = self.source.parent / "original-final-cd-gpu-manifest"
        payload = json.loads(original)
        initial_inode = target.stat().st_ino

        def switch_while_reverifying(*args, **kwargs):
            target.replace(saved)
            target.write_bytes(original)
            target.chmod(0o600)
            self.assertNotEqual(initial_inode, target.stat().st_ino)
            return payload

        try:
            with patch("tools.publish_map02_cd_bound_witness._verified",
                       side_effect=switch_while_reverifying):
                with self.assertRaisesRegex(ValueError, "witness identity changed"):
                    self.verify()
        finally:
            if saved.exists():
                target.unlink(missing_ok=True)
                saved.replace(target)
        self.assertEqual(initial_inode, target.stat().st_ino)

    def test_final_manifest_rejects_hardlinks_and_world_readable_mode(self):
        self.publish()
        target = self.source / MANIFEST
        alias = self.source.parent / "original-final-witness-hardlink"
        os.link(target, alias)
        try:
            with self.assertRaisesRegex(ValueError, "owner-only 0600"):
                self.verify()
        finally:
            alias.unlink()
        target.chmod(0o644)
        try:
            with self.assertRaisesRegex(ValueError, "owner-only 0600"):
                self.verify()
        finally:
            target.chmod(0o600)

    def test_manifest_cannot_claim_ps1_or_full_map_rendering(self):
        self.publish()
        path = self.source / MANIFEST
        saved = json.loads(path.read_bytes())
        for name in ("original_map02_rendering_proven",
                     "full_original_gameplay_authenticated",
                     "physical_ps1_equivalence_proven"):
            bad = dict(saved, **{name: True})
            path.write_text(json.dumps(bad) + "\n")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "overstated"):
                self.verify()

    def test_second_verification_changed_aborts_publication(self):
        import tools.publish_map02_cd_bound_witness as module
        first = module._verified(
            self.source, self.native, self.scoped, self.handoff,
            self.image, self.upstream, self.binary, frame=7, compiler="gcc")
        mutated = dict(first, capture_session_sha256="f" * 64)
        with patch("tools.publish_map02_cd_bound_witness._verified",
                   side_effect=[first, mutated]):
            with self.assertRaisesRegex(ValueError, "changed before publication"):
                self.publish()
        self.assertFalse((self.source / MANIFEST).exists())
        self.assertFalse(list(self.source.glob(".*.tmp")))

    def test_rejects_aliased_source_and_capture_directories(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            publish_original_cd_witness(
                self.source, self.native, self.scoped, self.source,
                self.image, self.upstream, self.binary, frame=7)

    def test_strict_schema_rejects_missing_keys_and_invalid_hashes(self):
        with self.assertRaises(ValueError):
            _validate({"schema": SCHEMA})
        self.publish()
        obj = json.loads((self.source / MANIFEST).read_bytes())
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            _validate(dict(obj, original_cd_read_receipt_sha256="0"))
        with self.assertRaises(ValueError):
            _validate(dict(obj, original_map02_sectors=13))


if __name__ == "__main__":
    unittest.main()
