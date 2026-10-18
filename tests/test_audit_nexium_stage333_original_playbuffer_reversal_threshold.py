"""Stage333 independent pinned guest call median reversal threshold regressions."""
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
from audit_nexium_stage333_original_playbuffer_reversal_threshold import (
    compare_thresholds,source_threshold,RESULT,
)
from test_compare_nexium_stage328_original_playbuffer_histories import (
    cohort,pin,pin_last,
)
from test_audit_nexium_stage329_guest_software_dispersion import heterogeneous

class AuthenticOriginalPlayBufferReversalTests(unittest.TestCase):
    def setUp(self):
        self.a=cohort()
        self.b=cohort(last_duration=22352500,prior_duration=31247083,total=382)

    def audit(self,a=None,b=None,first_history_sha=None,second_history_sha=None,
              first_last_sha=None,second_last_sha=None):
        a=self.a if a is None else a
        b=self.b if b is None else b
        return compare_thresholds(
            a,b,pin(a) if first_history_sha is None else first_history_sha,
            pin(b) if second_history_sha is None else second_history_sha,
            pin_last(a) if first_last_sha is None else first_last_sha,
            pin_last(b) if second_last_sha is None else second_last_sha)

    def test_bounded_uniform_original_guest_calls_prove_nonempty_subset_inequality(self):
        doc=self.audit()
        self.assertEqual(doc["result"],RESULT)
        self.assertEqual(doc["original_guest_software_subsets_per_capture"],4944)
        for item in doc["cohorts"]:
            self.assertEqual([r["subset_count"] for r in item["deletion_levels"]],
                             [1,15,105,455,1365,3003])
            self.assertTrue(item["proof_final_shorter_than_all_nonempty_subsets_of_original_prior_calls"])
            self.assertIsNone(item["first_checked_deletion_k_with_final_not_strictly_below_median"])
            self.assertTrue(all(r["all_subsets_keep_final_strictly_shorter"]
                                for r in item["deletion_levels"]))
        self.assertFalse(doc["physical_Nintendo_Switch_audio_measured"])

    def test_five_shorter_ten_longer_has_first_source_reversal_at_five_deleted(self):
        adjusted=heterogeneous(self.b,[x*1_000_000 for x in
            (5,6,7,8,9,25,26,27,28,29,30,31,32,33,34)])
        second=self.audit(b=adjusted)["cohorts"][1]
        self.assertEqual(second["prior_calls_shorter_equal_longer_than_last"],[5,0,10])
        self.assertEqual(second["first_checked_deletion_k_with_final_not_strictly_below_median"],5)
        self.assertFalse(second["proof_final_shorter_than_all_nonempty_subsets_of_original_prior_calls"])
        self.assertEqual(second["deletion_levels"][4]["subsets_with_final_strictly_shorter_than_median"],1365)
        self.assertEqual(second["deletion_levels"][5]["subsets_with_final_longer_than_median"],252)
        self.assertEqual(second["deletion_levels"][5]["subsets_with_final_strictly_shorter_than_median"],2751)
        self.assertEqual(second["deletion_levels"][5]["subsets_with_final_equal_to_median"],0)

    def test_stage332_three_deletion_outcome_counts_unchanged(self):
        report=self.audit()
        for cohort in report["cohorts"]:
            self.assertEqual(cohort["deletion_levels"][3]["subset_count"],455)
            self.assertTrue(cohort["deletion_levels"][3]["all_subsets_keep_final_strictly_shorter"])
            self.assertEqual(cohort["deletion_levels"][3]["subsets_with_final_longer_than_median"],0)

    def test_tied_earlier_calls_are_counted_as_equal_to_not_strictly_below(self):
        final=self.b["stage320"]["last_successful_PlayBuffer_software_duration_ns"]
        earlier=[final]*5+[final+10_000_000]*10
        adjusted=heterogeneous(self.b,earlier)
        result=self.audit(b=adjusted)["cohorts"][1]
        self.assertTrue(result["first_checked_deletion_k_with_final_not_strictly_below_median"] is not None)
        self.assertGreater(sum(x["subsets_with_final_equal_to_median"] for x in
                            result["deletion_levels"]),0)

    def test_tampered_original_guest_history_sha256_fails_closed(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(first_history_sha="0"*64)

    def test_tampered_original_last_success_sha256_fails_closed(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(second_last_sha="0"*64)

    def test_original_stage320_guest_software_source_tamper_rejected(self):
        modified=copy.deepcopy(self.a)
        modified["stage320"]["last_successful_PlayBuffer_return_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(a=modified)

    def test_original_stage322_bounded_software_history_tamper_rejected(self):
        modified=copy.deepcopy(self.b)
        modified["stage322"]["original_call_rows"][0]["duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(b=modified)

    def test_original_guest_csv_extra_untrusted_row_rejected(self):
        modified=copy.deepcopy(self.a)
        modified["history_csv"]+=b"extra,0,0,0,0\n"
        with self.assertRaises(ExitTimelineError):
            self.audit(a=modified)

    def test_identical_original_guest_source_cohorts_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(b=self.a)

    def test_source_outcome_count_conserved_for_each_omission_level(self):
        doc=self.audit()
        for c in doc["cohorts"]:
            for row in c["deletion_levels"]:
                self.assertEqual(
                    row["subsets_with_final_strictly_shorter_than_median"]
                    +row["subsets_with_final_equal_to_median"]
                    +row["subsets_with_final_longer_than_median"],
                    row["subset_count"])
        self.assertTrue(doc["all_original_stage328_to_332_source_audits_recomputed"])

    def test_no_absolute_guest_epochs_pcm_or_sound_claims_in_output(self):
        serialized=json.dumps(self.audit(),sort_keys=True)
        self.assertNotIn("begin_guest_ns",serialized)
        self.assertNotIn("end_guest_ns",serialized)
        self.assertNotIn("pcm_bytes",serialized)
        self.assertNotIn("1000000000",serialized)
        self.assertTrue(self.audit()["not_independent_repeated_gameplay_sessions"])
        self.assertFalse(self.audit()["physical_Nintendo_Switch_audio_measured"])


if __name__=="__main__":
    unittest.main()
