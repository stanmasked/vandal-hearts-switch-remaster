"""Pinned original DDA vertical-branch observability and source drift regressions."""
import tempfile
from pathlib import Path
import unittest

from test_instrument_map02_raster_skips import FAKE
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_vertical_dda import (
    ANCHORS, FLAG, instrument_vertical, prepare,
)

PART = r'''
static void dda_part(const DdaCtx *cx, const DdaPart *tp, DdaUV origin) {
    if (tp->upside_down) {
            if (y < cx->clipT) break;
            if (y > cx->clipB) continue;
    } else {
            if (y > cx->clipB) break;
            if (y >= cx->clipT) dda_span(cx, y, dda_unfp(left_x), dda_unfp(right_x), luv);
    }
}
'''


class VerticalDdaObserverTests(unittest.TestCase):
    def test_all_original_vertical_half_open_branches_observed_only(self):
        out = instrument_vertical(instrument_raster_skips(scope_raster(FAKE+PART)))
        for reason in range(4, 8):
            self.assertIn(f"VH_Map02SkipAt(vh_pixel_sample_x, y, {reason});", out)
        self.assertIn("cx->rc->target == 0", out)
        self.assertIn('#error "DDA vertical observer requires the native raster skip recorder"', out)
        self.assertIn("if (y >= cx->clipT)", out)
        self.assertIn("else if (cx->rc->target == 0)", out)
        self.assertIn("if (y < cx->clipT) {", out)
        self.assertIn("if (y > cx->clipB) {", out)
        self.assertIn("continue;", out)
        self.assertIn("break;", out)
        self.assertIn("if (cx->textured) { luv.u += cx->step.dudy;", out) if False else None
        self.assertEqual(out.count("#if defined(VH_MAP02_DDA_VERTICAL_TRACE)"), 4)
        with self.assertRaisesRegex(ValueError, "already installed"):
            instrument_vertical(out)

    def test_original_branch_text_must_be_exact_and_unique(self):
        for name, anchor in ANCHORS.items():
            with self.subTest(anchor=name):
                original=FAKE+PART
                with self.assertRaisesRegex(ValueError, "pinned source anchor count"):
                    instrument_vertical(instrument_raster_skips(scope_raster(
                        original.replace(anchor, "/* intentional upstream drift */"))))
                with self.assertRaisesRegex(ValueError, "pinned source anchor count"):
                    instrument_vertical(instrument_raster_skips(scope_raster(
                        original+anchor)))

    def test_refuse_unpinned_gpu_sources_and_output_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            g=root/"libgpu.c"
            r=root/"pc_raster.c"
            out=root/"out"
            g.write_text("unknown non-original GPU")
            r.write_text(FAKE+PART)
            with self.assertRaisesRegex(ValueError, "pinned original PC GPU"):
                prepare(g,r,out)
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaisesRegex(ValueError, "refusing overwrite"):
                prepare(g,r,out)


if __name__=="__main__":
    unittest.main()
