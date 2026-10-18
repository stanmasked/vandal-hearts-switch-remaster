"""Stage284 synthetic source-bound negative controls, not hardware evidence."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import analyze_contrasts
from analyze_nexium_steady_boundary_shifts import analyze_boundary_shifts
from analyze_nexium_steady_boundary_pair_grid import analyze_grid,_decompose
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class Stage284GridRegressions(unittest.TestCase):
    def setUp(self):
        td=tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root=Path(td.name)
        paths=[root/"a.zip",root/"b.zip"]
        for run,path in zip((28401,28402),paths):
            create_zip(path,paired_fixture(run))
        self.steady=analyze_archives(paths,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(self.steady,self.temporal,
                                         self.sensitivity,draws=8)
        self.boundaries=analyze_boundary_shifts(
            self.steady,self.temporal,self.sensitivity,self.contrasts,draws=8)

    def audit(self, boundary=None):
        return analyze_grid(self.steady,self.temporal,self.sensitivity,
                            self.contrasts,
                            self.boundaries if boundary is None else boundary,
                            draws=8)

    def test_five_shifts_two_pair_exclusions_and_drift_decomposition(self):
        report=self.audit()
        self.assertEqual(report["pair_count"],2)
        self.assertEqual(report["shift_count"],5)
        self.assertEqual(report["fixed_shifts_seconds"],[-4,-3,-2,-1,0])
        for threshold in ("ge40","ge50"):
            self.assertEqual(report["matrix_summary"][threshold][
                "total_shift_by_excluded_pair_cells"],10)
            for row in report["grid"]:
                band=row["bands"][threshold]
                self.assertEqual(len(band["leave_one_pair_out"]),2)
                self.assertEqual([x["excluded_workflow_run_id"]
                                  for x in band["leave_one_pair_out"]],
                                 report["source_run_ids"])
                self.assertEqual(
                    band["positive_leave_one_out"]
                    +band["negative_leave_one_out"]
                    +band["exact_zero_leave_one_out"],2)
        self.assertTrue(report["same_workflow_pair_removed_in_both_modes_and_both_windows"])
        self.assertFalse(report["physical_switch_tested"])
        self.assertFalse(report["is_statistical_significance_test"])

    def test_identical_source_reports_are_bit_reproducible(self):
        self.assertEqual(self.audit(),self.audit())

    def test_forged_boundary_counts_even_with_same_run_id_rejected(self):
        for mutation in ("aggregate","leave_one","order","physical"):
            with self.subTest(mutation=mutation):
                doc=copy.deepcopy(self.boundaries)
                if mutation=="aggregate":
                    doc["candidate_boundaries"][2]["bands"]["ge40"][
                        "difference_of_pooled_rate_differences_per_1000"]+=1
                elif mutation=="leave_one":
                    doc["candidate_boundaries"][1]["bands"]["ge50"][
                        "leave_one_pair_out_max_per_1000"]+=1
                elif mutation=="order":
                    doc["offsets_seconds"].reverse()
                else:
                    doc["physical_switch_tested"]=True
                with self.assertRaises(CorrelationError):
                    self.audit(doc)

    def test_per_second_mutation_or_reordered_run_ids_fails_closed(self):
        altered=copy.deepcopy(self.steady)
        altered["per_run_windows"][0]["switch"]["per_second"][47]["ge40"]+=1
        with self.assertRaises(CorrelationError):
            analyze_grid(altered,self.temporal,self.sensitivity,
                         self.contrasts,self.boundaries,draws=8)
        altered=copy.deepcopy(self.steady)
        altered["per_run_windows"].reverse()
        with self.assertRaises(CorrelationError):
            analyze_grid(altered,self.temporal,self.sensitivity,
                         self.contrasts,self.boundaries,draws=8)

    def test_mode_drift_uses_both_denominators_independently(self):
        early={"run_id":1,"idle_attempts":1000,"switch_attempts":500,
               "idle_ge40":10,"switch_ge40":10}
        later={"run_id":1,"idle_attempts":500,"switch_attempts":1000,
               "idle_ge40":10,"switch_ge40":10}
        x=_decompose([early],[later],"ge40")
        self.assertAlmostEqual(x["idle_earlier_minus_later_per_1000"],-10.)
        self.assertAlmostEqual(x["switch_earlier_minus_later_per_1000"],10.)
        self.assertAlmostEqual(x["switch_drift_minus_idle_drift_per_1000"],20.)

    def test_cannot_claim_audible_sound_or_randomization(self):
        report=self.audit()
        self.assertFalse(report["audible_underruns_or_DAC_clock_measured"])
        self.assertFalse(report["scene_switch_causal_effect_established"])
        self.assertFalse(report["physical_switch_tested"])
        self.assertTrue(report["overlapping_offsets_not_independent_observations"])


if __name__=="__main__":
    unittest.main()
