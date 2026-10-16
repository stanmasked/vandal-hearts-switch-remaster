"""Synthetic opt-in native PC PutPixel observer and source-drift tests."""
import tempfile
from pathlib import Path
import unittest

from tools.instrument_map02_native_putpixel import (
    INSERT_AFTER, CALL, FLAG, instrument, prepare,
)

SOURCE = """
#include <stdio.h>
#include <stdlib.h>
#define VRAM_W 1024
#define VRAM_H 512
static unsigned short s_vram[VRAM_H][VRAM_W];
static int AccurateEnabled(void) { return 1; }
static void WritePixel(unsigned short *px, int x, int y,
                       unsigned short c, int abr, int semiTrans, int textured) {
    (void)x; (void)y; (void)abr; (void)semiTrans; (void)textured;
    *px=c;
}
static void PutPixel(int x, int y, unsigned short c, int abr,
                     int semiTrans, int textured) {
    WritePixel(&s_vram[y][x], x, y, c, abr, semiTrans, textured);
}
"""

class NativePixelProbeGenerationTests(unittest.TestCase):
    def test_single_observer_never_changes_original_write_call(self):
        p=instrument(SOURCE)
        self.assertIn("VH_PixelSampleRecord(x, y, vh_before, c, s_vram[y][x]",p)
        self.assertEqual(p.count(CALL.strip()),1)
        self.assertIn("#if defined(VH_MAP02_PUTPIXEL_SAMPLE)",p)
        self.assertIn("static int AccurateEnabled(void);",p)
        self.assertIn("vh_pixel_sample_count < VH_PIXEL_SAMPLE_MAX",p)
        self.assertIn("vh_pixel_sample_dir[0] != '/'",p)
        self.assertIn("endx == vx",p)
        self.assertIn("x < 0 || x >= VRAM_W",p)
        self.assertIn("if (fclose(file) != 0) return;",p)
        self.assertEqual(p.count('VH_MAP02_PUTPIXEL_SAMPLE'), 3)
        self.assertTrue(SOURCE in SOURCE)
        with self.assertRaisesRegex(ValueError,"already installed"):
            instrument(p)

    def test_missing_or_duplicated_original_source_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,"one anchor"):
            instrument(SOURCE.replace(INSERT_AFTER,"/* altered */"))
        with self.assertRaisesRegex(ValueError,"one anchor"):
            instrument(SOURCE.replace(CALL,"/* altered */"))
        with self.assertRaisesRegex(ValueError,"one anchor"):
            instrument(SOURCE.replace(CALL,CALL+"\n"+CALL))

    def test_wrong_pinned_source_and_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/"pc_raster.c"
            out=Path(d)/"output.c"
            src.write_text(SOURCE)
            with self.assertRaisesRegex(ValueError,"not the pinned source"):
                prepare(src,out)
            self.assertFalse(out.exists())
            out.write_text("preserve")
            with self.assertRaisesRegex(ValueError,"destination exists"):
                prepare(src,out)
            self.assertEqual(out.read_text(),"preserve")


if __name__ == "__main__":
    unittest.main()
