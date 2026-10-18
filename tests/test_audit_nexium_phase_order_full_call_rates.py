"""Stage297 exact four-source full-call rate versus sampled-call tests."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from audit_nexium_phase_order_reversal import audit_four_sessions
from audit_nexium_phase_order_full_call_rates import compare_complete
from test_audit_nexium_phase_order_reversal import inputs


def fixture():
    stage=audit_four_sessions(*inputs())
    profiles=[]
    for i,row in enumerate(stage["session_records"]):
        sampled=row["slow_ge40_on_queried_attempts"]
        ge50=row["slow_ge50_on_queried_attempts"]
        profiles.append({
            "phase":row["phase"],
            "audout_attempts":row["audout_attempts"],
            "sample_count":row["service_query_count"],
            "slow_ge40_all_calls":sampled+4+i,
            "slow_ge50_all_calls":ge50+1,
            "slow_ge40_queried":sampled,
            "slow_ge50_queried":ge50,
            "original_slow_csv_sha256":str(i+1)*64,
            "original_probe_csv_sha256":row["original_guest_probe_sha256"],
            "source_guest_SD_reread_and_verified":True,
        })
    return stage,profiles


class ExactOriginalFullCallVsSampleTests(unittest.TestCase):
    def test_four_rates_and_distinct_sources(self):
        stage,profiles=fixture()
        r=compare_complete(stage,profiles)
        self.assertEqual(r["result"],
                         "FOUR_REAL_GUEST_SD_FULL_AUDOUT_VS_QUERIED_RATES_VERIFIED")
        self.assertEqual(len(r["sessions"]),4)
        self.assertEqual([x["queried_slow_ge40"] for x in r["sessions"]],[1,1,0,0])
        self.assertTrue(r["queried_slow_call_IDs_exact_subset_of_full_calls"])
        self.assertFalse(r["DAC_underruns_or_physical_Switch_audio_measured"])
        self.assertFalse(r["phase_or_music_switch_causality_proven"])

    def test_tampered_source_hash_and_attempt_count_rejected(self):
        for mode in ("hash","attempts","phase","sample"):
            with self.subTest(mode=mode),self.assertRaises(CorrelationError):
                stage,prof=fixture()
                if mode=="hash":prof[1]["original_probe_csv_sha256"]="d"*64
                if mode=="attempts":prof[1]["audout_attempts"]+=2
                if mode=="phase":prof[1]["phase"]=0
                if mode=="sample":prof[1]["slow_ge40_queried"]+=1
                compare_complete(stage,prof)

    def test_reject_nonconserved_slow_bands(self):
        stage,prof=fixture()
        prof[0]["slow_ge50_all_calls"]=prof[0]["slow_ge40_all_calls"]+1
        with self.assertRaises(CorrelationError):
            compare_complete(stage,prof)
        stage,prof=fixture()
        prof[0]["slow_ge40_all_calls"]=-1
        with self.assertRaises(CorrelationError):
            compare_complete(stage,prof)

    def test_refuse_unverified_order_or_hardware_claim(self):
        for kind in ("result","source","dac","causality"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                stage,prof=fixture()
                if kind=="result":stage["result"]="NOT VERIFIED"
                elif kind=="source":stage["all_four_guest_SD_sources_originally_audited"]=False
                elif kind=="dac":stage["physical_switch_audio_or_DAC_underrun_measured"]=True
                else:stage["causal_effect_of_phase_or_order_proven"]=True
                compare_complete(stage,prof)

    def test_report_is_exactly_reproducible(self):
        stage,prof=fixture()
        self.assertEqual(compare_complete(stage,prof),compare_complete(stage,prof))


if __name__=="__main__":
    unittest.main()
