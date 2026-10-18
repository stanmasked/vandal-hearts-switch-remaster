"""Stage282 synthetic same-pair interval contrast checks, not audio evidence."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import (
    analyze_contrasts, _paired_contrast
)
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class TemporalContrastRegression(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder=Path(tmp.name)
        paths=[folder/"a.zip",folder/"b.zip"]
        for run,path in zip((28201,28202),paths):
            create_zip(path,paired_fixture(run))
        self.steady=analyze_archives(paths,draws=8)
        self.thirds=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.thirds,draws=16)

    def test_three_contrasts_two_thresholds_exact_and_reproducible(self):
        a=analyze_contrasts(self.steady,self.thirds,self.sensitivity,draws=16)
        b=analyze_contrasts(self.steady,self.thirds,self.sensitivity,draws=16)
        self.assertEqual(a,b)
        self.assertEqual(a["pair_count"],2)
        self.assertEqual([x["name"] for x in a["contrasts"]],
                         ["early_minus_middle","middle_minus_late",
                          "early_minus_late"])
        self.assertTrue(a["upstream_281_exactly_recalculated"])
        self.assertTrue(a["same_pair_indices_used_in_both_resampled_windows"])
        self.assertFalse(a["confidence_interval_claim"])
        for contrast in a["contrasts"]:
            for threshold in ("ge40","ge50"):
                band=contrast["bands"][threshold]
                self.assertEqual(len(band["per_pair_earlier_minus_later_per_1000"]),2)
                self.assertEqual(
                    band["positive_pairs"]+band["negative_pairs"]+band["exact_ties"],2)
                self.assertFalse(band["same_pair_correlated_resampling"][
                    "is_formal_confidence_interval"])

    def test_upstream_mutated_sensitivity_rejected(self):
        for mutation in ("count","order","causality"):
            with self.subTest(mutation=mutation):
                doc=copy.deepcopy(self.sensitivity)
                if mutation=="count":
                    doc["thirds"][1]["bands"]["ge40"]["positive_pairs"]+=1
                elif mutation=="order":
                    doc["source_run_ids"].reverse()
                else:
                    doc["music_switch_causality_established"]=True
                with self.assertRaises(CorrelationError):
                    analyze_contrasts(self.steady,self.thirds,doc,draws=16)

    def test_stale_or_tampered_temporal_report_rejected(self):
        altered=copy.deepcopy(self.thirds)
        altered["segments"][1]["per_run_pairs"][0]["idle_ge40"]+=1
        with self.assertRaises(CorrelationError):
            analyze_contrasts(self.steady,altered,self.sensitivity,draws=16)

    def test_invalid_draw_count_rejected(self):
        for count in (0,-1,65537,True,1.2):
            with self.subTest(count=count),self.assertRaises(CorrelationError):
                analyze_contrasts(self.steady,self.thirds,self.sensitivity,
                                  draws=count)

    def test_disjoint_or_reordered_run_ids_in_resample_rejected(self):
        pairs=self.thirds["segments"][0]["per_run_pairs"]
        other=copy.deepcopy(pairs)
        other.reverse()
        with self.assertRaises(CorrelationError):
            _paired_contrast(pairs,other,"ge40")

    def test_temporal_difference_uses_both_mode_denominators(self):
        pair={
            "run_id":1,"idle_attempts":1000,"switch_attempts":500,
            "idle_ge40":10,"switch_ge40":10,
            "idle_ge50":2,"switch_ge50":1,
        }
        later={**pair,"idle_attempts":500,"switch_attempts":1000,
               "idle_ge40":10,"switch_ge40":10}
        self.assertAlmostEqual(_paired_contrast([pair],[later],"ge40"),20.0)


if __name__=="__main__":
    unittest.main()
