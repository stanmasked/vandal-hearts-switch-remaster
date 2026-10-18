"""Stage290 matched-NRO probe summary negative controls (synthetic, not DAC)."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_idle_switch_service_probes import (
    _verified_observations,compare_modes
)


def sample(mode:str)->dict:
    data={
        "result":"GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED",
        "queue_probe_dropped":0,
        "scheduler_or_DAC_state_measured":False,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
        "pre_submit_queue_service_snapshot_only":True,
        "audout_attempts":34,
        "queue_probe_samples":3,
        "queue_probe_successes":3,
        "queue_probe_failures":0,
        "sample_records":[
            {"index":i,"attempt":1+16*i,"submit_begin_ns":100+i*100,
             "audio_second":i,"query_succeeded":True,
             "pre_submit_queue_count":0} for i in range(3)
        ],
        "probed_slow_calls":[],
        "scene_input_count":10 if mode=="switch" else 0,
    }
    if mode=="switch":
        data.update({
            "guest_original_probe_sha256":"a"*64,
            "copied_probe_sha256":"a"*64,
            "original_guest_sd_opened_in_current_workflow":True,
            "probe_samples_begin_within_500ms_of_input":1,
        })
        data["probed_slow_calls"].append({
            **data["sample_records"][1], "duration_ns":45_000_000
        })
    else:
        data["idle_original_sd_reverified_current_run"]=True
    return data


class PairedServiceProbeComparison(unittest.TestCase):
    def setUp(self):
        self.a=sample("switch")
        self.b=sample("idle")
        self.slow={
            "result":"GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED",
            "nro_sha256":"a"*64,
            "audout_attempts":34,
            "slow_calls_captured":1,
            "slow_ge50ms_count":0,
        }
        self.idle={
            "result":"ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED",
            "nro_sha256":"a"*64,
            "guest_audout_attempts":34,
            "slow_ge40ms_calls":0,
            "slow_ge50ms_calls":0,
            "physical_switch_tested":False,
        }

    def test_exact_two_mode_summary_and_sampling(self):
        report=compare_modes(self.a,self.b,self.slow,self.idle)
        self.assertEqual(report["switching"]["sample_count"],3)
        self.assertEqual(report["idle"]["sample_count"],3)
        self.assertEqual(report["switching"]["slow_call_sampled_ge40"],1)
        self.assertEqual(report["idle"]["slow_call_sampled_ge40"],0)
        self.assertEqual(report["switching"]["pre_submit_service_count_histogram"],{"0":3})
        self.assertFalse(report["sampling_randomized"])
        self.assertFalse(report["physical_console_audio_measured"])
        self.assertTrue(report["queue_zero_is_NOT_DAC_underrun_proof"])

    def test_invalid_prior_evidence_and_identity_rejected(self):
        for key in ("nro","scene","source","slow","idle_sd"):
            with self.subTest(key=key):
                a=copy.deepcopy(self.a)
                b=copy.deepcopy(self.b)
                slow=copy.deepcopy(self.slow)
                idle=copy.deepcopy(self.idle)
                if key=="nro":slow["nro_sha256"]="b"*64
                elif key=="scene":a["scene_input_count"]=9
                elif key=="source":a["copied_probe_sha256"]="b"*64
                elif key=="slow":slow["slow_calls_captured"]=0
                else:b["idle_original_sd_reverified_current_run"]=False
                with self.assertRaises(CorrelationError):
                    compare_modes(a,b,slow,idle)

    def test_sample_count_and_order_rejected(self):
        a=copy.deepcopy(self.a)
        a["sample_records"][1]["attempt"]=18
        with self.assertRaises(CorrelationError):
            compare_modes(a,self.b,self.slow,self.idle)
        b=copy.deepcopy(self.b)
        b["sample_records"][2]["index"]=1
        with self.assertRaises(CorrelationError):
            compare_modes(self.a,b,self.slow,self.idle)

    def test_pre_submit_queue_zero_not_hardware_output(self):
        a=copy.deepcopy(self.a)
        a["sample_records"][0]["pre_submit_queue_count"]=2
        actual=compare_modes(a,self.b,self.slow,self.idle)
        self.assertEqual(actual["switching"]["pre_submit_service_count_histogram"],
                         {"0":2,"2":1})
        self.assertFalse(actual["operating_system_scheduler_events_measured"])
        a["sample_records"][0]["pre_submit_queue_count"]=-1
        with self.assertRaises(CorrelationError):
            compare_modes(a,self.b,self.slow,self.idle)

    def test_bounded_slow_durations_and_subset(self):
        a=copy.deepcopy(self.a)
        a["probed_slow_calls"][0]["duration_ns"]=50_000_000
        self.slow["slow_ge50ms_count"]=1
        record=compare_modes(a,self.b,self.slow,self.idle)
        self.assertEqual(record["switching"]["slow_call_sampled_ge50"],1)
        a["probed_slow_calls"][0]["duration_ns"]=39_999_999
        with self.assertRaises(CorrelationError):
            compare_modes(a,self.b,self.slow,self.idle)


if __name__=="__main__":
    unittest.main()
