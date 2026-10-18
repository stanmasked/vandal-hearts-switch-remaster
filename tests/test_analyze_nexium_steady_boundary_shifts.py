"""Stage283 fixed-offset NeXium window robustness with synthetic original-SD copies."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import analyze_contrasts
from analyze_nexium_steady_boundary_shifts import (
    analyze_boundary_shifts,_bounded_pair_window,OFFSETS
)
from audit_nexium_audout_scene_correlation import CorrelationError
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class BoundaryShiftRegression(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        archives=[root/"one.zip",root/"two.zip"]
        for run_id,path in zip((28301,28302),archives):
            create_zip(path,paired_fixture(run_id))
        self.steady=analyze_archives(archives,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(
            self.steady,self.temporal,self.sensitivity,draws=8)

    def run_analysis(self):
        return analyze_boundary_shifts(self.steady,self.temporal,
                                       self.sensitivity,self.contrasts,draws=8)

    def test_all_five_fixed_left_shifts_match_original_stage282(self):
        report=self.run_analysis()
        self.assertEqual(report["pair_count"],2)
        self.assertEqual(report["offsets_seconds"],[-4,-3,-2,-1,0])
        self.assertEqual(len(report["candidate_boundaries"]),5)
        self.assertEqual([x["earlier_seconds"] for x in report["candidate_boundaries"]],
                         [[14,30],[15,31],[16,32],[17,33],[18,34]])
        self.assertEqual([x["later_seconds"] for x in report["candidate_boundaries"]],
                         [[31,47],[32,48],[33,49],[34,50],[35,51]])
        self.assertTrue(report["unshifted_contrast_matches_stage282"])
        self.assertFalse(report["physical_switch_tested"])
        for row in report["candidate_boundaries"]:
            self.assertEqual(row["source_workflow_run_ids"],report["source_run_ids"])
            for side in ("earlier","later"):
                for mode in ("idle","switch"):
                    self.assertEqual(row[f"{side}_mode_totals"][f"{mode}_attempts"],2*17*36)
            for band in ("ge40","ge50"):
                stats=row["bands"][band]
                self.assertEqual(len(stats["within_pair_contrasts_per_1000"]),2)
                self.assertEqual(sum(stats[key] for key in (
                    "positive_pairs","negative_pairs","exact_ties")),2)

    def test_results_bit_reproducible(self):
        self.assertEqual(self.run_analysis(),self.run_analysis())

    def test_original_stage282_forged_or_stale_rejected(self):
        for mutation in ("aggregate","identity","hardware"):
            with self.subTest(mutation=mutation):
                changed=copy.deepcopy(self.contrasts)
                if mutation=="aggregate":
                    changed["middle_minus_late_ge40_per_1000"]+=1
                elif mutation=="identity":
                    changed["source_run_ids"].reverse()
                else:
                    changed["physical_switch_tested"]=True
                with self.assertRaises(CorrelationError):
                    analyze_boundary_shifts(self.steady,self.temporal,
                                            self.sensitivity,changed,draws=8)

    def test_missing_second_and_reordered_source_pair_rejected(self):
        forged=copy.deepcopy(self.steady)
        forged["per_run_windows"][0]["switch"]["per_second"][46]["second"]=1
        with self.assertRaises(CorrelationError):
            analyze_boundary_shifts(forged,self.temporal,
                                    self.sensitivity,self.contrasts,draws=8)
        forged=copy.deepcopy(self.steady)
        forged["per_run_windows"].reverse()
        with self.assertRaises(CorrelationError):
            analyze_boundary_shifts(forged,self.temporal,
                                    self.sensitivity,self.contrasts,draws=8)

    def test_shifted_window_never_uses_out_of_range_second(self):
        pair=self.steady["steady_pair_verdict"]["pairs"][0]
        source=self.steady["per_run_windows"][0]
        for start in (0,36,100,-1):
            with self.subTest(start=start),self.assertRaises(CorrelationError):
                _bounded_pair_window(pair,source,start)
        self.assertEqual(OFFSETS,(-4,-3,-2,-1,0))

    def test_independent_denominators_and_real_boundary_replacement(self):
        pair=self.steady["steady_pair_verdict"]["pairs"][0]
        source=copy.deepcopy(self.steady["per_run_windows"][0])
        # A legitimate hypothetical per-second amount; check that
        # moving one boundary actually includes the new leading second
        # and omits the trailing second instead of simply relabeling.
        before=_bounded_pair_window(pair,source,18)
        source["switch"]["per_second"][16]["attempts"]=1000
        shifted=_bounded_pair_window(pair,source,17)
        self.assertEqual(shifted["switch_attempts"]-before["switch_attempts"],
                         1000-source["switch"]["per_second"][33]["attempts"])
        self.assertEqual(shifted["idle_attempts"],17*36)

    def test_no_randomized_or_audible_claim(self):
        report=self.run_analysis()
        self.assertTrue(report["overlapping_shifted_windows_are_not_independent"])
        self.assertFalse(report["randomized_or_causal_conclusion"])
        self.assertFalse(report["audible_underruns_or_DAC_clock_measured"])


if __name__=="__main__":
    unittest.main()
