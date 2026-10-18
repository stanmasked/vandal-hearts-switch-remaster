"""Stage293 deterministic 16-attempt slow-call cycle regressions."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_probe_phase_sensitivity import phase_table
from analyze_nexium_phase_selection_gap import analyse_selection_gap
from analyze_nexium_slow_call_cycle_occupancy import (
    cycle_profile,analyse_cycle_occupancy
)
from test_analyze_nexium_phase_selection_gap import synthetic


def records(mode:str):
    if mode=="switching":
        attempts=[1,2,18]
        durations=[41_000_000,51_000_000,48_000_000]
    else:
        attempts=[1,17]
        durations=[53_000_000,41_000_000]
    return [
        {"attempt":n,"begin_ns":1_000_000_000+i*100_000_000,
         "duration_ns":duration,"returned":True}
        for i,(n,duration) in enumerate(zip(attempts,durations))
    ]


class CycleOccupancyRegressions(unittest.TestCase):
    def setUp(self):
        self.phase,self.witness=synthetic()
        self.selection=analyse_selection_gap(self.phase,self.witness)
        self.switching=records("switching")
        self.idle=records("idle")

    def audit(self,phase=None,selection=None):
        return analyse_cycle_occupancy(
            self.phase if phase is None else phase,self.witness,
            self.selection if selection is None else selection,
            self.switching,self.idle)

    def test_complete_and_partial_cycles_with_nonzero_offphase_calls(self):
        report=self.audit()
        s=report["switching"]
        idle=report["idle"]
        self.assertEqual(s["total_cycles"],3)
        self.assertEqual(s["full_cycles"],2)
        self.assertEqual(s["final_partial_cycle_attempts"],2)
        self.assertEqual(s["cycles_with_any_ge40"],2)
        self.assertEqual(s["cycles_with_multiple_ge40"],1)
        self.assertEqual(s["cycles_with_slow_at_actual_phase0"],1)
        self.assertEqual(s["cycles_with_slow_only_off_actual_phase0"],1)
        self.assertEqual(s["slow_calls_on_unqueried_phases"],2)
        self.assertEqual(s["adjacent_slow_call_attempt_pairs"],1)
        self.assertEqual(idle["cycles_with_any_ge40"],2)
        self.assertEqual(idle["cycles_with_slow_only_off_actual_phase0"],0)
        self.assertEqual(report[
            "switch_minus_idle_nonempty_cycle_rate_per_1000_cycles"],0.0)
        self.assertFalse(report["unqueried_phase_queue_values_imputed"])
        self.assertFalse(report["physical_console_playback_verified"])

    def test_exact_reproducibility(self):
        self.assertEqual(self.audit(),self.audit())

    def test_unverified_stage292_rejected(self):
        bad=copy.deepcopy(self.selection)
        bad["modes"]["switching"]["ge40"][
            "full_session_slow_call_count"]+=1
        with self.assertRaises(CorrelationError):
            self.audit(selection=bad)

    def test_repeated_or_reordered_attempts_rejected(self):
        for mutation in ("duplicate","order","clock","duration","returned"):
            with self.subTest(mutation=mutation):
                calls=copy.deepcopy(self.switching)
                if mutation=="duplicate":
                    calls[1]["attempt"]=1
                elif mutation=="order":
                    calls[1],calls[2]=calls[2],calls[1]
                elif mutation=="clock":
                    calls[1]["begin_ns"]=calls[0]["begin_ns"]
                elif mutation=="duration":
                    calls[1]["duration_ns"]=39_000_000
                else:
                    calls[0]["returned"]=False
                with self.assertRaises(CorrelationError):
                    cycle_profile(34,calls,self.phase["switching"],
                                  self.witness["switching"])

    def test_bad_denominators_and_phase0_scope_rejected(self):
        bad=copy.deepcopy(self.witness["switching"])
        bad["slow_call_sampled_ge40"]=2
        with self.assertRaises(CorrelationError):
            cycle_profile(34,self.switching,self.phase["switching"],bad)
        with self.assertRaises(CorrelationError):
            cycle_profile(33,self.switching,self.phase["switching"],
                          self.witness["switching"])

    def test_cannot_promote_cycle_occupancy_to_dac_or_causality(self):
        result=self.audit()
        self.assertTrue(result["cycle_occupancy_not_scheduler_execution_timing"])
        self.assertTrue(result["cycle_groups_not_independent_randomized_experiments"])
        self.assertFalse(result["OS_scheduler_events_or_DAC_underruns_measured"])
        self.assertFalse(result["musical_scene_switch_causality_proven"])


if __name__=="__main__":
    unittest.main()
