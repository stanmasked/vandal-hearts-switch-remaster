"""Stage295 real measured phase0 and phase8 source-bound comparison tests."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from compare_nexium_real_queue_phases import compare_real_phases,inspect_observations


def model(phase:int)->dict:
    attempts=50
    count=(attempts+15-phase)//16
    rows=[{
        "index":i,"attempt":1+phase+16*i,
        "submit_begin_ns":1_000_000_000+i*400_000_000,
        "audio_second":i,
        "query_succeeded":True,
        "pre_submit_queue_count":2 if phase==8 and i==1 else 0
    } for i in range(count)]
    r={
        "schema":"vh-audout-service-probe-guest-clock/v1",
        "result":"GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED",
        "declared_query_phase":phase,
        "original_guest_sd_opened_in_current_workflow":True,
        "pre_submit_queue_service_snapshot_only":True,
        "queries_per_sixteen_attempts_at_most_one":True,
        "scene_input_count":10,
        "probe_samples_begin_within_500ms_of_input":0,
        "scheduler_or_DAC_state_measured":False,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
        "scene_to_probe_causality_proven":False,
        "query_timestamp_is_exactly_recorded":False,
        "audout_submission_begin_timestamp_is_exactly_recorded":True,
        "guest_original_probe_sha256":("a" if phase==0 else "b")*64,
        "copied_probe_sha256":("a" if phase==0 else "b")*64,
        "guest_writer_receipt_sha256":"f"*64,
        "queue_probe_dropped":0,
        "audout_attempts":attempts,
        "queue_probe_samples":count,
        "queue_probe_successes":count,
        "queue_probe_failures":0,
        "sample_records":rows,
        "probed_slow_calls":[{**rows[-1],"duration_ns":50_000_000}],
    }
    return r


def manifests():
    base={
        "schema":"vh-switch-same-run-nro/v1",
        "git_sha":"f"*64,"run_id":321,"run_attempt":1,
        "nro_sha256":"c"*64,"nro_bytes":12345,
    }
    alt={
        "schema":"vh-switch-explicit-probe-phase/v1",
        "git_sha":"f"*64,"run_id":321,"run_attempt":1,
        "nro_sha256":"d"*64,"baseline_sha256":"c"*64,
        "phase":8,"nro_bytes":12346,
    }
    return base,alt


class TestRealServicePhases(unittest.TestCase):
    def test_both_queried_phases_and_distinct_manifest(self):
        b,a=manifests()
        report=compare_real_phases(model(0),model(8),b,a)
        self.assertEqual(report["phase0"]["service_query_count"],4)
        self.assertEqual(report["phase8"]["service_query_count"],3)
        self.assertEqual(report["phase8"][
            "successful_service_queries_with_nonzero_queue"],1)
        self.assertEqual(report["phase0"][
            "successful_service_queries_with_nonzero_queue"],0)
        self.assertTrue(report["no_unqueried_phase_service_occupancy_imputed"])
        self.assertFalse(report["causal_effect_of_query_phase_proven"])
        self.assertFalse(report["physical_switch_or_audible_playback_confirmed"])

    def test_rejects_unobserved_queue_count_promotion(self):
        for kind in ("unqueried","bad_phase","bad_clock","fake_failure","added"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                r=model(8)
                if kind=="unqueried":r["sample_records"][1]["attempt"]=18
                elif kind=="bad_phase":r["declared_query_phase"]=0
                elif kind=="bad_clock":r["sample_records"][1]["submit_begin_ns"]=1
                elif kind=="fake_failure":
                    r["sample_records"][1]["query_succeeded"]=False
                else:r["queue_probe_samples"]+=1
                inspect_observations(r,8)

    def test_rejects_manifest_mismatch(self):
        for kind in ("binary","run","commit","distinct","missing"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                base,alt=manifests()
                if kind=="binary":alt["baseline_sha256"]="a"*64
                elif kind=="run":alt["run_id"]+=1
                elif kind=="commit":alt["git_sha"]="e"*64
                elif kind=="distinct":alt["nro_sha256"]=base["nro_sha256"]
                else:alt["nro_bytes"]=0
                compare_real_phases(model(0),model(8),base,alt)

    def test_slow_subset_durations_reconciled(self):
        r=model(8)
        r["probed_slow_calls"][0]["duration_ns"]=39_000_000
        with self.assertRaises(CorrelationError):
            inspect_observations(r,8)
        r=model(8)
        r["probed_slow_calls"][0]["attempt"]=9
        with self.assertRaises(CorrelationError):
            inspect_observations(r,8)

    def test_bounded_failures_without_fake_zero(self):
        r=model(8)
        r["sample_records"][1]["query_succeeded"]=False
        r["sample_records"][1]["pre_submit_queue_count"]=None
        r["queue_probe_successes"]-=1
        r["queue_probe_failures"]=1
        output=inspect_observations(r,8)
        self.assertEqual(output["service_query_failure"],1)
        self.assertEqual(output["successful_service_queries_with_nonzero_queue"],0)
        self.assertEqual(output["service_query_success"],2)

    def test_previous_original_sd_cannot_be_relabeled(self):
        r=model(0)
        with self.assertRaises(CorrelationError):
            inspect_observations(r,8)
        r=model(8)
        r["guest_original_probe_sha256"]=model(0)["guest_original_probe_sha256"]
        with self.assertRaises(CorrelationError):
            inspect_observations(r,8)


if __name__=="__main__":
    unittest.main()
