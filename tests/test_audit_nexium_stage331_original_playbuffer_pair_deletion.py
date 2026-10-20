"""Stage331 genuine-source-compatible all-pairs previous-call deletion regressions."""
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
from audit_nexium_stage331_original_playbuffer_pair_deletion import (
    compare_two,one_cohort,EXPECTED_REPLICAS,RESULT,
)
from test_compare_nexium_stage328_original_playbuffer_histories import (
    cohort,pin,pin_last,
)
from test_audit_nexium_stage329_guest_software_dispersion import heterogeneous

class OriginalPlayBufferAllPairDeletions(unittest.TestCase):
    def setUp(self):
        self.a=cohort()
        self.b=cohort(last_duration=22352500,prior_duration=31247083,total=382)

    def audit(self,a=None,b=None,first_history_sha=None,second_history_sha=None,
              first_last_sha=None,second_last_sha=None):
        a=self.a if a is None else a
        b=self.b if b is None else b
        return compare_two(a,b,
                           pin(a) if first_history_sha is None else first_history_sha,
                           pin(b) if second_history_sha is None else second_history_sha,
                           pin_last(a) if first_last_sha is None else first_last_sha,
                           pin_last(b) if second_last_sha is None else second_last_sha)

    def test_uniform_original_tail_all_105_pair_deletions_conserve_counts(self):
        obj=self.audit()
        self.assertEqual(obj["result"],RESULT)
        for row,baseline in zip(obj["cohorts"],(32154011,31247083)):
            self.assertEqual(row["unordered_pair_deletion_replica_count"],105)
            self.assertEqual(row["retained_previous_call_count_per_replica"],13)
            self.assertEqual(row["previous_successful_call_count"],15)
            self.assertEqual(row["leave_two_out_lower_median_min_guest_software_ns"],baseline)
            self.assertEqual(row["leave_two_out_lower_median_max_guest_software_ns"],baseline)
            self.assertEqual(row["leave_two_out_MAD_min_guest_software_ns"],0)
            self.assertEqual(row["leave_two_out_MAD_max_guest_software_ns"],0)
            self.assertEqual(row["leave_two_out_final_first_possible_rank_min"],1)
            self.assertEqual(row["leave_two_out_final_first_possible_rank_max"],1)
            self.assertEqual(row["replicas_with_final_shorter_than_previous_median"],105)
        self.assertFalse(obj["physical_Nintendo_Switch_audio_tested"])

    def test_heterogeneous_original_prior_15_median_bounds(self):
        changed=heterogeneous(self.a,
            [x*1000000 for x in (5,6,7,8,9,10,12,20,30,31,32,33,34,35,36)])
        row=self.audit(a=changed)["cohorts"][0]
        self.assertEqual(row["previous_fifteen_lower_median_guest_software_ns"],20000000)
        self.assertEqual(row["leave_two_out_lower_median_min_guest_software_ns"],12000000)
        self.assertEqual(row["leave_two_out_lower_median_max_guest_software_ns"],30000000)
        self.assertEqual(row["replicas_with_final_shorter_than_previous_median"],105)
        self.assertEqual(row["leave_two_out_final_first_possible_rank_min"],5)
        self.assertEqual(row["leave_two_out_final_first_possible_rank_max"],7)

    def test_sensitive_original_pair_deletions_preserved_not_rejected(self):
        changed=heterogeneous(self.a,
            [x*1000000 for x in (5,6,7,8,9,10,11,12,30,31,32,33,34,35,36)])
        row=self.audit(a=changed)["cohorts"][0]
        self.assertGreater(row["replicas_with_final_longer_than_previous_median"],0)
        self.assertGreater(row["replicas_with_final_shorter_than_previous_median"],0)
        self.assertEqual(sum(row[x] for x in (
            "replicas_with_final_shorter_than_previous_median",
            "replicas_with_final_equal_to_previous_median",
            "replicas_with_final_longer_than_previous_median")),105)

    def test_tied_previous_calls_have_explicit_rank_convention(self):
        last=self.a["stage320"]["last_successful_PlayBuffer_software_duration_ns"]
        changed=heterogeneous(self.a,[last]*3+[last+5000000]*12)
        row=self.audit(a=changed)["cohorts"][0]
        self.assertEqual(row["leave_two_out_final_first_possible_rank_min"],1)
        self.assertEqual(row["leave_two_out_final_first_possible_rank_max"],1)
        self.assertEqual(row["replicas_with_final_shorter_than_previous_median"],105)

    def test_forged_history_hash_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(first_history_sha="0"*64)

    def test_forged_last_call_sha_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(second_last_sha="0"*64)

    def test_altered_original_stage320_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["stage320"]["last_successful_PlayBuffer_return_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(a=changed)

    def test_altered_original_stage322_report_rejected(self):
        changed=copy.deepcopy(self.b)
        changed["stage322"]["original_call_rows"][0]["duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(b=changed)

    def test_corrupt_source_bytes_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["history_csv"]+=b"FAKE\n"
        with self.assertRaises(ExitTimelineError):
            self.audit(a=changed)

    def test_missing_original_baseline_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["stage322"]["prior_successful_call_count_in_window"]=0
        with self.assertRaises(ExitTimelineError):
            self.audit(a=changed)

    def test_identical_original_cohort_not_independent(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(b=self.a)

    def test_guest_absolute_ns_and_pcm_not_exposed(self):
        output=json.dumps(self.audit(),sort_keys=True)
        self.assertNotIn("begin_guest_ns",output)
        self.assertNotIn("end_guest_ns",output)
        self.assertNotIn("pcm_bytes",output)
        self.assertNotIn("1000000000",output)
        self.assertFalse(self.audit()["original_soundtrack_or_audible_dropout_verified"])

if __name__=="__main__":
    unittest.main()
