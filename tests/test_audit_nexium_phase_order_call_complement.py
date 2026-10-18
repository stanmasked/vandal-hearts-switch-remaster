"""Stage298 exact duration-class complement synthetic regressions."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from audit_nexium_phase_order_full_call_rates import compare_complete
from audit_nexium_phase_order_call_complement import (
    complement_profile,compare_complements
)
from test_audit_nexium_phase_order_full_call_rates import fixture


def authentic_synthetic():
    witness,profiles=fixture()
    full=compare_complete(witness,profiles)
    return witness,full,profiles


class CallComplementRegression(unittest.TestCase):
    def test_exact_slow_counts_and_offphase_denominators(self):
        witness,full,source=authentic_synthetic()
        result=compare_complements(witness,full,source)
        self.assertEqual(result["result"],
                         "FOUR_ORIGINAL_SD_ACTUAL_VS_OTHER15_SLOW_CALLS_RECONCILED")
        self.assertEqual([r["phase"] for r in result["sessions"]],[0,8,8,0])
        self.assertEqual(result["sessions"][0]["ge40"]["queried_slow_count"],1)
        self.assertEqual(result["sessions"][0]["ge40"]["other_15_phases_slow_count"],4)
        self.assertEqual(result["sessions"][2]["ge40"]["other_15_phases_slow_count"],6)
        self.assertTrue(result["exact_integer_count_partition_and_fraction_weighting"])
        self.assertFalse(result["offphase_queue_service_counts_observed"])
        self.assertFalse(result["physical_switch_DAC_or_audible_glitches_measured"])

    def test_full_source_conservation_under_order_reversal(self):
        witness,full,source=authentic_synthetic()
        result=compare_complements(witness,full,source)
        self.assertEqual(set(result["phase0_vs_phase8_by_capture_pair"]),
                         {"first_pair","reversed_pair"})
        for session in result["sessions"]:
            self.assertEqual(
                session["ge40"]["all_call_slow_count"],
                session["ge40"]["queried_slow_count"]+
                session["ge40"]["other_15_phases_slow_count"])
            self.assertEqual(
                session["all_call_attempts"],
                session["actually_queried_attempts"]+
                session["other_15_phases_attempts"])

    def test_malformed_counts_and_thresholds_fail_closed(self):
        for mode in ("too_many","negative","nested","phase","denominator"):
            with self.subTest(mode=mode),self.assertRaises(CorrelationError):
                _,_,sources=authentic_synthetic()
                row=copy.deepcopy(sources[0])
                if mode=="too_many":row["slow_ge40_queried"]+=40
                elif mode=="negative":row["slow_ge40_all_calls"]=-1
                elif mode=="nested":
                    row["slow_ge50_all_calls"]=row["slow_ge40_all_calls"]+1
                elif mode=="phase":row["phase"]=8
                else:row["sample_count"]+=1
                complement_profile(row)

    def test_modified_stage297_source_witness_is_refused(self):
        for kind in ("count","hash","cause","random"):
            with self.subTest(kind=kind),self.assertRaises(CorrelationError):
                original,stage297,sources=authentic_synthetic()
                previous=copy.deepcopy(stage297)
                if kind=="count":previous["sessions"][0]["full_slow_ge40"]+=1
                elif kind=="hash":previous["sessions"][2]["source_original_slow_sha256"]="x"*64
                elif kind=="cause":
                    previous["phase_or_music_switch_causality_proven"]=True
                else:original["capture_sequence"]=["phase0_first"]*4
                compare_complements(original,previous,sources)

    def test_exactly_reproducible_and_no_hardware_claims(self):
        args=authentic_synthetic()
        a=compare_complements(*args)
        self.assertEqual(a,compare_complements(*args))
        self.assertFalse(a["capture_order_randomized"])
        self.assertFalse(a["causal_audio_effect_proven"])
        self.assertFalse(a["offphase_queue_service_values_imputed"])


if __name__=="__main__":
    unittest.main()
