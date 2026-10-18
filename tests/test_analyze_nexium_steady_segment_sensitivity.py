"""Stage281 synthetic interval variation; independent hardware not tested."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import analyze_archives
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from test_compare_nexium_idle_switch_pairs import paired_fixture
from test_compare_nexium_verified_slow_runs import create_zip


class Stage281Sensitivity(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        paths=[root/"a.zip",root/"b.zip"]
        for run_id,path in zip((28101,28102),paths):
            create_zip(path,paired_fixture(run_id))
        self.steady=analyze_archives(paths,draws=8)
        self.thirds=analyze_temporal_thirds(self.steady)

    def test_exact_derived_three_thirds_and_deterministic_paired_bands(self):
        one=analyze_sensitivity(self.steady,self.thirds,draws=32)
        two=analyze_sensitivity(self.steady,self.thirds,draws=32)
        self.assertEqual(one,two)
        self.assertEqual(one["pair_count"],2)
        self.assertEqual(len(one["thirds"]),3)
        for part in one["thirds"]:
            for label in ("ge40","ge50"):
                band=part["bands"][label]
                self.assertEqual(len(band["individual_pair_differences_per_1000"]),2)
                self.assertEqual(
                    band["positive_pairs"]+band["negative_pairs"]+band["exact_ties"],2)
                self.assertLessEqual(band["leave_one_pair_out_min_per_1000"],
                                     band["leave_one_pair_out_max_per_1000"])
                self.assertFalse(band["whole_pair_resampling"]["is_formal_confidence_interval"])
        self.assertTrue(one["source_stage280_report_exactly_rederived"])
        self.assertFalse(one["is_randomization_test"])
        self.assertFalse(one["physical_switch_tested"])

    def test_forged_stage280_counts_rejected_even_if_rate_is_untouched(self):
        altered=copy.deepcopy(self.thirds)
        altered["segments"][0]["totals"]["idle_ge40"]+=1
        with self.assertRaises(CorrelationError):
            analyze_sensitivity(self.steady,altered,draws=2)

    def test_modified_source_identity_and_stale_report_rejected(self):
        altered=copy.deepcopy(self.steady)
        altered["per_run_windows"][0]["run_id"]=28199
        with self.assertRaises(CorrelationError):
            analyze_sensitivity(altered,self.thirds,draws=2)
        altered=copy.deepcopy(self.thirds)
        altered["source_run_ids"].reverse()
        with self.assertRaises(CorrelationError):
            analyze_sensitivity(self.steady,altered,draws=2)

    def test_overclaimed_physical_audio_causality_rejected(self):
        for key in ("physical_switch_tested","music_switch_causal_effect_proven"):
            with self.subTest(key=key):
                altered=copy.deepcopy(self.thirds)
                altered[key]=True
                with self.assertRaises(CorrelationError):
                    analyze_sensitivity(self.steady,altered,draws=2)

    def test_invalid_resampling_size_rejected(self):
        for value in (0,-1,65537,True,1.5):
            with self.subTest(value=value),self.assertRaises(CorrelationError):
                analyze_sensitivity(self.steady,self.thirds,draws=value)

    def test_removed_bin_provenance_rejected(self):
        altered=copy.deepcopy(self.steady)
        del altered["per_run_windows"][0]["idle"]["per_second"][1]
        with self.assertRaises(CorrelationError):
            analyze_sensitivity(altered,self.thirds,draws=2)


if __name__=="__main__":
    unittest.main()
