#!/usr/bin/env python3
"""Stage364 fake-source/receipt mutation regressions only; CI separately replays actual ZIP."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_stage364_guest_host_triple import (
    RUN_ID,TRIPLE_PINS,EXTRA,FILENAMES,VERIFIED,
    bind_independent_reports,exact_guest_paths,
)
from audit_nexium_stage352_three_original_tail_sources import VERIFIED as THREE

def fixture():
    triple={
        "result":THREE,"original_neXium_run_id":RUN_ID,
        "original_guest_csv_sha256":{
            "stage313_last_audio_page_and_tail":TRIPLE_PINS["tail"],
            "stage348_software_PCM_lease":TRIPLE_PINS["lease"],
            "stage351_exit_tail_reason":TRIPLE_PINS["reason"],
        },
        "tail_reason_code":7,"tail_reason_name":"return_confirmed",
        "tail_attempted":True,"tail_descriptor_return_confirmed":True,
        "lease_pages_acquired":1438,"lease_pages_released":1438,
        "abandoned_sessions":0,"exact_archived_original_CSV_bytes_reaudited":True,
        "three_distinct_guest_source_receipts_matched":True,
        "independent_of_any_other_neXium_run":True,
        "older_unconfirmed_tail_failure_cause_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "DAC_or_speaker_audio_verified":False,
    }
    newer={
        "result":"STAGE363_AUTHENTIC_DUAL_CLOCK_AND_GUEST_EXIT_SOURCE_REAUDITED",
        "original_neXium_run_id":RUN_ID,"guest_tail_reason_code":7,
        "guest_audout_wait_raw_result":0,
        "guest_lease_pages_acquired":1438,
        "guest_lease_pages_released":1438,
        "guest_abandoned_sessions":0,
        "original_strict_stage303_success":True,
        "original_stage362_host_recorder_wall_ms":21,
        "original_stage362_host_recorder_monotonic_ns":20788687,
        "original_guest_exit_queue_depth_directly_measured":False,
        "old_failed_run_host_clocks_retroactively_fixed":False,
        "actual_speaker_or_DAC_audio_measured":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }
    return triple,newer

class Stage364Tests(unittest.TestCase):
    def test_consistent_original_receipt_shapes_are_linked(self):
        t,n=fixture()
        result=bind_independent_reports(t,n)
        self.assertEqual(result["result"],VERIFIED)
        self.assertEqual(result["guest_audio_lease_acquired"],1438)
        self.assertFalse(result["direct_exit_time_queue_depth_observed"])
        self.assertFalse(result["old_host_wall_regression_cause_proven"])
    def test_reject_forged_stage313_tail_sha(self):
        t,n=fixture()
        t["original_guest_csv_sha256"]["stage313_last_audio_page_and_tail"]="0"*64
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_changed_guest_exit_reason(self):
        t,n=fixture();t["tail_reason_code"]=4
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_int_for_boolean_guest_return(self):
        t,n=fixture();t["tail_descriptor_return_confirmed"]=1
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_unbalanced_software_pcm_leases(self):
        t,n=fixture();t["lease_pages_released"]=1437
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_unproven_original_bytes(self):
        t,n=fixture();t["exact_archived_original_CSV_bytes_reaudited"]=False
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_other_original_run_id(self):
        t,n=fixture();n["original_neXium_run_id"]+=1
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_forged_stage363_guest_lease(self):
        t,n=fixture();n["guest_lease_pages_acquired"]=1437
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_forged_host_wall_clock(self):
        t,n=fixture();n["original_stage362_host_recorder_wall_ms"]=-771
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_forged_monotonic_clock(self):
        t,n=fixture();n["original_stage362_host_recorder_monotonic_ns"]=-1
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_guest_to_hardware_claim(self):
        t,n=fixture();t["DAC_or_speaker_audio_verified"]=True
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_direct_exit_queue_claim(self):
        t,n=fixture();n["original_guest_exit_queue_depth_directly_measured"]=True
        with self.assertRaises(ValueError):bind_independent_reports(t,n)
    def test_reject_ambiguous_original_guest_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in FILENAMES.values():
                (root/name).write_bytes(b"synthetic only\n")
            duplicate=root/"duplicate"
            duplicate.mkdir()
            (duplicate/EXTRA["tail"][0]).write_bytes(b"fake tail\n")
            with self.assertRaises(ValueError):exact_guest_paths(root)
    def test_reject_symlinked_original_guest_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in FILENAMES.values():
                (root/name).write_bytes(b"synthetic only\n")
            path=root/EXTRA["stage314"][0]
            path.unlink()
            path.symlink_to(root/EXTRA["tail"][0])
            with self.assertRaises(ValueError):exact_guest_paths(root)

if __name__=="__main__":
    unittest.main()
