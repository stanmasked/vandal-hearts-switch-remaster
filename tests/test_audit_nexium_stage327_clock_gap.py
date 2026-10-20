"""Stage327 independent host clock gap diagnostic negative controls.

Synthetic receipts are derived from Stage326's independent source replayer.
No actual PCM samples or physical/audio assertions.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_host_clock_pairs import ClockPairError
from compare_nexium_stage326_original_host_clocks import compare_cohorts
from audit_nexium_stage327_clock_gap import (
    audit_stage326_clock_disagreement,THRESHOLD_NS,
)
from test_compare_nexium_stage326_original_host_clocks import sample,pins


class Stage327ClockGapTests(unittest.TestCase):
    def setUp(self):
        first=sample(100000,sizes=(100000,101000,120000),
                     wall_intervals=(357,4270),
                     monotonic_intervals=(357687151,4269790190))
        second=sample(200000,sizes=(200000,201600,240000),
                      wall_intervals=(358,4286),
                      monotonic_intervals=(357696182,4285779743))
        self.source=compare_cohorts(first,second,
                                    first_pins=pins(first),second_pins=pins(second))

    def derive(self,other=None):
        return audit_stage326_clock_disagreement(
            self.source if other is None else other)

    def test_verified_exact_gap_values_from_synthetic_source(self):
        r=self.derive()
        self.assertEqual(r["result"],
                         "STAGE327_TWO_ORIGINAL_HOST_CLOCK_INTERVAL_GAPS_CLASSIFIED")
        self.assertEqual([
            (x["first_host_wall_minus_monotonic_interval_ns"],
             x["second_host_wall_minus_monotonic_interval_ns"])
            for x in r["interval_disagreements"]],
            [(-687151,303818),(209810,220257)])
        self.assertEqual([x["second_minus_first_discrepancy_ns"]
                          for x in r["interval_disagreements"]],[990969,10447])
        self.assertFalse(any(
            x["first_exceeds_illustrative_one_ms_gap"] or
            x["second_exceeds_illustrative_one_ms_gap"]
            for x in r["interval_disagreements"]))
        self.assertTrue(r["one_ms_threshold_is_heuristic_not_guaranteed_sampling_bound"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_positive_host_wall_clocks_can_still_have_gap_candidate(self):
        changed=copy.deepcopy(self.source)
        row=changed["original_control_pair_comparison"][0]
        row["second_wall_delta_ms"]+=2000
        row["second_minus_first_wall_delta_ms"]+=2000
        r=self.derive(changed)
        self.assertTrue(r["interval_disagreements"][0][
            "second_exceeds_illustrative_one_ms_gap"])
        self.assertFalse(r["interval_disagreements"][0][
            "first_exceeds_illustrative_one_ms_gap"])
        self.assertTrue(r["all_original_stage326_source_scope_flags_conserved"])

    def test_invalid_or_missing_source_scope_flags_rejected(self):
        cases=(
            ("each_original_stage325_receipt_recomputed_from_original_csv",False),
            ("each_original_stage304_host_controls_matched_strict_receipt",False),
            ("each_original_stage305_success_receipt_present",False),
            ("entire_stage304_or_stage305_pcm_chain_independently_rerun",True),
            ("guest_to_host_clock_alignment_proven",True),
            ("sound_latency_or_dropout_verified",True),
            ("physical_Nintendo_Switch_audio_tested",True),
            ("result","FAKE_SUCCESS"),
            ("schema","FAKE_STAGE326_SCHEMA"),
        )
        for field,value in cases:
            changed=copy.deepcopy(self.source)
            changed[field]=value
            with self.subTest(field=field),self.assertRaises(ClockPairError):
                self.derive(changed)

    def test_changed_source_pins_rejected(self):
        changed=copy.deepcopy(self.source)
        changed["first_source_sha256"]["legacy"]="bad"
        with self.assertRaises(ClockPairError):
            self.derive(changed)

    def test_equal_cohort_pins_rejected(self):
        changed=copy.deepcopy(self.source)
        changed["second_source_sha256"]=copy.deepcopy(
            changed["first_source_sha256"])
        with self.assertRaises(ClockPairError):
            self.derive(changed)

    def test_duplicate_or_missing_original_events_rejected(self):
        for mutation in ("missing","swapped","extra"):
            changed=copy.deepcopy(self.source)
            rows=changed["original_control_pair_comparison"]
            if mutation=="missing":
                del rows[1]
            elif mutation=="swapped":
                rows.reverse()
            else:
                rows.append(copy.deepcopy(rows[1]))
            with self.subTest(mutation=mutation),self.assertRaises(ClockPairError):
                self.derive(changed)

    def test_forged_intercohort_difference_rejected(self):
        changed=copy.deepcopy(self.source)
        changed["original_control_pair_comparison"][0][
            "second_minus_first_monotonic_delta_ns"]+=1000
        with self.assertRaises(ClockPairError):
            self.derive(changed)

    def test_nonpositive_or_bogus_host_intervals_rejected(self):
        for key,value in (
            ("first_wall_delta_ms",0),
            ("second_monotonic_delta_ns",-1),
            ("second_pcm_file_size_delta_bytes",0),
            ("first_monotonic_delta_ns",True)):
            changed=copy.deepcopy(self.source)
            changed["original_control_pair_comparison"][0][key]=value
            with self.subTest(key=key),self.assertRaises(ClockPairError):
                self.derive(changed)

    def test_heuristic_is_not_converted_to_strict_source_failure(self):
        changed=copy.deepcopy(self.source)
        row=changed["original_control_pair_comparison"][1]
        row["first_monotonic_delta_ns"]-=20_000_000
        row["second_minus_first_monotonic_delta_ns"]+=20_000_000
        result=self.derive(changed)
        self.assertTrue(result["interval_disagreements"][1][
            "first_exceeds_illustrative_one_ms_gap"])
        self.assertEqual(result["diagnostic_one_ms_threshold_ns"],THRESHOLD_NS)
        self.assertFalse(result["guest_audio_timing_or_clock_causality_proven"])

    def test_no_absolute_host_epoch_or_audio_source_in_public_report(self):
        text=json.dumps(self.derive(),sort_keys=True)
        self.assertNotIn("1712345678000",text)
        self.assertNotIn("123450000000",text)
        self.assertNotIn("original_pcm",text)
        self.assertFalse(self.derive()["absolute_host_wall_epochs_exposed"])


if __name__=="__main__":
    unittest.main()
