"""Stage332 all 0..3 exclusions from authentic PlayBuffer last-16 software calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))
from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage332_original_playbuffer_frontier import (
    compare_frontiers,cohort_frontier,RESULT,
)
from test_compare_nexium_stage328_original_playbuffer_histories import (
    cohort,pin,pin_last,
)
from test_audit_nexium_stage329_guest_software_dispersion import heterogeneous


class AuthenticSoftwareCallSubsetFrontierTests(unittest.TestCase):
    def setUp(self):
        self.a=cohort()
        self.b=cohort(last_duration=22352500,prior_duration=31247083,total=382)

    def audit(self,a=None,b=None,first_history_sha=None,second_history_sha=None,
              first_last_sha=None,second_last_sha=None):
        a=self.a if a is None else a
        b=self.b if b is None else b
        return compare_frontiers(
            a,b,pin(a) if first_history_sha is None else first_history_sha,
            pin(b) if second_history_sha is None else second_history_sha,
            pin_last(a) if first_last_sha is None else first_last_sha,
            pin_last(b) if second_last_sha is None else second_last_sha)

    def test_uniform_software_history_has_all_expected_exact_combinations(self):
        r=self.audit()
        self.assertEqual(r["result"],RESULT)
        self.assertEqual(r["subset_count_per_cohort"],576)
        for c in r["cohorts"]:
            frontier=c["source_subset_sensitivity_frontier"]
            self.assertEqual([x["subset_count"] for x in frontier],[1,15,105,455])
            self.assertEqual([x["retained_previous_calls_per_subset"] for x in frontier],
                             [15,14,13,12])
            self.assertTrue(all(x["final_shorter_than_all_subsets"] for x in frontier))
            self.assertEqual(c["largest_checked_exclusion_k_with_all_subsets_shorter"],3)
            self.assertIsNone(c["first_checked_k_not_stable"])
            self.assertTrue(c["cannot_extrapolate_beyond_three_deleted_calls"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_measured"])

    def test_nonuniform_guest_history_first_loss_of_all_subset_stability_at_three(self):
        altered=heterogeneous(self.a,[x*1_000_000 for x in
            (5,6,7,8,9,10,12,20,30,31,32,33,34,35,36)])
        result=self.audit(a=altered)["cohorts"][0]
        frontier=result["source_subset_sensitivity_frontier"]
        self.assertEqual(frontier[3]["lower_median_min_software_ns"],10_000_000)
        self.assertEqual(frontier[3]["lower_median_max_software_ns"],30_000_000)
        self.assertEqual(frontier[3]["final_first_possible_rank_min"],4)
        self.assertEqual(frontier[3]["final_first_possible_rank_max"],7)
        self.assertTrue(frontier[2]["final_shorter_than_all_subsets"])
        self.assertFalse(frontier[3]["final_shorter_than_all_subsets"])
        self.assertEqual(result["largest_checked_exclusion_k_with_all_subsets_shorter"],2)
        self.assertEqual(result["first_checked_k_not_stable"],3)
        self.assertGreater(frontier[3]["subsets_with_final_longer_than_median"],0)
        self.assertGreater(frontier[3]["subsets_with_final_shorter_than_median"],0)

    def test_three_removed_guest_source_rows_preserve_equal_and_rank(self):
        duration=self.a["stage320"]["last_successful_PlayBuffer_software_duration_ns"]
        altered=heterogeneous(self.a,[duration]*3+[duration+5000000]*12)
        r=self.audit(a=altered)["cohorts"][0]
        for stage in r["source_subset_sensitivity_frontier"]:
            self.assertEqual(stage["final_first_possible_rank_min"],1)
            self.assertEqual(stage["final_first_possible_rank_max"],1)
            self.assertTrue(stage["final_shorter_than_all_subsets"])

    def test_four_stage_source_audits_crosscheck_one_and_two_deletion_medians(self):
        r=self.audit()
        for c,reference in zip(r["cohorts"],[32154011,31247083]):
            d=c["source_subset_sensitivity_frontier"]
            self.assertEqual(d[0]["lower_median_min_software_ns"],reference)
            self.assertEqual(d[1]["subset_count"],15)
            self.assertEqual(d[2]["subset_count"],105)
            self.assertEqual(d[3]["subset_count"],455)
        self.assertTrue(r["independent_original_stage328_to_331_source_replays_match"])

    def test_forged_original_history_csv_sha256_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(first_history_sha="0"*64)

    def test_forged_original_last_success_csv_sha256_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(second_last_sha="0"*64)

    def test_stage320_original_guest_last_call_tampering_rejected(self):
        corrupt=copy.deepcopy(self.a)
        corrupt["stage320"]["last_successful_PlayBuffer_return_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(a=corrupt)

    def test_stage322_original_guest_history_report_tampering_rejected(self):
        corrupt=copy.deepcopy(self.b)
        corrupt["stage322"]["original_call_rows"][0]["duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(b=corrupt)

    def test_corrupt_original_guest_history_csv_rejected(self):
        corrupt=copy.deepcopy(self.a)
        corrupt["history_csv"]+=b"fake\n"
        with self.assertRaises(ExitTimelineError):
            self.audit(a=corrupt)

    def test_two_identical_original_source_cohorts_not_independent(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(b=self.a)

    def test_last_call_is_never_excluded_from_any_subset(self):
        r=self.audit()
        for c in r["cohorts"]:
            self.assertEqual(c["retained_normal_successful_guest_software_calls"],16)
            self.assertEqual([x["retained_previous_calls_per_subset"] for x in
                              c["source_subset_sensitivity_frontier"]],[15,14,13,12])
            self.assertEqual(c["source_subset_sensitivity_frontier"][3]["subset_count"],455)

    def test_no_absolute_guest_epochs_or_pcm_or_sound_covered(self):
        s=json.dumps(self.audit(),sort_keys=True)
        self.assertNotIn("begin_guest_ns",s)
        self.assertNotIn("end_guest_ns",s)
        self.assertNotIn("pcm_bytes",s)
        self.assertNotIn("1000000000",s)
        self.assertTrue(self.audit()["no_population_confidence_or_audio_latency_guarantee"])
        self.assertFalse(self.audit()["original_soundtrack_or_audible_audio_verified"])


if __name__=="__main__":
    unittest.main()
