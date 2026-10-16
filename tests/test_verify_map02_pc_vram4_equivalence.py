"""Mutation gates for exact pinned PC VRAM4 arithmetic extraction."""
import unittest
from tools.verify_map02_pc_vram4_equivalence import (
    ANCHORS, FUNCTIONS, extract_sample_functions,
)

SOURCE = """
void TPageOrigin(int tpage, int *x, int *y, int *tp) {
    *x = (tpage & 0xF) * 64;
    *y = ((tpage >> 4) & 1) * 256;
    *tp = (tpage >> 7) & 3;
}
static unsigned short SampleTexture(const RenderCtx *rc, int tpage, int clut, int u, int v) {
    int clutX = (clut & 0x3F) * 16;
    int clutY = (clut >> 6) & 0x1FF;
    u = (u & ~(rc->twMaskX * 8)) | ((rc->twOffX & rc->twMaskX) * 8);
    v = (v & ~(rc->twMaskY * 8)) | ((rc->twOffY & rc->twMaskY) * 8);
    unsigned short hw = s_vram[tpY + v][tpX + u / 4];
    int index = (hw >> ((u % 4) * 4)) & 0xF;
    raw = s_vram[clutY][clutX + index];
}
"""
class Map02Vram4PinnedSourceTests(unittest.TestCase):
    def test_extract_requires_all_source_expressions(self):
        extracted=extract_sample_functions(SOURCE)
        for anchor in ANCHORS:
            self.assertIn(anchor,extracted)

    def test_changed_math_refused(self):
        for token in ANCHORS:
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError,"arithmetic changed"):
                    extract_sample_functions(SOURCE.replace(token,"changed();"))
    def test_changed_function_bounds_refused(self):
        for token in FUNCTIONS:
            with self.subTest(token=token):
                with self.assertRaisesRegex(ValueError,"function boundary changed"):
                    extract_sample_functions(SOURCE.replace(token,"changed() {"))
        with self.assertRaisesRegex(ValueError,"function boundary changed"):
            extract_sample_functions(SOURCE+SOURCE)

if __name__=="__main__":
    unittest.main()
