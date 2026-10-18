"""Independent pre-overlay PC scratch / VRAM / PNG comparisons (synthetic)."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_export_map02_native_vram_preview import (
    CycleBoundNativeVramPreviewTests,
)
from tools.verify_map02_pc_present_rgb24 import (
    RGB24_NAME, RGB24_RECEIPT, SCHEMA, compare_native_present_rgb24,
    pc_present_bottom_up,
)
from tools.export_map02_native_vram_preview import PNG_NAME
from tools.verify_map02_native_gpu_windows import verify_native_windows
from tools.verify_map02_vram_timeline import VRAM_BYTES


class NativePcPresentConversionTests(unittest.TestCase):
    def test_bottom_up_row_order_and_rgb555_channel_replication(self):
        raw = bytearray(VRAM_BYTES)
        # top-left red (bit15 STP ignored), next green, row below blue.
        raw[0:4] = (0x801f).to_bytes(2, "little") + (0x03e0).to_bytes(2, "little")
        raw[1024 * 2:1024 * 2 + 4] = (
            (0x7c00).to_bytes(2, "little") + (0x4210).to_bytes(2, "little"))
        self.assertEqual(
            pc_present_bottom_up(raw, [0, 0, 2, 2]),
            bytes([0, 0, 255, 132, 132, 132,
                   255, 0, 0, 0, 255, 0]))

    def test_rejects_malformed_rectangle_and_wrong_vram_length(self):
        raw = bytes(VRAM_BYTES)
        for rect in ([0, 0, 0, 1], [0, 0, 1025, 1],
                     [1023, 0, 2, 1], [0, 511, 1, 2],
                     [0, 0, True, 1], [0, 0, 1]):
            with self.subTest(rect=rect), self.assertRaises(ValueError):
                pc_present_bottom_up(raw, rect)
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            pc_present_bottom_up(raw[:-1], [0, 0, 1, 1])


class PrivatePcPresentEvidenceTests(unittest.TestCase):
    def setUp(self):
        base = CycleBoundNativeVramPreviewTests(
            methodName="test_same_session_native_rectangle_outputs_private_png")
        base.setUp()
        self.addCleanup(base.doCleanups)
        self.base = base
        base.run_cycle()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rgbdir = Path(self.temp.name) / "rgb24"
        self.rgbdir.mkdir(mode=0o700)
        self.rgbfile = self.rgbdir / RGB24_NAME
        self.rgbfile.write_bytes(
            pc_present_bottom_up(base.fixture.snapshots[-1], [0, 0, 1, 1]))
        self.rgbfile.chmod(0o600)
        self.receipt = {
            "schema": "vh.map02.pc-preoverlay-capture.v1",
            "capture_session": self.base.token,
            "gpu_draw_frame": 7, "width": 1, "height": 1,
            "bytes": 3, "pixel_format": "rgb24-bottom-up",
            "movie_overlay_active": False, "hires_active": False,
            "source_pinned": True,
            "presented_window_authenticated": False,
        }
        self.save_receipt()

    def save_receipt(self):
        p = self.rgbdir / RGB24_RECEIPT
        p.write_text(json.dumps(self.receipt, sort_keys=True) + "\n")
        p.chmod(0o600)

    def check(self):
        return compare_native_present_rgb24(
            self.base.fixture.root, self.base.cycle, self.base.output,
            self.rgbdir, frame=7)

    def test_matching_preoverlay_buffer_and_png(self):
        result = self.check()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["compared_source_pixels"], 1)
        self.assertEqual(result["native_draw_pairs"], 2)
        self.assertTrue(result["bottom_up_pc_rgb24_matches_native_vram"])
        self.assertTrue(result["private_png_matches_native_vram"])
        self.assertTrue(result["same_process_rgb24_receipt_matches_cycle_nonce_and_frame"])
        self.assertEqual(result["private_pc_preoverlay_rgb24_sha256"],
                         hashlib.sha256(self.rgbfile.read_bytes()).hexdigest())
        self.assertFalse(result["external_rgb24_source_provenance_authenticated"])
        self.assertFalse(result["presented_host_window_authenticated"])
        self.assertFalse(result["original_map02_authenticated"])
        self.assertNotIn(self.base.token, json.dumps(result))
        self.assertNotIn(str(self.rgbdir), json.dumps(result))

    def test_wrong_rgb24_rejected(self):
        self.rgbfile.write_bytes(bytes([255, 0, 0]))
        with self.assertRaisesRegex(ValueError, "RGB24 buffer differs"):
            self.check()

    def test_wrong_png_rejected_independently_of_rgb24(self):
        png = self.base.output / PNG_NAME
        png.write_bytes(png.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "PNG differs"):
            self.check()

    def test_hires_present_flag_must_not_be_accepted(self):
        self.base.event["present_backend_is_hires"] = True
        self.base.save_cycle()
        with self.assertRaisesRegex(ValueError, "hi-res"):
            self.check()

    def test_different_cycle_nonce_and_draw_count_rejected(self):
        for change in (
            {"capture_session": "ef" * 16},
            {"observed_draw_primitive_count": 3},
        ):
            original = dict(self.base.event)
            self.base.event.update(change)
            self.base.save_cycle()
            with self.subTest(change=change), self.assertRaisesRegex(
                    ValueError, "capture session differs|session or DRAW count"):
                self.check()
            self.base.event = original
        self.base.save_cycle()

    def test_capture_receipt_wrong_nonce_frame_dimensions_or_mode_rejected(self):
        for changes in (
            {"capture_session": "ef" * 16},
            {"gpu_draw_frame": 8}, {"width": 2}, {"bytes": 6},
            {"movie_overlay_active": True}, {"hires_active": True},
            {"pixel_format": "rgb24-top-down"}, {"source_pinned": False},
            {"presented_window_authenticated": True}):
            original = dict(self.receipt)
            self.receipt.update(changes)
            self.save_receipt()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check()
            self.receipt = original
        self.save_receipt()

    def test_missing_or_modified_rgb_capture_receipt_rejected(self):
        (self.rgbdir / RGB24_RECEIPT).unlink()
        with self.assertRaises(ValueError):
            self.check()
        self.save_receipt()
        (self.rgbdir / RGB24_RECEIPT).write_bytes(b"invalid json")
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_clean_exit_seal_rejected(self):
        (self.base.cycle / "map02-cycle-clean-exit.jsonl").unlink()
        with self.assertRaises(ValueError):
            self.check()

    def test_hardlinked_rgb24_evidence_is_rejected(self):
        import os
        twin = Path(self.temp.name) / "foreign-hardlink"
        os.link(self.rgbfile, twin)
        with self.assertRaisesRegex(ValueError, "owner-only 0600 regular"):
            self.check()

    def test_capture_receipt_replacement_between_audits_rejected(self):
        from tools.verify_map02_pc_present_rgb24 import _private_evidence_snapshot
        original = _private_evidence_snapshot(
            self.rgbdir, RGB24_RECEIPT, max_bytes=1024)
        altered = (original[0] + b" ", original[1])
        real = _private_evidence_snapshot
        def changed(root, name, *, max_bytes):
            if name == RGB24_RECEIPT:
                self.calls += 1
                return original if self.calls == 1 else altered
            return real(root, name, max_bytes=max_bytes)
        self.calls = 0
        with patch("tools.verify_map02_pc_present_rgb24._private_evidence_snapshot",
                   side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during comparison"):
                self.check()

    def test_capture_replacement_between_audits_rejected(self):
        original = verify_native_windows(self.base.fixture.root, target_frame=7)
        altered = dict(original, native_draw_pairs=99)
        with patch("tools.verify_map02_pc_present_rgb24.verify_native_windows",
                   side_effect=(original, altered)):
            with self.assertRaisesRegex(ValueError, "changed during comparison"):
                self.check()

    def test_unlisted_private_file_and_overlapping_roots_rejected(self):
        (self.rgbdir / "unexpected.txt").write_text("x")
        with self.assertRaisesRegex(ValueError, "unexpected entries"):
            self.check()
        (self.rgbdir / "unexpected.txt").unlink()
        with self.assertRaisesRegex(ValueError, "must be separate"):
            compare_native_present_rgb24(
                self.base.fixture.root, self.base.cycle,
                self.base.output, self.base.cycle, frame=7)


if __name__ == "__main__":
    unittest.main()
