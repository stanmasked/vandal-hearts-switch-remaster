"""Stage291 synthetic 16-offset full-call slow-band phase checks."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_probe_phase_sensitivity import (
    phase_table,compare_phase_sensitivity
)


def base():
    observed={
        "audout_attempts":34,
        "sample_count":3,
        "slow_call_sampled_ge40":1,
        "slow_call_sampled_ge50":0,
    }
    slow=[
        {"attempt":1,"duration_ns":41_000_000,"returned":True},
        {"attempt":2,"duration_ns":53_000_000,"returned":True},
    ]
    table=phase_table(34,slow,observed)
    return {
        "attempts":34,"slow_ge40":2,"slow_ge50":1,
        "phase_table":table,
    }


def witnesses():
    switch=base()
    idle=copy.deepcopy(switch)
    verdict={
        "result":"SAME_NRO_ORIGINAL_SD_TWO_MODE_PROBE_COMPARISON_RECONCILED",
        "both_original_guest_sd_audited_this_workflow":True,
        "sampled_on_exact_every_sixteenth_call":True,
        "sampling_randomized":False,
        "scene_switch_causality_proven":False,
        "physical_console_audio_measured":False,
        "nro_sha256":"a"*64,
        "switching":{"audout_attempts":34,"slow_call_sampled_ge40":1,
                     "slow_call_sampled_ge50":0},
        "idle":{"audout_attempts":34,"slow_call_sampled_ge40":1,
                "slow_call_sampled_ge50":0},
    }
    slow={"result":"GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED",
          "nro_sha256":"a"*64}
    idle_verdict={"result":"ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED",
                  "nro_sha256":"a"*64}
    return switch,idle,verdict,slow,idle_verdict


class PhaseSensitivityRegression(unittest.TestCase):
    def test_full_16_phase_conservation(self):
        actual={"audout_attempts":34,"sample_count":3,
                "slow_call_sampled_ge40":1,"slow_call_sampled_ge50":0}
        calls=[
            {"attempt":1,"duration_ns":42_000_000,"returned":True},
            {"attempt":2,"duration_ns":53_000_000,"returned":True},
            {"attempt":18,"duration_ns":41_000_000,"returned":True},
        ]
        report=phase_table(34,calls,actual)
        self.assertEqual(len(report),16)
        self.assertEqual(sum(x["sampled_attempts_for_this_phase"]
                             for x in report),34)
        self.assertEqual(sum(x["source_slow_ge40"] for x in report),3)
        self.assertEqual(sum(x["source_slow_ge50"] for x in report),1)
        self.assertEqual(report[0]["sampled_attempts_for_this_phase"],3)
        self.assertEqual(report[1]["source_slow_ge40"],2)
        self.assertTrue(report[0]["queue_service_count_actually_observed"])
        self.assertTrue(all(x["hypothetical_phase_is_NOT_queue_data"]
                            for x in report[1:]))

    def test_negative_slow_and_duplicate_attempts_rejected(self):
        actual={"audout_attempts":34,"sample_count":3,
                "slow_call_sampled_ge40":1,"slow_call_sampled_ge50":0}
        original={"attempt":1,"duration_ns":42_000_000,"returned":True}
        for calls in ([original,original],
                      [{**original,"attempt":35}],
                      [{**original,"duration_ns":39_999_999}],
                      [{**original,"returned":False}]):
            with self.subTest(calls=calls),self.assertRaises(CorrelationError):
                phase_table(34,calls,actual)

    def test_all_phase_comparison_not_significance(self):
        inputs=witnesses()
        result=compare_phase_sensitivity(*inputs)
        self.assertEqual(result["phase_exact_tie_count"],16)
        self.assertEqual(result["phase_positive_count"],0)
        self.assertTrue(result["other_phase_queue_counts_are_NOT_measured"])
        self.assertFalse(result["audio_scheduler_DAC_or_audible_underruns_measured"])

    def test_original_same_nro_and_sampler_identity(self):
        switch,idle,report,slow,verdict=witnesses()
        for mutation in ("nro","random","count","queues"):
            with self.subTest(mutation=mutation):
                r=copy.deepcopy(report)
                s=copy.deepcopy(switch)
                sl=copy.deepcopy(slow)
                if mutation=="nro":sl["nro_sha256"]="b"*64
                elif mutation=="random":r["sampling_randomized"]=True
                elif mutation=="count":s["slow_ge40"]=0
                else:r["both_original_guest_sd_audited_this_workflow"]=False
                with self.assertRaises(CorrelationError):
                    compare_phase_sensitivity(s,idle,r,sl,verdict)

    def test_actual_probe_phase0_mismatch_rejected(self):
        actual={"audout_attempts":34,"sample_count":4,
                "slow_call_sampled_ge40":1,"slow_call_sampled_ge50":0}
        with self.assertRaises(CorrelationError):
            phase_table(34,[{"attempt":1,"duration_ns":41_000_000,
                             "returned":True}],actual)


if __name__=="__main__":
    unittest.main()
