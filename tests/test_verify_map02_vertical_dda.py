"""Asset-free test of strict vertical *scanline* rejection attribution."""
import unittest

import test_verify_map02_raster_skips as prior
from tools.verify_map02_raster_skips import verify_skips


class OriginalVerticalScanlineAuditTests(unittest.TestCase):
    def setUp(self):
        self.base=prior.NativeRasterSkipAuditTests(
            methodName="test_three_exact_original_skip_branches_link_to_two_ft4")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.source=self.base.source
        self.native=self.base.native

    def test_all_four_real_pc_dda_vertical_row_decisions(self):
        fields=[
            "observed_upside_down_below_top_scanline_break_events",
            "observed_upside_down_above_bottom_scanline_continue_events",
            "observed_forward_above_bottom_scanline_break_events",
            "observed_forward_below_top_scanline_no_span_events",
        ]
        for index, key in enumerate(fields, start=4):
            with self.subTest(reason=index):
                self.base.rows=[self.base.row(0,1,index)]
                self.base.save()
                report=verify_skips(self.source,self.native)
                self.assertEqual(report["observed_skip_events"],1)
                self.assertEqual(report[key],1)
                self.assertEqual(report["vertical_scanline_rejections_observed"],1)
                self.assertEqual(
                    report["vertical_scanline_rejections_attributed_to_source_ft4"],1)
                self.assertTrue(report["vertical_clip_scanline_branches_observed_only"])
                self.assertFalse(report["vertical_scanline_horizontal_coverage_proven"])
                self.assertFalse(report["vertical_clip_per_pixel_confirmed"])
                self.assertFalse(report["triangle_coverage_and_mask_test_verified"])

    def test_non_source_primitive_vertical_decision_is_not_attributed_to_terrain(self):
        self.base.rows=[self.base.row(0,0,6)]
        self.base.rows[0]["primitive_type"]=5
        self.base.save()
        report=verify_skips(self.source,self.native)
        self.assertEqual(report["vertical_scanline_rejections_observed"],1)
        self.assertEqual(report["vertical_scanline_rejections_attributed_to_source_ft4"],0)
        self.assertEqual(report["source_keyed_ft4_primitives_with_direct_skip_observation"],0)

    def test_existing_texture_and_horizontal_reasons_still_work(self):
        self.base.save()
        report=verify_skips(self.source,self.native)
        self.assertEqual(report["observed_skip_events"],3)
        self.assertEqual(report["vertical_scanline_rejections_observed"],0)
        self.assertEqual(report["observed_dda_zero_bgr555_texel_events"],1)
        self.assertEqual(report["observed_dda_horizontal_span_clip_events"],1)
        self.assertEqual(report["observed_legacy_zero_bgr555_texel_events"],1)

    def test_out_of_range_reason_eight_rejected(self):
        self.base.rows=[self.base.row(0,1,8)]
        self.base.save()
        with self.assertRaisesRegex(ValueError, "expected integer"):
            verify_skips(self.source,self.native)


if __name__=="__main__":
    unittest.main()
