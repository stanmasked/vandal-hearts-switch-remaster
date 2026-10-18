"""Stage285 disjoint slow-call band controls with synthetic NeXium fixtures."""
from __future__ import annotations

import copy
from fractions import Fraction
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_steady_temporal_contrasts import analyze_contrasts
from analyze_nexium_steady_boundary_shifts import analyze_boundary_shifts
from analyze_nexium_steady_boundary_pair_grid import analyze_grid
from analyze_nexium_steady_disjoint_bands import (
    analyze_components,_raw_components,_per_mode_rate,_count
)
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class DisjointBandRegressions(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root=Path(temporary.name)
        paths=[root/"one.zip",root/"two.zip"]
        for run_id,path in zip((28501,28502),paths):
            create_zip(path,paired_fixture(run_id))
        self.steady=analyze_archives(paths,draws=4)
        self.temporal=analyze_temporal_thirds(self.steady)
        self.sensitivity=analyze_sensitivity(self.steady,self.temporal,draws=8)
        self.contrasts=analyze_contrasts(self.steady,self.temporal,
                                         self.sensitivity,draws=8)
        self.boundary=analyze_boundary_shifts(self.steady,self.temporal,
                            self.sensitivity,self.contrasts,draws=8)
        self.grid=analyze_grid(self.steady,self.temporal,self.sensitivity,
                               self.contrasts,self.boundary,draws=8)

    def run_analysis(self,grid=None):
        return analyze_components(self.steady,self.temporal,
                                  self.sensitivity,self.contrasts,
                                  self.boundary,self.grid if grid is None else grid,
                                  draws=8)

    def test_three_bands_five_shifts_both_source_pairs(self):
        result=self.run_analysis()
        self.assertEqual(result["pair_count"],2)
        self.assertEqual(len(result["boundary_rows"]),5)
        self.assertEqual(result["fixed_shifts_seconds"],[-4,-3,-2,-1,0])
        self.assertTrue(result["exact_fraction_conservation_before_rounding"])
        for row in result["boundary_rows"]:
            self.assertEqual(len(row["excluded_pairs"]),2)
            self.assertTrue(row["exact_ge40_equals_disjoint_sum"])
            self.assertEqual(set(row["full_cohort_disjoint_bands"]),
                             {"ge40","between40and50","ge50"})
        for band in ("ge40","between40and50","ge50"):
            stats=result["matrix_summary"][band]
            self.assertEqual(stats["evaluated_shift_and_exclusion_cells"],10)
            self.assertEqual(stats["positive_cells"]+stats["negative_cells"]
                             +stats["zero_cells"],10)
        self.assertFalse(result["physical_switch_tested"])
        self.assertFalse(result["audible_glitches_measured"])

    def test_bitwise_reproducibility(self):
        self.assertEqual(self.run_analysis(),self.run_analysis())

    def test_exact_rational_disjoint_identity_with_uneven_denominators(self):
        earlier=[{"run_id":1,"idle_attempts":200,"switch_attempts":100,
                  "idle_ge40":9,"idle_ge50":3,
                  "switch_ge40":12,"switch_ge50":2}]
        later=[{"run_id":1,"idle_attempts":100,"switch_attempts":200,
                "idle_ge40":8,"idle_ge50":1,
                "switch_ge40":15,"switch_ge50":6}]
        raw=_raw_components(earlier,later)
        for key in ("idle","switch","contrast"):
            self.assertIsInstance(raw["ge40"][key],Fraction)
            self.assertEqual(raw["ge40"][key],
                             raw["between40and50"][key]+raw["ge50"][key])
        self.assertEqual(_count(earlier[0],"idle","between40and50"),6)
        self.assertEqual(_per_mode_rate(earlier,"switch","between40and50"),
                         Fraction(1000*10,100))

    def test_impossible_bands_rejected(self):
        row={"run_id":1,"idle_attempts":100,"idle_ge40":2,"idle_ge50":3,
             "switch_attempts":100,"switch_ge40":0,"switch_ge50":0}
        with self.assertRaises(CorrelationError):
            _count(row,"idle","between40and50")
        row["idle_ge50"]=1
        row["idle_attempts"]=0
        with self.assertRaises(CorrelationError):
            _count(row,"idle","ge50")

    def test_tampered_or_overclaimed_stage284_rejected(self):
        for key in ("count","run","hardware"):
            with self.subTest(key=key):
                grid=copy.deepcopy(self.grid)
                if key=="count":
                    grid["matrix_summary"]["ge40"]["positive_cells"]+=1
                elif key=="run":
                    grid["source_run_ids"].reverse()
                else:
                    grid["physical_switch_tested"]=True
                with self.assertRaises(CorrelationError):
                    self.run_analysis(grid)

    def test_unchanged_threshold_crosscheck(self):
        result=self.run_analysis()
        for band in ("ge40","ge50"):
            self.assertEqual(result["matrix_summary"][band]["positive_cells"],
                             self.grid["matrix_summary"][band]["positive_cells"])
            self.assertEqual(result["matrix_summary"][band]["negative_cells"],
                             self.grid["matrix_summary"][band]["negative_cells"])

    def test_bounded_draws_and_unaudited_second_rejected(self):
        for bad in (0,-2,65537,True,1.5):
            with self.subTest(bad=bad),self.assertRaises(CorrelationError):
                analyze_components(self.steady,self.temporal,self.sensitivity,
                                   self.contrasts,self.boundary,self.grid,draws=bad)
        forged=copy.deepcopy(self.steady)
        forged["per_run_windows"][0]["idle"]["per_second"][19]["ge50"]+=1
        with self.assertRaises(CorrelationError):
            analyze_components(forged,self.temporal,self.sensitivity,
                               self.contrasts,self.boundary,self.grid,draws=8)


if __name__=="__main__":
    unittest.main()
