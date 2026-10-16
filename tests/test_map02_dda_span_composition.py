"""Regression for the exact production generator composition chain.

Does not assert that fabricated source is the actual pinned C blob.
"""
import unittest

from test_instrument_map02_raster_skips import FAKE
from test_instrument_map02_vertical_dda import PART
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_vertical_dda import instrument_vertical
from tools.instrument_map02_dda_span import instrument_span


class ComposedOriginalDdaHookTests(unittest.TestCase):
    def make(self):
        return instrument_span(instrument_vertical(
            instrument_raster_skips(scope_raster(FAKE + PART))))

    def test_vertical_reasons_retained_and_one_span_entry(self):
        src = self.make()
        for reason in (4, 5, 6, 7):
            self.assertEqual(
                src.count("VH_Map02SkipAt(vh_pixel_sample_x, y, %d);" % reason), 1)
        self.assertEqual(src.count(
            "VH_Map02SpanObserve(cx, y, x_start, x_bound);"), 1)

    def test_observer_does_not_modify_original_span_call_sites(self):
        src = self.make()
        self.assertIn("dda_span(cx, y, dda_unfp(left_x), dda_unfp(right_x), luv);", src)
        self.assertIn("if (y >= cx->clipT)", src)
        self.assertIn("if (y < cx->clipT)", src)
        self.assertIn("if (y > cx->clipB)", src)

    def test_missing_original_span_signature_fails_closed(self):
        from tools.instrument_map02_raster_skips import SPAN_ANCHOR
        modified = instrument_vertical(instrument_raster_skips(scope_raster(FAKE + PART)))
        with self.assertRaises(ValueError):
            instrument_span(modified.replace(SPAN_ANCHOR, "/* upstream drift */"))

    def test_baseline_has_no_unconditional_span_recorder_call(self):
        src = self.make()
        pos = src.index("VH_Map02SpanObserve(cx, y, x_start, x_bound);")
        self.assertIn("#if defined(VH_MAP02_DDA_SPAN_TRACE)", src[pos - 70:pos])
        self.assertIn("#endif", src[pos:pos + 85])


if __name__ == "__main__":
    unittest.main()
