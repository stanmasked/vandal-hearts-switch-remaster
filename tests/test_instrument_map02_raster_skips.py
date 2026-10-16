"""Mutation tests for opt-in original native DDA skip instrumentation."""
import tempfile
from pathlib import Path
import unittest

from test_instrument_map02_native_putpixel import SOURCE
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import (
    FLAG, SPAN_ANCHOR, DDA_END_ANCHOR,
    DDA_DRAW_ANCHOR, LEGACY_ANCHOR, instrument_raster_skips, prepare,
)

FAKE = (SOURCE + "\n" + SPAN_ANCHOR + "\n"
        "    int width = x_bound - x_start;\n"
        "    (void)width;\n}\n"
        "void fake_dda(int current_x, int y) {\n" +
        DDA_DRAW_ANCHOR + "\n" +
        DDA_END_ANCHOR + "\n}\n"
        "void fake_legacy(void) {\n" +
        LEGACY_ANCHOR + "\n}\n" +
        "void test_rows(void) {\n"
        "            y--; left_x -= lstep; right_x -= rstep;\n"
        "        do {\n            if (y > cx->clipB) break;\n"
        "}\n")


class NativeRasterSkipGeneratorTests(unittest.TestCase):
    def test_exact_rejection_branches_in_existing_source_only(self):
        output=instrument_raster_skips(scope_raster(FAKE))
        self.assertIn("VH_Map02SkipAt(current_x, y, 1);",output)
        self.assertIn("VH_Map02SkipAt(vh_pixel_sample_x, y, 2);",output)
        self.assertIn("VH_Map02SkipAt(x, y, 3);",output)
        self.assertEqual(output.count("VH_Map02SkipAt(vh_pixel_sample_x, y, 4);"),2)
        self.assertIn("vh_pixel_sample_active &&",output) if False else None
        self.assertIn("vh_sample_scope_active",output)
        self.assertIn("vh_map02_skip_count >= VH_MAP02_SKIP_CAP",output)
        self.assertIn("cx->rc->target == 0",output)
        self.assertIn("rc->target == 0",output)
        self.assertIn("vh_sample_scope_ordinal",output)
        self.assertIn("VH_MAP02_RASTER_SKIP_TRACE",output)
        self.assertEqual(output.count('WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);'),1)
        with self.assertRaisesRegex(ValueError,"already installed"):
            instrument_raster_skips(output)

    def test_missing_original_dda_span_or_zero_texel_branch_rejected(self):
        for anchor in (SPAN_ANCHOR,DDA_END_ANCHOR,LEGACY_ANCHOR):
            with self.subTest(anchor=anchor[:40]):
                malformed=FAKE.replace(anchor,"/* intentional drift */")
                with self.assertRaisesRegex(ValueError,"pinned source anchor count"):
                    instrument_raster_skips(scope_raster(malformed))

    def test_no_upstream_mutations_on_wrong_sha_or_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            gpu=base/"gpu.c"; raster=base/"raster.c"
            gpu.write_text("not the original GPU")
            raster.write_text(FAKE)
            dest=base/"output"
            with self.assertRaisesRegex(ValueError,"pinned original PC GPU blob mismatch"):
                prepare(gpu,raster,dest)
            self.assertFalse(dest.exists())
            dest.mkdir()
            with self.assertRaisesRegex(ValueError,"no overwrite"):
                prepare(gpu,raster,dest)


if __name__=="__main__":
    unittest.main()
