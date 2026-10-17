"""Stage278 synthetic paired-variance controls, not real NeXium inference."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_idle_switch_variability import analyze,_bootstrap
from compare_nexium_idle_switch_pairs import summarize

NRO="4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb"

def fixture():
    # Synthetic arithmetically valid samples model varying workflow rates.
    rows=[
        (2287,1981,33,29,5,1),
        (2222,1949,25,33,3,2),
        (2233,1925,21,22,0,1),
        (2176,1861,41,33,4,5),
        (2227,1944,26,32,1,4),
        (2250,1952,41,24,3,0),
        (2250,1951,28,35,3,2),
    ]
    pairs=[]
    for i,(ia,sa,i40,s40,i50,s50) in enumerate(rows):
        pairs.append({
            "run_id":10_000+i,
            "git_sha":"a"*40,
            "nro_sha256":NRO,
            "idle_attempts":ia,"switch_attempts":sa,
            "idle_ge40":i40,"switch_ge40":s40,
            "idle_ge50":i50,"switch_ge50":s50,
            "idle_seconds":61,"switch_seconds":53,
            "idle_original_sd_audited_in_prior_workflow":True,
            "switch_original_sd_audited_in_prior_workflow":True,
            "all_copied_guest_bytes_reverified":True,
        })
    return summarize(pairs)


class AnalyzePairedVariabilityTests(unittest.TestCase):
    def test_realistic_synthetic_seven_pair_metrics_deterministic(self):
        source=fixture()
        result=analyze(source,draws=1024)
        self.assertEqual(result["pair_count"],7)
        self.assertEqual(result["result"],
                         "EXPLORATORY_PAIRED_NEXIUM_VARIABILITY_COMPUTED")
        self.assertFalse(result["statistical_causal_music_claim"])
        self.assertFalse(result["bootstrap_is_inferential_confidence_interval"])
        self.assertFalse(result["switching_order_randomized"])
        for band in ("ge40","ge50"):
            b=result["bands"][band]
            self.assertAlmostEqual(
                b["aggregate_switch_minus_idle_per_1000"],
                round(source["rates"]["switch_"+band+"_per_1000_attempts"]-
                      source["rates"]["idle_"+band+"_per_1000_attempts"],3),
                delta=.0011
            )
            self.assertEqual(
                b["positive_pairs"]+b["negative_pairs"]+b["zero_difference_pairs"],7)
            self.assertLessEqual(
                b["leave_one_pair_out_difference_min_per_1000"],
                b["leave_one_pair_out_difference_max_per_1000"])
            self.assertFalse(b["paired_resampling_sensitivity"]["is_formal_confidence_interval"])
            self.assertFalse(b["paired_resampling_sensitivity"]["is_randomization_test"])
        second=analyze(source,draws=1024)
        self.assertEqual(second,result)

    def test_remove_each_whole_workflow_instead_of_individual_buffers(self):
        r=analyze(fixture(),draws=64)
        d=r["bands"]["ge40"]
        self.assertEqual(len(d["individual_pair_differences_per_1000"]),7)
        self.assertNotEqual(
            d["leave_one_pair_out_difference_max_per_1000"],
            d["leave_one_pair_out_difference_min_per_1000"])

    def test_wrong_total_denominator_rejected(self):
        source=fixture()
        source["totals"]["idle_attempts"]+=1
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_forged_rate_rejected(self):
        source=fixture()
        source["rates"]["switch_ge40_per_1000_attempts"]+=.002
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_pair_direction_tampering_rejected(self):
        source=fixture()
        source["paired_rate_directions"]["ge50"]["switch_rate_higher"]+=1
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_incomplete_sd_or_nro_refused(self):
        source=fixture()
        source["pairs"][0]["idle_original_sd_audited_in_prior_workflow"]=False
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)
        source=fixture()
        source["pairs"][1]["nro_sha256"]="0"*64
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_fake_extra_or_duplicate_run_id_refused(self):
        source=fixture()
        source["pairs"][1]["run_id"]=source["pairs"][0]["run_id"]
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)
        source=fixture()
        source["independent_workflow_run_ids"].append(77)
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_invalid_audio_bands_and_short_capture_rejected(self):
        source=fixture()
        source["pairs"][0]["idle_ge50"]=50
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)
        source=fixture()
        source["pairs"][0]["idle_seconds"]=49
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_no_fake_randomization_or_formal_claim(self):
        source=fixture()
        source["randomized_or_causal_inference"]=True
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)
        source=fixture()
        source["original_guest_sd_reopened_offline"]=True
        with self.assertRaises(CorrelationError):
            analyze(source,draws=4)

    def test_zero_overflow_and_deterministic_bounds(self):
        with self.assertRaises(CorrelationError):
            analyze(fixture(),draws=0)
        with self.assertRaises(CorrelationError):
            analyze(fixture(),draws=65537)
        self.assertEqual(
            _bootstrap(fixture()["pairs"],"ge40",256),
            _bootstrap(fixture()["pairs"],"ge40",256))


if __name__=="__main__":
    unittest.main()
