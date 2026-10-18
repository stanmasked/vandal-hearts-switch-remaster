"""Stage296 synthetic checks for authentic phase order reversal."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from audit_nexium_phase_order_reversal import audit_four_sessions
from test_compare_nexium_real_queue_phases import model,manifests


def inputs():
    p0=model(0)
    p8=model(8)
    p8_reverse=model(8)
    p0_reverse=model(0)
    p8_reverse["guest_original_probe_sha256"]="3"*64
    p8_reverse["copied_probe_sha256"]="3"*64
    p0_reverse["guest_original_probe_sha256"]="4"*64
    p0_reverse["copied_probe_sha256"]="4"*64
    p8_reverse["probed_slow_calls"]=[]
    p0_reverse["probed_slow_calls"]=[]
    base,alt=manifests()
    return p0,p8,p8_reverse,p0_reverse,base,alt


class ReversePhaseOrderSyntheticTests(unittest.TestCase):
    def test_exact_four_distinct_original_sds(self):
        result=audit_four_sessions(*inputs())
        self.assertEqual(result["capture_sequence"],[
            "phase0_first","phase8_first","phase8_reversed",
            "phase0_reversed"])
        self.assertEqual([r["phase"] for r in result["session_records"]],
                         [0,8,8,0])
        self.assertEqual(result["total_queried_attempts"],14)
        self.assertTrue(result["all_four_guest_SD_probe_sha256_distinct"])
        self.assertFalse(result["causal_effect_of_phase_or_order_proven"])
        self.assertFalse(result["physical_switch_audio_or_DAC_underrun_measured"])

    def test_relabel_or_recycle_guest_sd_rejected(self):
        values=inputs()
        bad=list(copy.deepcopy(values))
        bad[2]["guest_original_probe_sha256"]=bad[1][
            "guest_original_probe_sha256"]
        bad[2]["copied_probe_sha256"]=bad[1]["copied_probe_sha256"]
        with self.assertRaises(CorrelationError):
            audit_four_sessions(*bad)
        bad=list(copy.deepcopy(values))
        bad[3]=copy.deepcopy(bad[0])
        with self.assertRaises(CorrelationError):
            audit_four_sessions(*bad)

    def test_wrong_phase_order_rejected(self):
        v=list(inputs())
        v[2],v[3]=v[3],v[2]
        with self.assertRaises(CorrelationError):
            audit_four_sessions(*v)

    def test_nro_run_and_hash_mutations_rejected(self):
        for mode in ("hash","run","attempt"):
            with self.subTest(mode=mode),self.assertRaises(CorrelationError):
                v=list(copy.deepcopy(inputs()))
                if mode=="hash":v[5]["baseline_sha256"]="e"*64
                elif mode=="run":v[5]["run_id"]+=1
                else:v[5]["run_attempt"]+=1
                audit_four_sessions(*v)

    def test_exact_denominator_and_no_fake_queues(self):
        v=list(copy.deepcopy(inputs()))
        v[3]["queue_probe_samples"]+=1
        with self.assertRaises(CorrelationError):
            audit_four_sessions(*v)
        v=list(copy.deepcopy(inputs()))
        v[2]["sample_records"][0]["query_succeeded"]=False
        # Unsuccessful service queries may not be assigned ANY count.
        # Leaving the original count in place must fail strictly.
        with self.assertRaises(CorrelationError):
            audit_four_sessions(*v)

    def test_source_clocks_never_aligned_across_runs(self):
        v=list(copy.deepcopy(inputs()))
        # No cross-run monotonicity is claimed. Individual clocks remain
        # strict, but the start of a new NRO is a new independent epoch.
        v[3]["sample_records"][0]["submit_begin_ns"]=999
        r=audit_four_sessions(*v)
        self.assertTrue(r["different_guest_clocks_not_aligned"])
        self.assertTrue(r["capture_order_not_randomized"])


if __name__=="__main__":
    unittest.main()
