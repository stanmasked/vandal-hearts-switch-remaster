"""Synthetic in-process pre-overlay receipt binding, no retail image."""
import hashlib
import json
import unittest
from pathlib import Path

from tests.test_verify_map02_pc_present_rgb24 import PrivatePcPresentEvidenceTests
from tools.verify_map02_pc_preoverlay_session import verify_preoverlay_session
from tools.verify_map02_pc_present_rgb24 import RGB24_RECEIPT, RGB24_NAME


class PcPreoverlaySessionTests(unittest.TestCase):
    def setUp(self):
        fixture = PrivatePcPresentEvidenceTests(
            methodName="test_matching_preoverlay_buffer_and_png")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.expect_nonce = hashlib.sha256(fixture.base.token.encode("ascii")).hexdigest()

    def check(self, **kwargs):
        return verify_preoverlay_session(
            self.fixture.rgbdir, self.fixture.base.cycle, frame=7,
            expected_session_sha256=self.expect_nonce, **kwargs)

    def test_valid_private_session_receipt_and_rgb24_hash(self):
        out = self.check()
        self.assertTrue(out["same_process_capture_nonce_checked"])
        self.assertEqual(out["native_rect"], [0, 0, 1, 1])
        self.assertEqual(out["gpu_draw_frame"], 7)
        self.assertEqual(out["pc_rgb24_image_sha256"],
                         hashlib.sha256(self.fixture.rgbfile.read_bytes()).hexdigest())
        self.assertFalse(out["original_gameplay_authenticated"])
        self.assertNotIn(str(self.fixture.rgbdir), json.dumps(out))

    def test_wrong_capture_session_and_early_process_nonce_mismatch(self):
        with self.assertRaisesRegex(ValueError, "cycle nonce"):
            verify_preoverlay_session(
                self.fixture.rgbdir, self.fixture.base.cycle, frame=7,
                expected_session_sha256="f" * 64)
        self.fixture.receipt["capture_session"] = "ff" * 16
        self.fixture.save_receipt()
        with self.assertRaisesRegex(ValueError, "nonce differs"):
            self.check()

    def test_capture_dimensions_or_bad_mode_rejected(self):
        for changes in ({"bytes": 4}, {"width": 2},
                        {"gpu_draw_frame": 8},
                        {"source_pinned": False},
                        {"presented_window_authenticated": True}):
            old = dict(self.fixture.receipt)
            self.fixture.receipt.update(changes)
            self.fixture.save_receipt()
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.check()
            self.fixture.receipt = old
        self.fixture.save_receipt()

    def test_hires_cycle_rejected_and_rgb_image_size_mismatch(self):
        self.fixture.base.event["present_backend_is_hires"] = True
        self.fixture.base.save_cycle()
        with self.assertRaisesRegex(ValueError, "cycle nonce or backend"):
            self.check()
        self.fixture.base.event["present_backend_is_hires"] = False
        self.fixture.base.save_cycle()
        self.fixture.rgbfile.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "payload length differs"):
            self.check()

    def test_unsealed_receipt_or_unexpected_directory_file_rejected(self):
        (self.fixture.rgbdir / RGB24_RECEIPT).unlink()
        with self.assertRaises(ValueError):
            self.check()
        self.fixture.save_receipt()
        (self.fixture.rgbdir / "unexpected").write_text("foreign")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.check()

    def test_hardlinked_receipt_rejected(self):
        import os
        twin = Path(self.fixture.rgbdir.parent) / "foreign-receipt-hardlink"
        os.link(self.fixture.rgbdir / RGB24_RECEIPT, twin)
        self.addCleanup(twin.unlink)
        with self.assertRaises(ValueError):
            self.check()

    def test_invalid_expected_session_digest_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid expected"):
            verify_preoverlay_session(
                self.fixture.rgbdir, self.fixture.base.cycle, frame=7,
                expected_session_sha256=True)


if __name__ == "__main__":
    unittest.main()
