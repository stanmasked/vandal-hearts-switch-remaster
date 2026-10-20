#!/usr/bin/env python3
"""Stage365 synthetic cross-run provenance / missing-pair controls, never guest playback."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from audit_nexium_stage365_distinct_timeout_success import (
    compare, safe_files, old_capture, TIMEOUT_SOURCES, TIMEOUT_RUN,
    SUCCESS_RUN, TIMEOUT_VERIFIED, SUCCESS_VERIFIED, VERIFIED,
    TIMEOUT_TAIL_SHA, TIMEOUT_LEASE_SHA, TIMEOUT_REASON_SHA,
    TIMEOUT_WAIT_SHA, SUCCESS_PINS,
)

def fixture():
    failed={
        "result":TIMEOUT_VERIFIED,
        "original_neXium_run_id":TIMEOUT_RUN,
        "source_sha256":{
            "stage313":TIMEOUT_TAIL_SHA,
            "stage348":TIMEOUT_LEASE_SHA,
            "stage351":TIMEOUT_REASON_SHA,
            "stage357":TIMEOUT_WAIT_SHA,
        },
        "stage351_reason_code":4,
        "stage357_audout_wait_raw_result_decimal":59905,
        "software_lease_pages_acquired":1414,
        "software_lease_pages_released":1413,
        "software_abandoned_sessions":1,
        "underlying_event_wait_call_site_uniquely_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }
    passed={
        "result":SUCCESS_VERIFIED,
        "original_neXium_run_id":SUCCESS_RUN,
        "stage313_original_tail_csv_sha256":SUCCESS_PINS["tail"],
        "stage348_original_lease_csv_sha256":SUCCESS_PINS["lease"],
        "stage351_original_reason_csv_sha256":SUCCESS_PINS["reason"],
        "guest_tail_reason_code":7,
        "guest_raw_audout_wait_result":0,
        "guest_audio_lease_acquired":1438,
        "guest_audio_lease_released":1438,
        "guest_audio_abandoned_sessions":0,
        "original_three_guest_families_independently_replayed":True,
        "original_stage363_host_and_guest_source_replayed":True,
        "host_strict_stage303_success":True,
        "host_recorder_stop_wall_delta_ms":21,
        "host_recorder_stop_monotonic_delta_ns":20788687,
        "physical_Nintendo_Switch_audio_tested":False,
        "guest_to_host_clock_sync_proven":False,
        "old_host_wall_regression_cause_proven":False,
        "older_timeout_has_matched_stage360_probe":False,
        "direct_exit_time_queue_depth_observed":False,
    }
    return failed,passed

class Stage365Tests(unittest.TestCase):
    def test_separately_validated_distinct_original_runs_do_not_infer_queue(self):
        a,b=fixture()
        result=compare(a,b)
        self.assertEqual(result["result"],VERIFIED)
        self.assertEqual([result["timeout_original_run_id"],result["success_original_run_id"]],
                         [39325440778,39340120727])
        self.assertIsNone(result["timeout_old_pre_submit_queue_depth"])
        self.assertIsNone(result["timeout_old_pre_submit_probe_age_ns"])
        self.assertFalse(result["causal_inference_about_old_timeout_proven"])
        self.assertFalse(result["real_hardware_Nintendo_Switch_speaker_or_DAC_verified"])
    def test_reject_timeout_disguised_as_successful_run(self):
        a,b=fixture();a["original_neXium_run_id"]=SUCCESS_RUN
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_fake_timeout_return_zero(self):
        a,b=fixture();a["stage357_audout_wait_raw_result_decimal"]=0
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_fake_timeout_source_sha(self):
        a,b=fixture();a["source_sha256"]["stage357"]="0"*64
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_timeout_abandoned_page_forgery(self):
        a,b=fixture();a["software_abandoned_sessions"]=0
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_false_hardware_evidence(self):
        a,b=fixture();a["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_success_wrong_guest_tail_original_sha(self):
        a,b=fixture();b["stage313_original_tail_csv_sha256"]=TIMEOUT_TAIL_SHA
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_success_earlier_timeout_lease_counts(self):
        a,b=fixture();b["guest_audio_lease_released"]=1413
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_original_success_guest_exit_reason_forgery(self):
        a,b=fixture();b["guest_tail_reason_code"]=4
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_synthetic_bool_as_guest_zero_result(self):
        a,b=fixture();b["guest_raw_audout_wait_result"]=False
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_old_timeout_forged_kernel_callsite_proof(self):
        a,b=fixture();a["underlying_event_wait_call_site_uniquely_proven"]=True
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_success_claims_old_matched_probe(self):
        a,b=fixture();b["older_timeout_has_matched_stage360_probe"]=True
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_forged_exit_queue_depth_measurement(self):
        a,b=fixture();b["direct_exit_time_queue_depth_observed"]=True
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_guest_to_host_clock_alignment_claim(self):
        a,b=fixture();b["guest_to_host_clock_sync_proven"]=True
        with self.assertRaises(ValueError):compare(a,b)
    def test_reject_ambiguous_old_guest_archive_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in TIMEOUT_SOURCES.values():
                (root/name).write_bytes(b"synthetic\n")
            dup=root/"duplicate"
            dup.mkdir()
            (dup/TIMEOUT_SOURCES["wait"]).write_bytes(b"fake\n")
            with self.assertRaises(ValueError):safe_files(root,TIMEOUT_SOURCES)
    def test_reject_unexpected_probe_in_old_timeout_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in TIMEOUT_SOURCES.values():
                (root/name).write_bytes(b"synthetic\n")
            (root/"audio-exit-probe-context-000.csv").write_bytes(b"impossible pairing\n")
            with self.assertRaises(ValueError):
                old_capture(root)
    def test_reject_linked_old_timeout_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in TIMEOUT_SOURCES.values():
                (root/name).write_bytes(b"synthetic\n")
            item=root/TIMEOUT_SOURCES["wait"]
            item.unlink()
            item.symlink_to(root/TIMEOUT_SOURCES["tail"])
            with self.assertRaises(ValueError):safe_files(root,TIMEOUT_SOURCES)

if __name__=="__main__":
    unittest.main()
