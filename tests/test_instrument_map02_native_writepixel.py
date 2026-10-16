"""Regress native-only opt-in WritePixel insertion and fail-closed anchors."""
import unittest
from tools.instrument_map02_native_writepixel import instrument, ANCHOR, DECL_ANCHOR


class InstrumentNativeWritePixelTests(unittest.TestCase):
    def setUp(self):
        self.source = "header\n" + DECL_ANCHOR + "\n" + ANCHOR + "\nfooter\n"

    def test_single_native_vram_hook(self):
        patched = instrument(self.source)
        self.assertIn("vh_map02_native_writepixel(x, y, before, c", patched)
        self.assertIn("#ifdef VH_MAP02_PIXEL_PROBE", patched)
        self.assertIn("#else\n" + ANCHOR.splitlines()[1] + "\n#endif", patched)
        self.assertEqual(patched.count("vh_map02_native_writepixel("), 2)
        self.assertIn("if (x < 0 || x >= VRAM_W", patched)

    def test_rejects_source_drift_duplicate_and_reinstrumentation(self):
        for broken in (self.source.replace("VRAM_W", "VRAM_WIDTH"),
                       self.source + ANCHOR,
                       self.source.replace(DECL_ANCHOR, ""),
                       instrument(self.source)):
            with self.subTest(broken=broken[:40]), self.assertRaises(ValueError):
                instrument(broken)


if __name__ == "__main__":
    unittest.main()
