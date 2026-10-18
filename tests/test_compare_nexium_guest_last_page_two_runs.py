"""Stage316 two original NeXium guest last-page sources with unequal evidence tiers."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import SUBDIR
from audit_nexium_guest_last_buffer_return import audit_source
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from compare_nexium_guest_last_page_two_runs import (
    compare_two, EXPECTED_CLASS,
)
from replay_nexium_original_guest_exit_archive import reconstructed_stage310
from replay_nexium_original_audout_exit_archive import (
    reconstruct_stage314, independent_original_audout_replay,
)
from test_compare_nexium_guest_exit_cohort import fixture


def audited_capture(index:int):
    run,png,guest,raw,_=fixture(index)
    optical=audit_guest_clocks(png,guest)
    times=guest["guest_monotonic_timestamps_ns"]
    page=times["stop_requested"]+100
    tail=times["worker_cleanup_entered"]+50
    page_raw=("event,value\n"
              "page_return_count,380\n"
              f"last_page_return_guest_ns,{page}\n"
              "last_page_frames,128\n"
              f"tail_attempt_guest_ns,{tail}\n"
              f"tail_success_return_guest_ns,{tail+100}\n").encode()
    page_receipt=audit_source(page_raw,guest)
    page_receipt["original_guest_page_witness_observed"]=True
    page_receipt["guest_source_path"]=str(SUBDIR/"audio-exit-output-000.csv")
    return run,png,guest,raw,optical,page_raw,page_receipt


class AudoutTwoOriginalRuns(unittest.TestCase):
    def setUp(self):
        older=audited_capture(0)
        newer=audited_capture(1)
        self.old=(older[0],older[1],older[2],older[4],older[6])
        raw,png,guest,guest_page,new_stage308=(
            newer[3],newer[1],newer[2],newer[5],newer[4])
        stage310=reconstructed_stage310(raw,new_stage308)
        stage314=reconstruct_stage314(guest_page,raw,newer[6])
        self.new_id=newer[0]
        self.new_raw=(raw,guest_page,png,guest,new_stage308,
                      stage310,newer[6],stage314)
        self.new=(self.new_id,self.new_raw,self.new_id)
        self.stage315=independent_original_audout_replay(
            *self.new_raw,self.new_id)

    def compare(self,old=None,new=None,receipt=None):
        return compare_two(
            self.old if old is None else old,
            self.new if new is None else new,
            self.stage315 if receipt is None else receipt)

    def test_two_distinct_guest_original_pages_with_tier(self):
        report=self.compare()
        self.assertEqual(report["result"],
                         "TWO_INDEPENDENT_GUEST_LAST_PAGE_RELEASES_COMPARED")
        self.assertEqual(report["run_count"],2)
        self.assertEqual(report["capture_time_JSON_only_audout_run_ids"],[self.old[0]])
        self.assertEqual(report["byte_original_independently_reaudited_audout_run_ids"],
                         [self.new_id])
        self.assertTrue(report["all_successful_last_page_returns_after_stop_before_cleanup"])
        self.assertTrue(report["all_bounded_taper_buffer_returns_confirmed"])
        self.assertFalse(report["physical_Nintendo_Switch_audio_tested"])
        self.assertEqual(report["source_runs"][0]["last_page_position_relative_to_exit"],
                         EXPECTED_CLASS)
        self.assertFalse(report["source_runs"][0][
            "original_last_page_csv_bytes_independently_reaudited"])
        self.assertTrue(report["source_runs"][1][
            "original_last_page_csv_bytes_independently_reaudited"])

    def test_guest_exit_software_timing_not_audible(self):
        report=self.compare()
        self.assertTrue(report["audout_return_is_NOT_speaker_or_DAC_sample_time"])
        self.assertTrue(report["guest_clock_NOT_calibrated_to_host_pcm_frames"])
        self.assertIs(report["Plus_caused_audible_dropout_proven"],False)

    def test_same_source_workflow_id_rejected(self):
        new=(self.old[0],self.new_raw,self.old[0])
        with self.assertRaises(TraceError):
            self.compare(new=new)

    def test_older_guest_exit_sha_forgery_rejected(self):
        old=list(self.old)
        page=copy.deepcopy(old[4])
        page["original_guest_exit_csv_sha256"]="f"*64
        old[4]=page
        with self.assertRaises(TraceError):
            self.compare(old=tuple(old))

    def test_older_page_timestamp_out_of_source_window_rejected(self):
        old=list(self.old)
        page=copy.deepcopy(old[4])
        page["last_page_relative_to_Plus_ns"]+=200
        old[4]=page
        with self.assertRaises(TraceError):
            self.compare(old=tuple(old))

    def test_older_guest_optical_source_crc_changed_rejected(self):
        old=list(self.old)
        old[1]=self.new_raw[2]
        with self.assertRaises(TraceError):
            self.compare(old=tuple(old))

    def test_older_audible_overclaim_rejected(self):
        old=list(self.old)
        page=copy.deepcopy(old[4])
        page["audible_dropout_verified"]=True
        old[4]=page
        with self.assertRaises(TraceError):
            self.compare(old=tuple(old))

    def test_older_last_page_before_plus_not_falsely_inside_exit(self):
        old=list(self.old)
        page=copy.deepcopy(old[4])
        plus=old[2]["guest_monotonic_timestamps_ns"]["plus_observed"]
        page["last_page_return_guest_ns"]=plus-100
        page["last_page_relative_to_Plus_ns"]=-100
        page["last_page_position_relative_to_guest_exit"] = (
            "last_page_returned_before_Plus_observed")
        old[4]=page
        report=self.compare(old=tuple(old))
        self.assertFalse(report["all_successful_last_page_returns_after_stop_before_cleanup"])

    def test_forged_original_second_source_csv_bytes_rejected(self):
        second=list(self.new_raw)
        second[1]=second[1].replace(b"page_return_count,380",
                                    b"page_return_count,381")
        with self.assertRaises(TraceError):
            self.compare(new=(self.new_id,tuple(second),self.new_id))

    def test_forged_independent_Stage315_SHA_rejected(self):
        report=copy.deepcopy(self.stage315)
        report["original_guest_audout_page_csv_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.compare(receipt=report)

    def test_new_source_stage314_report_change_rejected(self):
        new=list(self.new_raw)
        receipt=copy.deepcopy(new[7])
        receipt["original_guest_output_csv_sha256"]="a"*64
        new[7]=receipt
        with self.assertRaises(TraceError):
            self.compare(new=(self.new_id,tuple(new),self.new_id))

    def test_duplicate_optical_source_is_not_independent(self):
        old=list(self.old)
        old[1]=self.new_raw[2]
        old[3]=self.new_raw[4]
        with self.assertRaises(TraceError):
            self.compare(old=tuple(old))

    def test_reproducibility(self):
        self.assertEqual(self.compare(),self.compare())


if __name__=="__main__":
    unittest.main()
