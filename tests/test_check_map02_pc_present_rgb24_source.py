"""Synthetic regression tests for pinned upstream PC RGB conversion anchors."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.check_map02_pc_present_rgb24_source import (
    ANCHORS, BLOB_SHA1, check_source,
)


class PcPresentSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "pc_gpu_window.c"
        self.source.write_text("\n".join(ANCHORS) + "\n")

    def test_valid_pinned_source_conversion_and_overlay_order(self):
        with patch("tools.check_map02_pc_present_rgb24_source.git_blob_sha1",
                   return_value=BLOB_SHA1):
            result = check_source(self.source)
        self.assertTrue(result["verified_bgr555_to_bottom_up_rgb24_before_overlays"])
        self.assertFalse(result["original_map02_frame_authenticated"])

    def test_source_sha_drift_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "source blob has drifted"):
            check_source(self.source)

    def test_duplicate_or_reordered_conversion_is_rejected(self):
        with patch("tools.check_map02_pc_present_rgb24_source.git_blob_sha1",
                   return_value=BLOB_SHA1):
            original = self.source.read_text()
            self.source.write_text(original + ANCHORS[-1] + "\n")
            with self.assertRaisesRegex(ValueError, "missing/duplicated"):
                check_source(self.source)
            self.source.write_text("\n".join(reversed(ANCHORS)) + "\n")
            with self.assertRaisesRegex(ValueError, "order changed"):
                check_source(self.source)


if __name__ == "__main__":
    unittest.main()
