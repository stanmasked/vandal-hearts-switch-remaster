"""Stage322 bounded guest original PlayBuffer rolling history source tests."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_guest_last_playbuffer import audit_original as audit_last_call
from audit_nexium_guest_playbuffer_history import (
    VERIFIED, audit_source, HEADER, CAP,
)
from test_audit_nexium_guest_last_playbuffer import originals, csv as last_csv


def history(*,failure_seq=(),total=380,final_begin=100000,final_end=112900):
    start=total-15
    rows=[]
    for i,seq in enumerate(range(start,total+1)):
        if i==15:
            begin,end=final_begin,final_end
        else:
            begin=75000+1000*i
            end=begin+500
        rows.append((total,seq,begin,end,int(seq not in failure_seq)))
    return HEADER+b"".join(
        f"{all_calls},{seq},{begin},{end},{returned}\n".encode()
        for all_calls,seq,begin,end,returned in rows
    )


class GuestPlayBufferHistoryTests(unittest.TestCase):
    def setUp(self):
        _,_,_,self.exit,self.page,self.worker=originals()
        self.final=audit_last_call(last_csv(),self.exit,self.page,self.worker)
        self.raw=history()

    def check(self,raw=None,final=None):
        return audit_source(
            self.raw if raw is None else raw,
            self.final if final is None else final)

    def test_realistic_prior_baseline_and_source_sha(self):
        r=self.check()
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["original_recent_call_count"],16)
        self.assertEqual(r["prior_successful_call_count_in_window"],15)
        self.assertEqual(r["prior_successful_duration_lower_median_guest_ns"],500)
        self.assertEqual(r["final_call_duration_guest_ns"],12900)
        self.assertEqual(r["final_minus_prior_lower_median_guest_ns"],12400)
        self.assertTrue(r["final_successful_call_in_recent_window"])
        self.assertEqual(r["original_guest_history_csv_sha256"],
                         hashlib.sha256(self.raw).hexdigest())
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_changed_last_call_is_rejected_against_original_stage320(self):
        bad=self.raw.replace(b"380,380,100000,112900,1",
                             b"380,380,100000,112901,1")
        with self.assertRaises(ExitTimelineError):
            self.check(raw=bad)

    def test_unordered_or_nonconsecutive_history_is_rejected(self):
        bad=self.raw.replace(b"380,370,",b"380,369,")
        with self.assertRaises(ExitTimelineError):
            self.check(raw=bad)

    def test_overlap_between_calls_is_rejected(self):
        bad=self.raw.replace(b"380,367,77000,77500,1",
                             b"380,367,76001,77500,1")
        with self.assertRaises(ExitTimelineError):
            self.check(raw=bad)

    def test_wrong_original_global_call_counter_is_rejected(self):
        bad=self.raw.replace(b"380,365,",b"379,365,")
        with self.assertRaises(ExitTimelineError):
            self.check(raw=bad)

    def test_bad_lease_result_or_counter_not_consistent(self):
        for bad in (
            self.raw.replace(b"380,370,80000,80500,1",
                             b"380,370,80000,80500,2"),
            history(failure_seq=(370,)),
        ):
            with self.subTest(bad=bad[:40]),self.assertRaises(ExitTimelineError):
                self.check(raw=bad)

    def test_missing_or_excessive_rows_fail_closed(self):
        for bad in (
            HEADER,
            self.raw.rsplit(b"\n",2)[0]+b"\n",
            self.raw+self.raw.splitlines(keepends=True)[1],
        ):
            with self.subTest(case=bad[:65]),self.assertRaises(ExitTimelineError):
                self.check(raw=bad)

    def test_noncanonical_corrupt_source_fails_closed(self):
        for bad in (
            self.raw[:-1],
            self.raw.replace(b"\n",b"\r\n"),
            self.raw.replace(b"lease_returned",b"speaker_played"),
            self.raw.replace(b"380,370,",b"0380,370,"),
            self.raw.replace(b"380,370,",b"-380,370,"),
            self.raw+b"\x00",
            self.raw.replace(b"380,370,",b"18446744073709551616,370,"),
        ):
            with self.subTest(case=bad[:40]),self.assertRaises(ExitTimelineError):
                self.check(raw=bad)

    def test_forged_stage320_timestamp_rejected(self):
        doc=copy.deepcopy(self.final)
        doc["last_successful_PlayBuffer_return_guest_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.check(final=doc)

    def test_missing_stage320_source_is_not_equivalent_to_original(self):
        with self.assertRaises(ExitTimelineError):
            self.check(final={"result":"NOT_OBSERVED"})

    def test_history_less_than_sixteen_is_valid_if_total_is_small(self):
        doc=copy.deepcopy(self.final)
        doc["PlayBuffer_call_attempt_count"]=2
        doc["successful_PlayBuffer_call_count"]=2
        doc["last_successful_PlayBuffer_attempt_index"]=2
        short=(HEADER+
               b"2,1,90000,90500,1\n"
               b"2,2,100000,112900,1\n")
        report=self.check(raw=short,final=doc)
        self.assertEqual(report["original_recent_call_count"],2)
        self.assertEqual(report["prior_successful_duration_lower_median_guest_ns"],500)

    def test_no_earlier_sample_is_not_forged_into_baseline(self):
        doc=copy.deepcopy(self.final)
        doc["PlayBuffer_call_attempt_count"]=1
        doc["successful_PlayBuffer_call_count"]=1
        doc["last_successful_PlayBuffer_attempt_index"]=1
        report=self.check(
            raw=HEADER+b"1,1,100000,112900,1\n",final=doc)
        self.assertEqual(report["prior_successful_call_count_in_window"],0)
        self.assertIsNone(report["prior_successful_duration_lower_median_guest_ns"])
        self.assertIsNone(report["final_minus_prior_lower_median_guest_ns"])

    def test_last_success_outside_window_is_explicit_and_no_fabricated_baseline(self):
        doc=copy.deepcopy(self.final)
        doc["successful_PlayBuffer_call_count"]=364
        doc["last_successful_PlayBuffer_attempt_index"]=364
        # The older verified last success ended at 112900. All later
        # failed attempts must be monotonic AFTER that original call.
        raw=(HEADER+b"".join(
            f"380,{seq},{112901+2*(seq-365)},{112902+2*(seq-365)},0\n".encode()
            for seq in range(365,381)))
        report=self.check(raw=raw,final=doc)
        self.assertFalse(report["final_successful_call_in_recent_window"])
        self.assertIsNone(report["prior_successful_duration_lower_median_guest_ns"])
        self.assertEqual(report["original_recent_failed_return_count"],16)

    def test_replay_is_deterministic_without_audible_claims(self):
        r=self.check()
        self.assertEqual(r,self.check())
        self.assertTrue(r["history_is_not_the_entire_session"])
        self.assertTrue(r["one_call_is_not_DAC_or_last_audible_sample"])
        self.assertIs(r["original_PS1_retail_soundtrack_verified"],False)


if __name__=="__main__":
    unittest.main()
