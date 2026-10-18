"""Stage330 original PlayBuffer guest software leave-one-out source audit tests."""
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
from audit_nexium_stage330_original_playbuffer_jackknife import (
    compare_jackknives,source_jackknife,RESULT,
)
from test_compare_nexium_stage328_original_playbuffer_histories import (
    cohort,pin,pin_last,
)
from test_audit_nexium_stage329_guest_software_dispersion import heterogeneous


class SourceBoundPlayBufferJackknifeTests(unittest.TestCase):
    def setUp(self):
        self.a=cohort()
        self.b=cohort(last_duration=22352500,prior_duration=31247083,total=382)

    def audit(self,first=None,second=None,first_history_sha=None,
              second_history_sha=None,first_last_sha=None,second_last_sha=None):
        a=self.a if first is None else first
        b=self.b if second is None else second
        return compare_jackknives(
            a,b,
            pin(a) if first_history_sha is None else first_history_sha,
            pin(b) if second_history_sha is None else second_history_sha,
            pin_last(a) if first_last_sha is None else first_last_sha,
            pin_last(b) if second_last_sha is None else second_last_sha)

    def test_uniform_prior_cohorts_have_fixed_leave_one_out_medians(self):
        r=self.audit()
        self.assertEqual(r["result"],RESULT)
        for doc,baseline in zip(r["cohorts"],[32154011,31247083]):
            self.assertEqual(doc["original_retained_success_count"],16)
            self.assertEqual(doc["original_previous_success_count"],15)
            self.assertEqual(doc["jackknife_replica_count"],15)
            self.assertEqual(doc["calls_in_each_replica"],14)
            self.assertEqual(doc["leave_one_out_lower_median_min_ns"],baseline)
            self.assertEqual(doc["leave_one_out_lower_median_max_ns"],baseline)
            self.assertEqual(doc["leave_one_out_lower_median_span_ns"],0)
            self.assertEqual(doc["leave_one_out_MAD_min_ns"],0)
            self.assertEqual(doc["leave_one_out_MAD_max_ns"],0)
            self.assertEqual(doc["leave_one_out_last_first_possible_rank_min"],1)
            self.assertEqual(doc["leave_one_out_last_first_possible_rank_max"],1)
            self.assertTrue(doc["all_replicas_have_last_shorter_than_prior_lower_median"])
        self.assertTrue(r["leave_one_out_is_descriptive_not_population_confidence_interval"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_measured"])

    def test_heterogeneous_previous_15_one_removed_changes_baseline(self):
        changed=heterogeneous(self.a,[
            x*1_000_000 for x in (5,6,7,8,9,10,12,20,30,31,32,33,34,35,36)])
        doc=self.audit(first=changed)["cohorts"][0]
        self.assertEqual(doc["full_previous_lower_median_ns"],20_000_000)
        self.assertEqual(doc["leave_one_out_lower_median_min_ns"],12_000_000)
        self.assertEqual(doc["leave_one_out_lower_median_max_ns"],20_000_000)
        self.assertEqual(doc["leave_one_out_lower_median_span_ns"],8_000_000)
        self.assertEqual(doc["leave_one_out_last_first_possible_rank_min"],6)
        self.assertEqual(doc["leave_one_out_last_first_possible_rank_max"],7)
        self.assertTrue(doc["all_replicas_have_last_shorter_than_prior_lower_median"])

    def test_complete_fifteen_deletions_never_generate_fabricated_samples(self):
        source=self.audit()
        self.assertEqual(len(source["cohorts"]),2)
        self.assertTrue(source["both_stage329_original_source_receipts_independently_replayed"])
        for row in source["cohorts"]:
            self.assertTrue(row["jackknife_deleted_one_previous_call_per_replica"])
            self.assertEqual(row["calls_in_each_replica"]*row["jackknife_replica_count"],210)

    def test_bad_history_csv_pin_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(first_history_sha="0"*64)

    def test_bad_last_success_original_csv_pin_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(second_last_sha="0"*64)

    def test_altered_stage320_guest_original_timestamp_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["stage320"]["last_successful_PlayBuffer_return_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(first=changed)

    def test_altered_stage322_original_call_row_rejected(self):
        changed=copy.deepcopy(self.b)
        changed["stage322"]["original_call_rows"][1]["duration_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.audit(second=changed)

    def test_spoofed_guest_pcm_audio_verification_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["stage320"]["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(ExitTimelineError):
            self.audit(first=changed)

    def test_missing_real_original_retained_history_rejected(self):
        changed=copy.deepcopy(self.a)
        changed["history_csv"]=b"total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n"
        with self.assertRaises(ExitTimelineError):
            self.audit(first=changed)

    def test_identical_original_capture_pins_are_not_two_independent_runs(self):
        with self.assertRaises(ExitTimelineError):
            self.audit(second=self.a)

    def test_last_call_does_not_have_to_remain_below_every_resample_median(self):
        changed=heterogeneous(
            self.a,[x*1_000_000 for x in
                    (5,6,7,8,9,10,11,12,30,31,32,33,34,35,36)])
        # Full previous median 12 ms exceeds final call ~11.226ms, but
        # omitting one high source observation yields lower median 11ms.
        with self.assertRaises(ExitTimelineError):
            self.audit(first=changed)

    def test_no_guest_absolute_begin_end_or_host_PCM_in_result(self):
        text=json.dumps(self.audit(),sort_keys=True)
        self.assertNotIn("begin_guest_ns",text)
        self.assertNotIn("end_guest_ns",text)
        self.assertNotIn("pcm_bytes",text)
        self.assertNotIn("1000000000",text)
        self.assertFalse(self.audit()["original_PS1_music_or_speaker_sound_verified"])


if __name__=="__main__":
    unittest.main()
