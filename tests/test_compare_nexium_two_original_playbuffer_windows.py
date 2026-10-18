"""Stage324 two source-original guest PlayBuffer windows comparison tests."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_switch_guest_scene_trace import TraceError
from compare_nexium_two_original_playbuffer_windows import (
    compare_replays,VERIFIED,
)
from replay_nexium_original_playbuffer_history_archive import (
    VERIFIED as SOURCE_VERIFIED,
)


def synthetic_replay(run:int,final:int,prior:int,shorter:int,equal:int,longer:int):
    def sha(tag):
        return hashlib.sha256(f"{tag}/{run}".encode()).hexdigest()
    return {
        "result":SOURCE_VERIFIED,
        "original_source_workflow_run_id":run,
        "original_stage322_history_CSV_and_receipt_replayed":True,
        "original_stage307_308_310_313_314_317_320_321_sources_replayed":True,
        "guest_software_call_is_NOT_DAC_or_speaker_sound":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_guest_to_host_PCM_clock_fit_verified":False,
        "plus_caused_audible_dropout_verified":False,
        "source_call_count":380,
        "recent_original_service_call_count":16,
        "last_successful_duration_guest_ns":final,
        "prior_successful_calls_in_window":shorter+equal+longer,
        "prior_successful_calls_shorter_than_last":shorter,
        "prior_successful_calls_equal_to_last":equal,
        "prior_successful_calls_longer_than_last":longer,
        "has_source_verified_prior_call_baseline":True,
        "prior_successful_lower_median_duration_guest_ns":prior,
        "last_call_ascending_rank_among_prior_plus_last":shorter+1,
        "last_minus_prior_lower_median_guest_ns":final-prior,
        "prior_successful_duration_rank_is_only_this_bounded_window":True,
        "original_guest_history_csv_sha256":sha("history"),
        "original_guest_exit_csv_sha256":sha("guest-exit"),
        "original_guest_optical_crc_PNG_sha256":sha("optical"),
    }


class TwoOriginalPlayBufferRuns(unittest.TestCase):
    def setUp(self):
        self.a=synthetic_replay(
            39159226320,18_385_781,31_775_052,3,0,12)
        self.b=synthetic_replay(
            39162251380,21_000_000,29_000_000,5,0,10)

    def compare(self,a=None,b=None):
        return compare_replays(self.a if a is None else a,
                               self.b if b is None else b)

    def test_different_original_guest_sources_and_duration_pair(self):
        r=self.compare()
        self.assertEqual(r["result"],VERIFIED)
        self.assertEqual(r["independent_original_workflow_run_count"],2)
        self.assertTrue(r["both_final_calls_below_own_prior_lower_median"])
        self.assertEqual(r["source_runs"][0]["final_call_ascending_rank_in_window"],4)
        self.assertEqual(r["source_runs"][1]["final_call_ascending_rank_in_window"],6)
        self.assertEqual(r["last_call_guest_duration_difference_second_minus_first_ns"],
                         21_000_000-18_385_781)
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_two_runs_need_distinct_workflow_ids(self):
        b=copy.deepcopy(self.b)
        b["original_source_workflow_run_id"]=self.a["original_source_workflow_run_id"]
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_same_original_guest_raw_history_sha_rejected(self):
        b=copy.deepcopy(self.b)
        b["original_guest_history_csv_sha256"]=self.a["original_guest_history_csv_sha256"]
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_same_original_optical_crc_png_valid_for_deterministic_scene(self):
        b=copy.deepcopy(self.b)
        b["original_guest_optical_crc_PNG_sha256"]=self.a["original_guest_optical_crc_PNG_sha256"]
        result=self.compare(b=b)
        self.assertEqual(result["result"],VERIFIED)
        self.assertNotEqual(result["source_runs"][0]["original_guest_history_csv_sha256"],
                            result["source_runs"][1]["original_guest_history_csv_sha256"])

    def test_malformed_original_optical_sha_is_rejected(self):
        b=copy.deepcopy(self.b)
        b["original_guest_optical_crc_PNG_sha256"]="wrong"
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_same_original_exit_guest_csv_sha_rejected(self):
        b=copy.deepcopy(self.b)
        b["original_guest_exit_csv_sha256"]=self.a["original_guest_exit_csv_sha256"]
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_forged_final_below_median_difference_rejected(self):
        b=copy.deepcopy(self.b)
        b["last_minus_prior_lower_median_guest_ns"]+=1
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_forged_rank_conservation_rejected(self):
        b=copy.deepcopy(self.b)
        b["last_call_ascending_rank_among_prior_plus_last"]+=1
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_missing_source_verified_baseline_rejected(self):
        b=copy.deepcopy(self.b)
        b["has_source_verified_prior_call_baseline"]=False
        b["prior_successful_lower_median_duration_guest_ns"]=None
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_no_prior_successes_is_not_comparable(self):
        b=copy.deepcopy(self.b)
        b["prior_successful_calls_in_window"]=0
        b["prior_successful_calls_shorter_than_last"]=0
        b["prior_successful_calls_longer_than_last"]=0
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_two_real_runs_may_disagree_about_final_call_shortness(self):
        b=synthetic_replay(39162251380,40_000_000,29_000_000,12,0,3)
        result=self.compare(b=b)
        self.assertFalse(result["both_final_calls_below_own_prior_lower_median"])
        self.assertTrue(result["source_runs"][0]["final_below_own_prior_median"])
        self.assertFalse(result["source_runs"][1]["final_below_own_prior_median"])

    def test_negative_or_boolean_original_timestamps_rejected(self):
        for bad in (-1,True):
            b=copy.deepcopy(self.b)
            b["last_successful_duration_guest_ns"]=bad
            with self.subTest(bad=bad),self.assertRaises(TraceError):
                self.compare(b=b)

    def test_missing_original_optical_sha_rejected(self):
        b=copy.deepcopy(self.b)
        b.pop("original_guest_optical_crc_PNG_sha256")
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_last_service_call_may_be_tied_with_prior(self):
        b=synthetic_replay(39162251380,30_000_000,30_000_000,4,2,9)
        r=self.compare(b=b)
        self.assertEqual(r["source_runs"][1]["prior_equal"],2)
        self.assertFalse(r["source_runs"][1]["final_below_own_prior_median"])

    def test_original_audio_hardware_overclaim_rejected(self):
        b=copy.deepcopy(self.b)
        b["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(TraceError):
            self.compare(b=b)

    def test_deterministic_with_no_retail_soundtrack_claim(self):
        r=self.compare()
        self.assertEqual(r,self.compare())
        self.assertTrue(r["guest_software_times_not_host_PCM_or_DAC_samples"])
        self.assertFalse(r["retail_PlayStation_music_fidelity_verified"])
        self.assertFalse(r["audible_Plus_audio_dropout_causality_verified"])


if __name__=="__main__":
    unittest.main()
