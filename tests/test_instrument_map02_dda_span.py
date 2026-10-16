import unittest
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_dda_span import instrument_span, FLAG
from test_instrument_map02_raster_skips import FAKE

class SpanInstrumentationTests(unittest.TestCase):
    def test_one_exact_executed_span_hook(self):
        src = instrument_span(instrument_raster_skips(scope_raster(FAKE)))
        self.assertEqual(src.count("VH_Map02SpanObserve(cx, y, x_start, x_bound);"), 1)
        self.assertIn("cx->rc->target != 0", src)
        self.assertIn("y != vh_pixel_sample_y", src)
        self.assertIn("dda-native-spans.jsonl", src)
        self.assertIn("#error \"DDA span trace requires", src)
        self.assertIn("vh_map02_span_count >= VH_MAP02_SPAN_CAP", src)
        self.assertIn(FLAG, src)

    def test_refuse_double_install(self):
        src = instrument_span(instrument_raster_skips(scope_raster(FAKE)))
        with self.assertRaisesRegex(ValueError, "already installed"):
            instrument_span(src)

    def test_refuse_unscoped_source(self):
        with self.assertRaisesRegex(ValueError, "requires existing"):
            instrument_span(FAKE)

    def test_refuse_missing_or_duplicate_anchor(self):
        src = instrument_raster_skips(scope_raster(FAKE))
        from tools.instrument_map02_raster_skips import SPAN_ANCHOR
        with self.assertRaises(ValueError): instrument_span(src.replace(SPAN_ANCHOR, "/* drift */"))
        with self.assertRaises(ValueError): instrument_span(src + SPAN_ANCHOR)

if __name__ == "__main__":
    unittest.main()
