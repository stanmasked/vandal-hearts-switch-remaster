"""Stage287 synthetic per-second slow-call concentration and audit controls."""
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
from analyze_nexium_steady_rate_exposure import analyze_exposure
from analyze_nexium_steady_second_profile import (
    analyze_second_profile,_concentration,_longest_positive_streak
)
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class ExactSecondProfileRegressions(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        files=[base/"a.zip",base/"b.zip"]
        for run,path in zip((28701,28702),files):
            create_zip(path,paired_fixture(run))
        self.steady=analyze_archives(files,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(
            self.steady,self.temporal,self.sensitivity,draws=8)
        self.boundary=analyze_boundary_shifts(
            self.steady,self.temporal,self.sensitivity,self.contrasts,draws=8)
        self.grid=analyze_grid(self.steady,self.temporal,self.sensitivity,
                               self.contrasts,self.boundary,draws=8)
        self.disjoint=analyze_components(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,draws=8)
        self.exposure=analyze_exposure(
            self.steady,self.temporal,self.sensitivity,self.contrasts,
            self.boundary,self.grid,self.disjoint,draws=8)

    def audit(self,exposure=None,steady=None):
        return analyze_second_profile(
            self.steady if steady is None else steady,
            self.temporal,self.sensitivity,self.contrasts,self.boundary,
            self.grid,self.disjoint,
            self.exposure if exposure is None else exposure,draws=8)

    def test_exact_51_seconds_two_modes_and_three_thresholds(self):
        report=self.audit()
        self.assertEqual(report["source_run_ids"],[28701,28702])
        self.assertEqual(report["seconds_included"],51)
        self.assertEqual([x["guest_audio_service_second"]
                          for x in report["per_second"]],list(range(1,52)))
        for second in report["per_second"]:
            for mode in ("idle","switch"):
                counts=second["totals"][mode]
                self.assertEqual(counts["between40and50"],
                                 counts["ge40"]-counts["ge50"])
                self.assertEqual(counts["attempts"],72)
            for band in ("ge40","between40and50","ge50"):
                self.assertEqual(sum(second["paired_rate_directions"][band].values()),2)
        for band in ("ge40","between40and50","ge50"):
            self.assertEqual(sum(report["band_summary"][band][x] for x in (
                "positive_seconds","negative_seconds","exact_zero_seconds")),51)
        self.assertTrue(report["exact_count_and_17s_third_conservation"])
        self.assertFalse(report["physical_switch_tested"])

    def test_same_inputs_bit_reproducible(self):
        self.assertEqual(self.audit(),self.audit())

    def test_top5_abs_l1_concentration_includes_tie_break(self):
        original=[(7,Fraction(0)),(3,Fraction(3)),
                  (4,Fraction(1)),(1,Fraction(3)),
                  (2,Fraction(1)),(5,Fraction(1))]
        result=_concentration(original)
        self.assertEqual([r["second"] for r in result["top_seconds"]],
                         [1,3,2,4,5])
        self.assertAlmostEqual(result["top_five_share_percent"],100)
        self.assertTrue(result["not_share_of_whole_51s_pooled_rate"])
        self.assertEqual(_concentration([(1,Fraction(0))])[
            "top_five_share_percent"],0)

    def test_gaps_and_positive_streak(self):
        self.assertEqual(_longest_positive_streak([
            (1,Fraction(1)),(2,Fraction(2)),(3,Fraction(-1)),
            (4,Fraction(0)),(5,Fraction(1))]),2)
        with self.assertRaises(CorrelationError):
            _longest_positive_streak([(1,Fraction(1)),(3,Fraction(1))])

    def test_previous_report_forgery_or_hardware_claim_rejected(self):
        for mutation in ("rate","run","hardware"):
            with self.subTest(mutation=mutation):
                altered=copy.deepcopy(self.exposure)
                if mutation=="rate":
                    altered["windows"][0]["full_cohort"]["ge40"][
                        "contrast"]["count_effect"]+=0.01
                elif mutation=="run":
                    altered["source_run_ids"].reverse()
                else:
                    altered["physical_switch_tested"]=True
                with self.assertRaises(CorrelationError):
                    self.audit(exposure=altered)

    def test_missing_duplicate_out_of_order_second_rejected(self):
        for mutation in ("drop","duplicate","counter"):
            with self.subTest(mutation=mutation):
                altered=copy.deepcopy(self.steady)
                r=altered["per_run_windows"][0]["switch"]["per_second"]
                if mutation=="drop":
                    r.pop(4)
                elif mutation=="duplicate":
                    r[4]["second"]=r[3]["second"]
                else:
                    r[5]["ge40"]+=1
                with self.assertRaises(CorrelationError):
                    self.audit(steady=altered)

    def test_nonrandomized_and_fixed_order_claims(self):
        report=self.audit()
        self.assertTrue(report["top_five_seconds_selected_post_hoc_not_independent"])
        self.assertTrue(report["guest_service_seconds_not_scheduler_execution_trace"])
        self.assertTrue(report["fixed_switch_before_idle_capture_order"])
        self.assertFalse(report["DAC_underruns_or_audible_glitches_measured"])
        self.assertFalse(report["music_switch_causality_proven"])


if __name__=="__main__":
    unittest.main()
