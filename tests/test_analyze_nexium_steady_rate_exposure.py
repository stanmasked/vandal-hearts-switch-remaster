"""Stage286 exact numerator/denominator audout rate decomposition tests."""
from __future__ import annotations

import copy
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import analyze_contrasts
from analyze_nexium_steady_boundary_shifts import analyze_boundary_shifts
from analyze_nexium_steady_boundary_pair_grid import analyze_grid
from analyze_nexium_steady_disjoint_bands import analyze_components
from analyze_nexium_steady_rate_exposure import (
    analyze_exposure,_mode_effects,_full_effects,_same_stage285,TERMS
)
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class RateExposureRegression(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base=Path(temporary.name)
        archives=[base/"1.zip",base/"2.zip"]
        for run_id,path in zip((28601,28602),archives):
            create_zip(path,paired_fixture(run_id))
        self.steady=analyze_archives(archives,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(
            self.steady,self.temporal,self.sensitivity,draws=8)
        self.boundary=analyze_boundary_shifts(
            self.steady,self.temporal,self.sensitivity,self.contrasts,draws=8)
        self.grid=analyze_grid(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,draws=8)
        self.disjoint=analyze_components(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,draws=8)

    def evaluate(self,upstream=None):
        return analyze_exposure(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,
            self.disjoint if upstream is None else upstream,draws=8)

    def test_five_times_two_grid_every_band_and_mode(self):
        result=self.evaluate()
        self.assertEqual(result["pair_count"],2)
        self.assertEqual(result["shifts_seconds"],[-4,-3,-2,-1,0])
        self.assertEqual(len(result["windows"]),5)
        for band in ("ge40","between40and50","ge50"):
            self.assertEqual(result["matrix_summary"][band][
                "total_shift_and_excluded_pair_cells"],10)
            for position in result["windows"]:
                self.assertEqual(len(position["leave_one_pair_out"]),2)
                for mode in ("idle","switch","contrast"):
                    effects=position["full_cohort"][band][mode]
                    self.assertEqual(set(effects).intersection(TERMS),set(TERMS))
                    self.assertAlmostEqual(
                        effects["count_effect"]+effects["denominator_effect"],
                        effects["rate_drift"],delta=0.0000011)
        self.assertTrue(result["exact_fraction_identity_before_rounding"])
        self.assertFalse(result["physical_switch_tested"])
        self.assertFalse(result["randomized_significance_test"])

    def test_numerator_only_effect_unequal_slow_count_equal_attempts(self):
        first=[{"run_id":1,"idle_attempts":100,
                "idle_ge40":12,"idle_ge50":3}]
        second=[{"run_id":1,"idle_attempts":100,
                 "idle_ge40":4,"idle_ge50":1}]
        r=_mode_effects(first,second,"idle","ge40")
        self.assertEqual(r["count_effect"],Fraction(80))
        self.assertEqual(r["denominator_effect"],Fraction(0))
        self.assertEqual(r["rate_drift"],Fraction(80))

    def test_denominator_only_effect_equal_slow_count_unequal_attempts(self):
        first=[{"run_id":1,"idle_attempts":100,
                "idle_ge40":10,"idle_ge50":5}]
        second=[{"run_id":1,"idle_attempts":200,
                 "idle_ge40":10,"idle_ge50":5}]
        r=_mode_effects(first,second,"idle","ge40")
        self.assertEqual(r["count_effect"],Fraction(0))
        self.assertEqual(r["denominator_effect"],Fraction(50))
        self.assertEqual(r["rate_drift"],Fraction(50))

    def test_all_exact_fraction_band_additivity(self):
        first=[{"run_id":1,"idle_attempts":100,"idle_ge40":12,
                "idle_ge50":2,"switch_attempts":120,"switch_ge40":9,
                "switch_ge50":1}]
        second=[{"run_id":1,"idle_attempts":120,"idle_ge40":3,
                 "idle_ge50":1,"switch_attempts":100,"switch_ge40":7,
                 "switch_ge50":4}]
        result=_full_effects(first,second)
        for mode in ("idle","switch","contrast"):
            for term in TERMS:
                self.assertEqual(result["ge40"][mode][term],
                                 result["between40and50"][mode][term]
                                 +result["ge50"][mode][term])
                self.assertIsInstance(result["ge40"][mode][term],Fraction)
        self.assertEqual(result["ge40"]["idle"]["rate_drift"],
                         result["ge40"]["idle"]["count_effect"]+
                         result["ge40"]["idle"]["denominator_effect"])

    def test_negative_controls_upstream_tampering(self):
        for mutation in ("value","pair_id","hardware"):
            altered=copy.deepcopy(self.disjoint)
            if mutation=="value":
                altered["boundary_rows"][0]["full_cohort_disjoint_bands"][
                    "ge40"]["idle_earlier_minus_later_per_1000"]+=1
            elif mutation=="pair_id":
                altered["source_run_ids"].reverse()
            else:
                altered["physical_switch_tested"]=True
            with self.subTest(mutation=mutation),self.assertRaises(CorrelationError):
                self.evaluate(altered)

    def test_determinism_and_invalid_bootstrap_count(self):
        self.assertEqual(self.evaluate(),self.evaluate())
        for size in (0,-1,65537,True,1.25):
            with self.subTest(size=size),self.assertRaises(CorrelationError):
                analyze_exposure(self.steady,self.temporal,self.sensitivity,
                                 self.contrasts,self.boundary,self.grid,
                                 self.disjoint,draws=size)

    def test_missing_second_or_source_run_rejected(self):
        altered=copy.deepcopy(self.steady)
        altered["per_run_windows"][0]["switch"]["per_second"][25]["ge50"]+=1
        with self.assertRaises(CorrelationError):
            analyze_exposure(altered,self.temporal,self.sensitivity,
                             self.contrasts,self.boundary,self.grid,
                             self.disjoint,draws=8)


if __name__=="__main__":
    unittest.main()
