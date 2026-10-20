"""Synthetic postcapture pipeline tests; NO original game assets or retail ELF."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from tests.test_verify_map02_final_pc_frame_join import (
    SyntheticFinalPcFrameJoinTests,
)
from tools.finalize_map02_private_capture import (
    SCHEMA, finalize_private_capture,
)
from tools.publish_map02_cd_bound_witness import MANIFEST
from tools.export_map02_native_vram_preview import PNG_NAME


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class PrivatePostcaptureCompletionTests(unittest.TestCase):
    def setUp(self):
        f = SyntheticFinalPcFrameJoinTests(
            methodName="test_original_process_cd_gpu_and_native_rgb24_png_join")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fixture = f
        self.source = f.source
        self.preview = f.base.output
        self.rgb = f.fixture.rgbdir
        self.verify_cd = patch(
            "tools.finalize_map02_private_capture.verify_published_original_cd_witness",
            side_effect=self._verified_cd)
        self.verify_mock = self.verify_cd.start()
        self.addCleanup(self.verify_cd.stop)

    def _verified_cd(self, *args, **kwargs):
        return {
            "private_map02_cd_final_sha256":
                sha((self.source / MANIFEST).read_bytes())
        }

    def finish(self, *, source=None, preview=None, rgb=None,
               complete_missing=False):
        f = self.fixture
        return finalize_private_capture(
            source or f.source, f.base.fixture.root, f.scoped, f.handoff,
            f.base.cycle, preview or self.preview, rgb or self.rgb,
            Path("/no-owned-retail-image"),
            Path("/no-private-pc-source"),
            Path("/no-local-game-elf"),
            frame=7, complete_missing=complete_missing)

    def test_existing_artifacts_read_only_and_no_game_bytes(self):
        old_png = (self.preview / PNG_NAME).read_bytes()
        old_cd = (self.source / MANIFEST).read_bytes()
        result = self.finish()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertTrue(result["independently_verified_cd_gpu_process_and_rgb24_png"])
        self.assertFalse(result["private_cd_witness_created"])
        self.assertFalse(result["private_native_vram_png_created"])
        self.assertEqual(result["verified_draw_primitives"], 2)
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["game_bytes_uploaded"])
        self.assertEqual(self.verify_mock.call_count, 2)
        self.assertEqual((self.preview / PNG_NAME).read_bytes(), old_png)
        self.assertEqual((self.source / MANIFEST).read_bytes(), old_cd)
        output = json.dumps(result)
        for secret in (self.fixture.token, str(self.source), str(self.preview)):
            self.assertNotIn(secret, output)

    def test_missing_preview_requires_explicit_opt_in(self):
        png = self.preview / PNG_NAME
        png.unlink()
        with self.assertRaisesRegex(ValueError, "explicit completion"):
            self.finish()
        self.verify_mock.assert_not_called()
        self.assertFalse(png.exists())

    def test_generate_private_png_from_native_vram_then_join(self):
        png = self.preview / PNG_NAME
        png.unlink()
        report = self.finish(complete_missing=True)
        self.assertTrue(report["private_native_vram_png_created"])
        self.assertFalse(report["private_cd_witness_created"])
        self.assertTrue(png.is_file())
        self.assertEqual(png.stat().st_mode & 0o777, 0o600)
        self.assertEqual(report["native_vram_png_sha256"], sha(png.read_bytes()))

    def test_missing_cd_witness_requires_opt_in_before_png_write(self):
        (self.source / MANIFEST).unlink()
        (self.preview / PNG_NAME).unlink()
        with self.assertRaisesRegex(ValueError, "explicit completion"):
            self.finish()
        self.assertFalse((self.preview / PNG_NAME).exists())
        self.verify_mock.assert_not_called()

    def test_explicit_cd_witness_publication_then_final_join(self):
        cd = self.source / MANIFEST
        cd.unlink()
        def publish(*args, **kwargs):
            p = self.fixture.write(self.source, MANIFEST,
                                   self.fixture.original)
            return {"private_map02_cd_final_sha256": sha(p.read_bytes())}
        with patch(
                "tools.finalize_map02_private_capture.publish_original_cd_witness",
                side_effect=publish) as published:
            result = self.finish(complete_missing=True)
        published.assert_called_once()
        self.assertTrue(result["private_cd_witness_created"])
        self.assertFalse(result["private_native_vram_png_created"])
        self.assertEqual(result["source_cd_gpu_process_witness_sha256"],
                         sha(cd.read_bytes()))

    def test_bad_pc_rgb24_nonce_blocks_output_publication(self):
        f = self.fixture
        f.fixture.receipt["capture_session"] = "ff" * 16
        f.fixture.save_receipt()
        (self.source / MANIFEST).unlink()
        (self.preview / PNG_NAME).unlink()
        with patch(
                "tools.finalize_map02_private_capture.publish_original_cd_witness"
        ) as publish:
            with self.assertRaisesRegex(ValueError, "nonce differs"):
                self.finish(complete_missing=True)
        publish.assert_not_called()
        self.assertFalse((self.preview / PNG_NAME).exists())

    def test_swapped_process_rgb24_digest_rejected_before_writes(self):
        f = self.fixture
        f.process["pc_preoverlay_image_sha256"] = "f" * 64
        f.write_fixture()
        (self.preview / PNG_NAME).unlink()
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.finish(complete_missing=True)
        self.assertFalse((self.preview / PNG_NAME).exists())

    def test_legacy_process_without_v3_rejected(self):
        f = self.fixture
        f.process["schema"] = "vh.map02.local-executed-process.v2"
        for key in ("pc_preoverlay_image_sha256",
                    "pc_preoverlay_receipt_sha256",
                    "pc_preoverlay_capture_session_bound"):
            f.process.pop(key)
        f.write_fixture()
        with self.assertRaisesRegex(ValueError, "unbound"):
            self.finish()
        self.verify_mock.assert_not_called()

    def test_overlapping_and_non_private_roots_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.finish(preview=self.source)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.finish(rgb=self.preview)
        self.preview.chmod(0o755)
        self.addCleanup(self.preview.chmod, 0o700)
        with self.assertRaises(ValueError):
            self.finish()

    def test_unexpected_png_directory_entry_or_symlink_rejected(self):
        foreign = self.preview / "unrelated.txt"
        foreign.write_text("x")
        with self.assertRaisesRegex(ValueError, "unexpected or linked"):
            self.finish()
        foreign.unlink()
        path = self.preview / PNG_NAME
        path.unlink()
        path.symlink_to(Path("/untrusted/file"))
        with self.assertRaisesRegex(ValueError, "unexpected or linked"):
            self.finish(complete_missing=True)

    def test_failed_cd_publication_does_not_export_png(self):
        (self.source / MANIFEST).unlink()
        (self.preview / PNG_NAME).unlink()
        with patch(
                "tools.finalize_map02_private_capture.publish_original_cd_witness",
                side_effect=ValueError("independent CD proof unavailable")):
            with self.assertRaisesRegex(ValueError, "CD proof unavailable"):
                self.finish(complete_missing=True)
        self.assertFalse((self.preview / PNG_NAME).exists())

    def test_cd_readback_digest_mismatch_blocks_png(self):
        (self.preview / PNG_NAME).unlink()
        with patch(
                "tools.finalize_map02_private_capture.verify_published_original_cd_witness",
                return_value={"private_map02_cd_final_sha256": "f" * 64}):
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                self.finish(complete_missing=True)
        # The extra PNG may be generated, but no success is returned and
        # its pixels never leave the private preview folder.
        self.assertTrue((self.preview / PNG_NAME).is_file())

    def test_reject_nonboolean_opt_in(self):
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            finalize_private_capture(
                self.source, self.fixture.base.fixture.root,
                self.fixture.scoped, self.fixture.handoff,
                self.fixture.base.cycle, self.preview, self.rgb,
                Path("/no-image"), Path("/no-src"), Path("/no-elf"),
                frame=7, complete_missing="yes")


if __name__ == "__main__":
    unittest.main()
