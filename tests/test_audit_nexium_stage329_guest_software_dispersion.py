"""Stage329 original bounded guest software-call dispersion positive/negative tests."""
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

from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError
from audit_nexium_guest_playbuffer_history import HEADER,FILE as HISTORY_FILE,audit_source
from audit_nexium_stage329_guest_software_dispersion import compare_shapes,RESULT
from test_compare_nexium_stage328_original_playbuffer_histories import (
    cohort,pin,pin_last,
)


def heterogeneous(source,earlier):
    """Produce a legitimate re-audited source with 15 uneven prior durations."""
    source=copy.deepcopy(source)
    if len(earlier)!=15:
        raise ValueError("need fifteen synthetic prior software calls")
    total=source["stage320"]["PlayBuffer_call_attempt_count"]
    last_duration=source["stage320"]["last_successful_PlayBuffer_software_duration_ns"]
    begin=1_000_000_000
    lines=[]
    for seq,duration in zip(range(total-15,total),earlier):
        end=begin+duration
        lines.append(f"{total},{seq},{begin},{end},1\n".encode())
        begin=end+10000
    last_begin=begin+20000
    last_end=last_begin+last_duration
    lines.append(f"{total},{total},{last_begin},{last_end},1\n".encode())
    source["history_csv"]=HEADER+b"".join(lines)
    source["last_csv"]=(
        f"event,value\nattempts,{total}\nsuccesses,{total}\nfailures,0\n"
        f"last_success_attempt,{total}\nlast_success_begin_guest_ns,{last_begin}\n"
        f"last_success_end_guest_ns,{last_end}\nnonmonotonic_rejected,0\n"
    ).encode()
    stage320=source["stage320"]
    stage320["original_last_playbuffer_csv_sha256"]=hashlib.sha256(
        source["last_csv"]).hexdigest()
    stage320["last_successful_PlayBuffer_begin_guest_ns"]=last_begin
    stage320["last_successful_PlayBuffer_return_guest_ns"]=last_end
    source["stage322"]=audit_source(source["history_csv"],stage320)
    source["stage322"].update({
        "original_guest_history_source_observed":True,
        "original_guest_history_bytes_preserved":True,
        "original_guest_history_source_path":str(SUBDIR/HISTORY_FILE),
    })
    return source


class OriginalGuestBoundedSoftwareDispersionTests(unittest.TestCase):
    def setUp(self):
        self.first=cohort()
        self.second=cohort(last_duration=22352500,prior_duration=31247083,total=382)

    def derive(self,first=None,second=None,first_sha=None,second_sha=None,
               first_last_sha=None,second_last_sha=None):
        a=self.first if first is None else first
        b=self.second if second is None else second
        return compare_shapes(
            a,b,
            pin(a) if first_sha is None else first_sha,
            pin(b) if second_sha is None else second_sha,
            pin_last(a) if first_last_sha is None else first_last_sha,
            pin_last(b) if second_last_sha is None else second_last_sha)

    def test_original_uniform_prior_15_and_last_insert_at_rank_one(self):
        r=self.derive()
        self.assertEqual(r["result"],RESULT)
        self.assertEqual([d["previous_lower_median_duration_guest_software_ns"]
                          for d in r["cohorts"]],[32154011,31247083])
        self.assertEqual([d["last_successful_duration_guest_software_ns"]
                          for d in r["cohorts"]],[11225937,22352500])
        for d in r["cohorts"]:
            self.assertEqual(d["previous_successful_call_count"],15)
            self.assertEqual(d["previous_range_guest_software_ns"],0)
            self.assertEqual(d["previous_median_absolute_deviation_guest_software_ns"],0)
            self.assertEqual(d["previous_calls_faster_than_last"],0)
            self.assertEqual(d["previous_calls_equal_to_last"],0)
            self.assertEqual(d["previous_calls_slower_than_last"],15)
            self.assertEqual(d["last_call_first_possible_rank_among_16"],1)
        self.assertFalse(r["Nintendo_Switch_speaker_audio_measured"])

    def test_source_authenticated_mixed_prior_baseline_rank_seven(self):
        modified=heterogeneous(self.first,[
            x*1_000_000 for x in (5,6,7,8,9,10,12,20,30,31,32,33,34,35,36)
        ])
        out=self.derive(first=modified)
        d=out["cohorts"][0]
        self.assertEqual(d["previous_min_duration_guest_software_ns"],5_000_000)
        self.assertEqual(d["previous_lower_median_duration_guest_software_ns"],20_000_000)
        self.assertEqual(d["previous_max_duration_guest_software_ns"],36_000_000)
        self.assertEqual(d["previous_range_guest_software_ns"],31_000_000)
        self.assertEqual(d["previous_calls_faster_than_last"],6)
        self.assertEqual(d["previous_calls_equal_to_last"],0)
        self.assertEqual(d["previous_calls_slower_than_last"],9)
        self.assertEqual(d["last_call_first_possible_rank_among_16"],7)
        self.assertGreater(d["previous_median_absolute_deviation_guest_software_ns"],0)

    def test_source_authenticated_prior_ties_with_final_are_counted(self):
        duration=self.first["stage320"]["last_successful_PlayBuffer_software_duration_ns"]
        modified=heterogeneous(self.first,[
            duration if i<2 else duration+10_000_000 for i in range(15)])
        d=self.derive(first=modified)["cohorts"][0]
        self.assertEqual(d["previous_calls_faster_than_last"],0)
        self.assertEqual(d["previous_calls_equal_to_last"],2)
        self.assertEqual(d["previous_calls_slower_than_last"],13)
        self.assertEqual(d["last_call_first_possible_rank_among_16"],1)

    def test_forged_history_csv_hash_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.derive(first_sha="0"*64)

    def test_forged_last_success_csv_hash_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.derive(second_last_sha="0"*64)

    def test_altered_original_history_source_rejected(self):
        changed=copy.deepcopy(self.first)
        changed["history_csv"]=changed["history_csv"].replace(b",1\n",b",0\n",1)
        with self.assertRaises(ExitTimelineError):
            self.derive(first=changed,first_sha=pin(self.first))

    def test_altered_stage320_original_receipt_rejected(self):
        changed=copy.deepcopy(self.first)
        changed["stage320"]["last_successful_PlayBuffer_software_duration_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.derive(first=changed)

    def test_altered_stage322_receipt_rejected(self):
        changed=copy.deepcopy(self.second)
        changed["stage322"]["prior_successful_duration_lower_median_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.derive(second=changed)

    def test_missing_original_previous_baseline_fails_closed(self):
        changed=copy.deepcopy(self.first)
        changed["stage322"]["prior_successful_call_count_in_window"]=0
        with self.assertRaises(ExitTimelineError):
            self.derive(first=changed)

    def test_same_source_original_cohort_is_not_two_independent_captures(self):
        with self.assertRaises(ExitTimelineError):
            self.derive(second=self.first)

    def test_no_absolute_guest_timestamps_or_sample_data_in_output(self):
        obj=self.derive()
        body=json.dumps(obj,sort_keys=True)
        self.assertNotIn("begin_guest_ns",body)
        self.assertNotIn("end_guest_ns",body)
        self.assertNotIn("pcm_bytes",body)
        self.assertTrue(obj["no_absolute_original_guest_software_timestamps_published"])
        self.assertFalse(obj["original_PS1_soundtrack_or_audible_dropout_verified"])

    def test_each_raw_prior_call_stays_source_bound_to_complete_16(self):
        changed=copy.deepcopy(self.first)
        lines=changed["history_csv"].splitlines(keepends=True)
        changed["history_csv"]=b"".join(lines[:-1])
        with self.assertRaises(ExitTimelineError):
            self.derive(first=changed)


if __name__=="__main__":
    unittest.main()
