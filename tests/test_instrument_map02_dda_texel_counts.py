"""Source-mutational test for opt-in native PC GPU DDA sample counters."""
import unittest

from test_instrument_map02_raster_skips import FAKE
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_dda_texel_counts import (
    DDA_ANCHOR, FLAG, instrument_scoped_raster,
)


class NativeDdaTexelCounterGeneratorTests(unittest.TestCase):
    def test_capture_exact_executed_native_dda_samples(self):
        converted = instrument_scoped_raster(scope_raster(FAKE))
        self.assertIn("VH_Map02TexelCount(draw ? texel : 0u);", converted)
        self.assertIn("cx->rc->target == 0", converted)
        self.assertIn("vh_sample_scope_type != 2", converted)
        self.assertIn("VH_Map02TexelReset();", converted)
        self.assertIn("VH_Map02TexelFinish();", converted)
        self.assertIn("if (!bgr555) ++vh_dda_zero;", converted)
        self.assertIn("else if (bgr555 & 0x8000u) ++vh_dda_stp;", converted)
        self.assertIn("else ++vh_dda_opaque;", converted)
        self.assertIn("native-dda-ft4-texel-counts.jsonl", converted)
        self.assertIn(f"#if defined({FLAG})", converted)
        self.assertIn("VH_MAP02_DDA_TEXEL_CAP 64u", converted)
        self.assertEqual(converted.count(DDA_ANCHOR), 1)
        with self.assertRaisesRegex(ValueError, "already installed"):
            instrument_scoped_raster(converted)

    def test_reject_missing_original_decision_or_scope_lifecycle(self):
        originals = (
            FAKE.replace(DDA_ANCHOR, "/* intentional changed DDA */"),
            FAKE.replace("static unsigned short s_vram[VRAM_H][VRAM_W];",
                         "static unsigned short s_vram_wrong[VRAM_H][VRAM_W];"),
        )
        for source in originals:
            with self.subTest(source=source[:40]):
                with self.assertRaisesRegex(ValueError, "pinned source anchor|original"):
                    instrument_scoped_raster(scope_raster(source))


if __name__ == "__main__":
    unittest.main()
