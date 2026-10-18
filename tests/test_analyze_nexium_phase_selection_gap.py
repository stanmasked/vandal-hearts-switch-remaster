"""Stage292 exact full-call versus measured deterministic phase-zero rates."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_probe_phase_sensitivity import phase_table,compare_phase_sensitivity
from analyze_nexium_phase_selection_gap import analyse_selection_gap


def synthetic():
    switch_calls=[
        {"attempt":1,"duration_ns":41_000_000,"returned":True},
        {"attempt":2,"duration_ns":51_000_000,"returned":True},
        {"attempt":18,"duration_ns":48_000_000,"returned":True},
    ]
    idle_calls=[
        {"attempt":1,"duration_ns":53_000_000,"returned":True},
        {"attempt":17,"duration_ns":41_000_000,"returned":True},
    ]
    def make(calls,ge40,ge50):
        sampled={"audout_attempts":34,"sample_count":3,
                 "slow_call_sampled_ge40":ge40,
                 "slow_call_sampled_ge50":ge50}
        return {"attempts":34,"slow_ge40":len(calls),
                "slow_ge50":sum(c["duration_ns"]>=50_000_000 for c in calls),
                "phase_table":phase_table(34,calls,sampled)}
    switch=make(switch_calls,1,0)
    idle=make(idle_calls,2,1)
    witnesses={
        "result":"SAME_NRO_ORIGINAL_SD_TWO_MODE_PROBE_COMPARISON_RECONCILED",
        "both_original_guest_sd_audited_this_workflow":True,
        "sampled_on_exact_every_sixteenth_call":True,
        "sampling_randomized":False,
        "scene_switch_causality_proven":False,
        "physical_console_audio_measured":False,
        "nro_sha256":"a"*64,
        "switching":{
            "audout_attempts":34,"sample_count":3,
            "slow_call_sampled_ge40":1,"slow_call_sampled_ge50":0
        },
        "idle":{
            "audout_attempts":34,"sample_count":3,
            "slow_call_sampled_ge40":2,"slow_call_sampled_ge50":1
        },
    }
    slow={"result":"GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED",
          "nro_sha256":"a"*64}
    idle_verdict={"result":"ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED",
                  "nro_sha256":"a"*64}
    report=compare_phase_sensitivity(
        switch,idle,witnesses,slow,idle_verdict)
    return report,witnesses


class PhaseSelectionGapRegressions(unittest.TestCase):
    def test_weighted_phase_identity_and_exact_disjoint_classes(self):
        stage,witness=synthetic()
        result=analyse_selection_gap(stage,witness)
        self.assertEqual(result["result"],
                         "MEASURED_PHASE_ZERO_VS_ALL_AUDOUT_CALLS_RECONCILED")
        self.assertEqual(result["modes"]["switching"]["ge40"][
            "full_session_slow_call_count"],3)
        self.assertEqual(result["modes"]["idle"]["ge40"][
            "actual_phase0_slow_call_count"],2)
        self.assertAlmostEqual(result["bands"]["ge40"][
            "actual_phase0_switch_minus_idle_per_1000"],-1000/3,places=5)
        self.assertAlmostEqual(result["bands"]["ge40"][
            "all_calls_switch_minus_idle_per_1000"],1000/34,places=5)
        self.assertTrue(result["exact_fraction_weighted_phase_identity"])
        self.assertFalse(result["other_phase_queue_counts_imputed"])
        self.assertFalse(result["physical_switch_tested"])

    def test_repeat_exactly(self):
        stage,witness=synthetic()
        self.assertEqual(analyse_selection_gap(stage,witness),
                         analyse_selection_gap(stage,witness))

    def test_tampered_phase_count_or_denominator_rejected(self):
        stage,witness=synthetic()
        for kind in ("count","size","order","measured","rate"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                changed=copy.deepcopy(stage)
                phase=changed["switching"]["phase_table"]
                if kind=="count":phase[1]["source_slow_ge40"]+=1
                elif kind=="size":phase[1]["sampled_attempts_for_this_phase"]+=1
                elif kind=="order":phase[0]["phase_offset_zero_based"]=5
                elif kind=="measured":phase[0]["queue_service_count_actually_observed"]=False
                else:phase[0]["ge40_rate_per_1000"]+=0.01
                analyse_selection_gap(changed,witness)

    def test_stage291_report_and_causal_claims_rejected(self):
        stage,witness=synthetic()
        for kind in ("nro","random","hardware","stage"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                a=copy.deepcopy(stage)
                w=copy.deepcopy(witness)
                if kind=="nro":w["nro_sha256"]="b"*64
                elif kind=="random":w["sampling_randomized"]=True
                elif kind=="hardware":a["audio_scheduler_DAC_or_audible_underruns_measured"]=True
                else:a["result"]="UNVERIFIED"
                analyse_selection_gap(a,w)

    def test_source_phase0_matches_actual_service_probes(self):
        stage,witness=synthetic()
        witness["idle"]["slow_call_sampled_ge40"]=1
        with self.assertRaises(CorrelationError):
            analyse_selection_gap(stage,witness)

    def test_phase0_and_whole_duration_difference_is_not_estimator_bias(self):
        stage,witness=synthetic()
        out=analyse_selection_gap(stage,witness)
        self.assertTrue(out["sample_selection_gap_not_statistical_estimator_bias"])
        self.assertFalse(out["randomized_significance_test"])
        self.assertTrue(out["session_switching_preceded_idle"])
        self.assertFalse(out["music_scene_switch_causality_proven"])


if __name__=="__main__":
    unittest.main()
