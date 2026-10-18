"""Synthetic independent final MAP02 CD/GPU/process ↔ RGB24/PNG witness join.

The full expensive original-disc witness is mocked here; native GPU/VRAM,
RGB24/PNG, cycle receipt, process/CD-manifest schemas and inode checks are real.
No proprietary game material or authenticated retail execution is supplied.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_verify_map02_pc_present_rgb24 import (
    PrivatePcPresentEvidenceTests,
)
from tools.publish_map02_cd_bound_witness import MANIFEST
from tools.map02_verified_process_launch import RECEIPT
from tools.verify_map02_window_scoped_join import CD_READ
from tools.verify_map02_final_pc_frame_join import (
    SCHEMA, verify_final_pc_frame,
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SyntheticFinalPcFrameJoinTests(unittest.TestCase):
    def setUp(self):
        fixture = PrivatePcPresentEvidenceTests(
            methodName="test_matching_preoverlay_buffer_and_png")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.base = fixture.base
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.source, self.scoped, self.handoff = (
            root / "source", root / "scoped", root / "handoff")
        for p in (self.source, self.scoped, self.handoff):
            p.mkdir(mode=0o700)
        self.token = self.base.token
        self.session = sha(self.token.encode("ascii"))
        self.cd = {
            "schema": "vh.map02.original-cd-read.v2",
            "capture_session": self.token, "source":
            "original-CdRead-and-ContinueLoadingCdFile",
            "cdf": "CDF_M_MAP02_PRS", "lba": 0x1bcc, "sectors": 12,
            "bytes": 24576, "raw_user_crc32": "a" * 8,
            "returned_user_crc32": "a" * 8,
            "raw_user_sha256": "a" * 64,
            "returned_user_sha256": "a" * 64,
            "loader_completed": True,
        }
        self.process = {
            "schema": "vh.map02.local-executed-process.v2",
            "gpu_draw_frame": 7,
            "local_plan_sha256": "f" * 64,
            "kernel_observed_executable_sha256": "a" * 64,
            "kernel_executable_device": 1, "kernel_executable_inode": 1,
            "observed_pid": 321, "pc_process_exit_code": 0,
            "capture_session_sha256": self.session,
            "game_image_fd_observed": True,
            "kernel_game_image_device": 1, "kernel_game_image_inode": 2,
            "native_window_all_files_sha256": "b" * 64,
            "selected_pixel_x": 0, "selected_pixel_y": 0,
            "kernel_executable_matched_plan": True,
            "same_process_gpu_scoped_nonce_checked": True,
            "game_image_consumption_proven": False,
            "retail_gameplay_authenticated": False,
            "physical_ps1_equivalence_proven": False,
        }
        self.original = {
            "schema": "vh.map02.native-gte-gpu-cd-process-witness.v1",
            "gpu_draw_frame": 7, "original_map02_lba": 0x1bcc,
            "original_map02_sectors": 12,
            "verified_gpu_gte_witness_sha256": "1" * 64,
            "observed_process_receipt_sha256": "",
            "original_cd_read_receipt_sha256": "2" * 64,
            "owned_disc_image_sha256": "3" * 64,
            "original_map02_user_data_sha256": "4" * 64,
            "capture_session_sha256": self.session,
            "source_gte_gpu_verified": True,
            "kernel_pc_executable_observed": True,
            "original_cd_loader_completion_observed": True,
            "original_cd_payload_matches_owned_image": True,
            "same_process_all_streams": True,
            "full_original_gameplay_authenticated": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
        }
        self.write_fixture()
        # ONLY the existing very expensive retail-disc/GTE/OS verifier
        # is mocked; all new cryptographic joins and RGB comparison run.
        self.patch = patch(
            "tools.verify_map02_cycle_cd_gpu_join.verify_published_original_cd_witness",
            side_effect=lambda *a, **kw: {
                "private_map02_cd_final_sha256": sha(
                    (self.source / MANIFEST).read_bytes())
            })
        self.mock = self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, directory, filename, record):
        path = directory / filename
        path.write_bytes((json.dumps(record, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode())
        path.chmod(0o600)
        return path

    def write_fixture(self):
        self.write(self.scoped, CD_READ, self.cd)
        process = self.write(self.handoff, RECEIPT, self.process)
        self.original["observed_process_receipt_sha256"] = sha(
            process.read_bytes())
        self.write(self.source, MANIFEST, self.original)

    def check(self, **kw):
        return verify_final_pc_frame(
            self.source, self.base.fixture.root, self.scoped, self.handoff,
            self.base.cycle, self.base.output, self.fixture.rgbdir,
            Path("/no-owned-private-retail-image"),
            Path("/no-real-retail-upstream"), Path("/no-original-elf"),
            frame=7, **kw)

    def test_original_process_cd_gpu_and_native_rgb24_png_join(self):
        report = self.check()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertTrue(report["independent_full_cd_gpu_process_witness_verified"])
        self.assertTrue(report["pc_preoverlay_rgb24_and_native_vram_png_match"])
        self.assertEqual(report["capture_session_sha256"], self.session)
        self.assertEqual(report["matched_native_draw_primitives"], 2)
        self.assertEqual(report["native_display_source_rect"], [0, 0, 1, 1])
        self.assertFalse(report["presented_host_window_authenticated"])
        self.assertFalse(report["original_map02_rendering_proven"])
        self.assertFalse(report["full_original_gameplay_authenticated"])
        self.assertNotIn(self.token, json.dumps(report))
        self.assertNotIn(str(self.fixture.rgbdir), json.dumps(report))
        self.mock.assert_called_once()

    def test_changed_process_witness_digest_rejected_early(self):
        self.original["observed_process_receipt_sha256"] = "a" * 64
        self.write(self.source, MANIFEST, self.original)
        with self.assertRaisesRegex(ValueError, "not bound to this process"):
            self.check()
        self.mock.assert_not_called()

    def test_wrong_process_frame_and_nonce_rejected_early(self):
        for replacement in (
            {"gpu_draw_frame": 8},
            {"capture_session_sha256": "e" * 64},
        ):
            old = dict(self.process)
            self.process.update(replacement)
            self.write_fixture()
            with self.subTest(changed=replacement), self.assertRaisesRegex(
                    ValueError, "not bound to this process"):
                self.check()
            self.process = old
        self.write_fixture()

    def test_overstated_original_process_authentication_rejected(self):
        self.process["retail_gameplay_authenticated"] = True
        self.write_fixture()
        with self.assertRaises(ValueError):
            self.check()
        self.mock.assert_not_called()

    def test_rgb24_mismatch_and_hires_mode_rejected(self):
        self.fixture.rgbfile.write_bytes(b"\xff\x00\x00")
        with self.assertRaisesRegex(ValueError, "RGB24 buffer differs"):
            self.check()
        self.fixture.rgbfile.write_bytes(b"\x10\x00\x00")
        self.base.event["present_backend_is_hires"] = True
        self.base.save_cycle()
        with self.assertRaises(ValueError):
            self.check()

    def test_changed_original_manifest_after_nested_verifier_is_rejected(self):
        original = self.source / MANIFEST
        def changed(*args, **kw):
            original.write_bytes(original.read_bytes() + b"changed")
            return {"private_map02_cd_final_sha256": sha(original.read_bytes())}
        with patch(
                "tools.verify_map02_cycle_cd_gpu_join.verify_published_original_cd_witness",
                side_effect=changed):
            with self.assertRaises(ValueError):
                self.check()

    def test_aliased_and_nested_capture_roots_rejected(self):
        with self.assertRaisesRegex(ValueError, "roots overlap"):
            verify_final_pc_frame(
                self.source, self.base.fixture.root, self.scoped, self.handoff,
                self.base.cycle, self.fixture.rgbdir, self.fixture.rgbdir,
                Path("/no-image"), Path("/no-upstream"), Path("/no-elf"),
                frame=7)
        nested = self.handoff / "nested"
        nested.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "roots overlap"):
            verify_final_pc_frame(
                self.source, self.base.fixture.root, self.scoped, self.handoff,
                self.base.cycle, nested, self.fixture.rgbdir,
                Path("/no-image"), Path("/no-upstream"), Path("/no-elf"),
                frame=7)

    def test_rgb_receipt_hardlink_or_changed_png_rejected(self):
        import os
        path = self.fixture.rgbdir / "map02-pc-present-preoverlay-receipt.jsonl"
        hardlink = Path(self.tmp.name) / "linked-rgb-receipt"
        os.link(path, hardlink)
        with self.assertRaises(ValueError):
            self.check()
        hardlink.unlink()
        png = self.base.output / "map02-native-vram-preview.png"
        png.write_bytes(png.read_bytes() + b"modified")
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
