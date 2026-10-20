"""Structural-only tests: this does not certify C compilation or scene behavior."""
import unittest
from test_instrument_map02_raster_skips import FAKE
from test_instrument_map02_vertical_dda import PART
from tools.instrument_map02_putpixel_scope import scope_raster
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_vertical_dda import instrument_vertical
from tools.instrument_map02_dda_rejected_edges import instrument_rejected_edges

class RejectedCandidateTests(unittest.TestCase):
    def make(self):
        return instrument_rejected_edges(instrument_vertical(
            instrument_raster_skips(scope_raster(FAKE + PART))))

    def test_one_candidate_per_vertical_branch(self):
        out = self.make()
        for reason in (4, 5, 6, 7):
            self.assertEqual(out.count(
                f"VH_Map02RejectedEdges(cx, y, left_x, right_x, {reason});"), 1)
        self.assertIn("rejected_edge_candidate", out)
        self.assertIn("dda-rejected-edge-candidates.jsonl", out)

    def test_candidate_flag_is_strictly_opt_in(self):
        out = self.make()
        self.assertIn('#error "DDA rejected edges requires original native diagnostic chain"', out)
        self.assertEqual(out.count("#if defined(VH_MAP02_DDA_REJECTED_EDGES_TRACE)"), 6)
        # Two helper-level guards (prerequisites + definition), four rejection sites.
        for reason in (4, 5, 6, 7):
            condition = "y < cx->clipT" if reason in (4, 7) else "y > cx->clipB"
            self.assertIn(
                f"if ({condition}) VH_Map02RejectedEdges(cx, y, left_x, right_x, {reason});",
                out)
            self.assertIn(f"VH_Map02SkipAt(vh_pixel_sample_x, y, {reason});", out)
        self.assertIn("vh_rejected_edge_count >= 64u", out)
        self.assertIn("cx->rc->target != 0", out)

    def test_refuse_double_instrumentation(self):
        with self.assertRaisesRegex(ValueError, "already installed"):
            instrument_rejected_edges(self.make())

    def test_refuse_uninstrumented_source(self):
        with self.assertRaisesRegex(ValueError, "vertical observer required"):
            instrument_rejected_edges(FAKE + PART)

if __name__ == "__main__":
    unittest.main()
