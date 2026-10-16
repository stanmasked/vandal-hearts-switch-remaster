"""Pure arithmetic regression tests; NOT original MAP02 gameplay tests."""
import unittest
from dataclasses import replace
from tools.map02_dda_coverage import Row, classify

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.row = Row(10, 20, 12, 5, 25, 10, 15, 15, 12)

    def test_half_open_left_in_right_out(self):
        self.assertTrue(classify(replace(self.row, sample_x=10))["dda_clipped_x_covered"])
        self.assertFalse(classify(replace(self.row, sample_x=20))["dda_unclipped_x_covered"])

    def test_vertical_above_and_below(self):
        for y in (9, 16):
            r = classify(replace(self.row, y=y, sample_y=y))
            self.assertTrue(r["vertical_rejected_but_unclipped_x_covered"])
            self.assertFalse(r["dda_clipped_x_covered"])

    def test_clip_boundaries_inclusive(self):
        for y in (10, 15):
            self.assertTrue(classify(replace(self.row, y=y, sample_y=y))["dda_clipped_x_covered"])

    def test_horizontal_clip(self):
        r = classify(replace(self.row, clip_l=16))
        self.assertFalse(r["dda_clipped_x_covered"])
        self.assertTrue(r["dda_unclipped_x_covered"])

    def test_degenerate_span(self):
        self.assertFalse(classify(replace(self.row, x_start=10, x_bound=10))["dda_unclipped_x_covered"])

    def test_row_mismatch(self):
        self.assertFalse(classify(replace(self.row, sample_y=13))["dda_unclipped_x_covered"])

    def test_invalid_and_noninteger_refused(self):
        with self.assertRaises(ValueError): classify(replace(self.row, x_start=21))
        with self.assertRaises(ValueError): classify(replace(self.row, clip_t=16))
        with self.assertRaises(ValueError): classify(replace(self.row, sample_x=True))

    def test_no_hardware_claim(self):
        r = classify(self.row)
        self.assertFalse(r["coverage_proven_by_original_gpu"])
        self.assertFalse(r["pixel_written_proven"])
        self.assertFalse(r["hardware_mask_stp_abr_proven"])

if __name__ == "__main__":
    unittest.main()
