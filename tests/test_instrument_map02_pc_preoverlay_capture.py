"""Guard the exact native BGR555 -> RGB24 -> OSD source tap location."""
import unittest
from unittest.mock import patch

from tools.check_map02_pc_present_rgb24_source import ANCHORS, BLOB_SHA1
from tools.instrument_map02_pc_preoverlay_capture import instrument


class PcPreoverlaySourceTapTests(unittest.TestCase):
    def setUp(self):
        self.source = "\n".join(
            "    " + s if s.startswith("/* Langpack movie subtitles:") else s
            for s in ANCHORS) + "\n"

    def run_instrument(self, source):
        with patch("tools.instrument_map02_pc_preoverlay_capture.git_blob_sha1",
                   return_value=BLOB_SHA1):
            return instrument(source)

    def test_callback_after_rgb_loop_before_any_subtitles_or_osd(self):
        compiled = self.run_instrument(self.source)
        self.assertEqual(compiled.count("vh_map02_pc_capture_preoverlay("), 1)
        self.assertLess(compiled.index("out[2] = (unsigned char)"),
                        compiled.index("vh_map02_pc_capture_preoverlay("))
        self.assertLess(compiled.index("vh_map02_pc_capture_preoverlay("),
                        compiled.index("/* Langpack movie subtitles:"))
        self.assertIn("s_drawFrame, s_rgbaScratch", compiled)
        self.assertIn("HiresActive()", compiled)
        self.assertIn("(s_movieOverlay || s_movieOverlayRGB)", compiled)
        self.assertIn("abort();", compiled)

    def test_pinned_source_drift_missing_duplicate_and_moved_anchor_fail(self):
        with self.assertRaisesRegex(ValueError, "source blob differs"):
            instrument(self.source)
        with self.assertRaisesRegex(ValueError, "anchors drifted"):
            self.run_instrument(self.source.replace(ANCHORS[6], ""))
        with self.assertRaisesRegex(ValueError, "anchors drifted"):
            self.run_instrument(self.source + ANCHORS[6])
        with self.assertRaisesRegex(ValueError, "anchors drifted"):
            self.run_instrument(self.source.replace(
                "    /* Langpack movie subtitles:", "/* altered */"))


if __name__ == "__main__":
    unittest.main()
