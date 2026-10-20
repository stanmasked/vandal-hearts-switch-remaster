"""Synthetic negative/positive checks for bounded Stage336 source gate diagnosis."""
from __future__ import annotations
import copy
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))
from audit_nexium_stage340_failed_nro_binding_diagnostic import inspect_bind
from test_audit_nexium_stage336_capture_build_binding import SameRunSourceToNroBindingTests as Fixtures
SHA="a"*40
RUN=39180000000

class Stage340SourceGateTests(unittest.TestCase):
    def setUp(self):
        x=Fixtures()
        x.setUp()
        self.saved=x.saved
        self.preflight=x.preflight
        self.monitor=x.monitor

    def test_original_source_witness_and_same_NRO_pins_match(self):
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,
            self.monitor,git_sha=SHA,run_id=RUN,run_attempt=1),
            "all_visible_Stage336_binding_gates_pass")

    def test_forged_saved_original_stage334_receipt(self):
        altered=dict(self.saved,original_guest_last_call_duration_software_ns=-1)
        self.assertEqual(inspect_bind(self.saved,altered,self.preflight,
            self.monitor,git_sha=SHA,run_id=RUN,run_attempt=1),
            "original_stage334_saved_receipt_not_identical_to_source_replay")

    def test_preflight_commit_mismatch(self):
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,
            self.monitor,git_sha="e"*40,run_id=RUN,run_attempt=1),
            "NRO_preflight_commit_does_not_match_capture")

    def test_preflight_run_number_mismatch(self):
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,
            self.monitor,git_sha=SHA,run_id=RUN+1,run_attempt=1),
            "NRO_preflight_run_id_does_not_match_capture")

    def test_preflight_attempt_mismatch(self):
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,
            self.monitor,git_sha=SHA,run_id=RUN,run_attempt=2),
            "NRO_preflight_run_attempt_does_not_match_capture")

    def test_preflight_result_not_valid(self):
        p=dict(self.preflight,result="INCOMPLETE")
        self.assertEqual(inspect_bind(self.saved,self.saved,p,self.monitor,
            git_sha=SHA,run_id=RUN,run_attempt=1),"NRO_preflight_result_not_verified")

    def test_preflight_wrong_build_size(self):
        p=dict(self.preflight,nro_bytes=1)
        self.assertEqual(inspect_bind(self.saved,self.saved,p,self.monitor,
            git_sha=SHA,run_id=RUN,run_attempt=1),"NRO_preflight_size_invalid")

    def test_wrong_NRO_digest_between_preflight_and_monitor(self):
        m=dict(self.monitor,source_nro_sha256="c"*64)
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,m,
            git_sha=SHA,run_id=RUN,run_attempt=1),
            "host_monitor_NRO_SHA256_differs_from_preflight")

    def test_wrong_host_recording_scope(self):
        m=dict(self.monitor,recording="physical audio")
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,m,
            git_sha=SHA,run_id=RUN,run_attempt=1),
            "host_monitor_recording_scope_invalid")

    def test_zero_host_pcm_source(self):
        m=dict(self.monitor,raw_bytes=0)
        self.assertEqual(inspect_bind(self.saved,self.saved,self.preflight,m,
            git_sha=SHA,run_id=RUN,run_attempt=1),
            "host_monitor_source_byte_count_invalid")

    def test_forged_original_digest_rejected(self):
        original=dict(self.saved,original_host_monotonic_csv_sha256="wrong")
        self.assertEqual(inspect_bind(original,original,self.preflight,self.monitor,
            git_sha=SHA,run_id=RUN,run_attempt=1),
            "original_guest_or_host_source_SHA256_invalid")

if __name__=="__main__":
    unittest.main()
