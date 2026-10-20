#!/usr/bin/env python3
"""Stage361 synthetic tampering controls; authentic archive replay is separate."""
import hashlib
import sys
import unittest
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_stage361_original_success_probe import (
    RUN_ID,PINS,VERIFIED,FILES,bound_source,receipt_equals,parse_failed_host_stop,archive_paths
)

ORIGINAL_HOST=(b"event,pcm_bytes,host_epoch_ms,signal_success\n"
    b"before_sigint,8732688,1792449461974,1\n"
    b"after_wait,8732688,1792449461203,1\n")
ORIGINAL_PROBE=(b"scope,value\n"
    b"software_exit_probe_context_only,1\n"
    b"tail_observed,1\n"
    b"tail_begin_guest_ns,37963280677\n"
    b"tail_end_guest_ns,37968564062\n"
    b"tail_elapsed_ns,5283385\n"
    b"normal_submit_attempts_at_tail,1365\n"
    b"last_pre_submit_probe_observed,1\n"
    b"last_pre_submit_probe_attempt,1361\n"
    b"last_pre_submit_probe_queue_status,1\n"
    b"last_pre_submit_probe_queue_count,0\n"
    b"last_pre_submit_probe_age_ns,125833907\n"
    b"last_pre_submit_probe_dropped_count,0\n"
    b"stage351_tail_reason_code,7\n")

class Stage361Tests(unittest.TestCase):
    def test_pinned_authentic_probe_and_host(self):
        self.assertEqual(RUN_ID,39333759265)
        self.assertEqual(hashlib.sha256(ORIGINAL_PROBE).hexdigest(),PINS["probe"])
        self.assertEqual(hashlib.sha256(ORIGINAL_HOST).hexdigest(),PINS["host_stop"])
        self.assertEqual(bound_source(ORIGINAL_PROBE,"probe"),ORIGINAL_PROBE)
        self.assertIn("HOST_STAGE303_FAILED",VERIFIED)
    def test_strict_host_failure_is_not_waived(self):
        x=parse_failed_host_stop(ORIGINAL_HOST)
        self.assertEqual(x["host_wall_clock_regression_ms"],-771)
        self.assertEqual(x["host_pcm_bytes_delta"],0)
        self.assertFalse(x["original_stage303_strict_host_recorder_passed"])
    def test_forbid_fabricated_monotone_host_clock(self):
        forged=ORIGINAL_HOST.replace(b"1792449461203",b"1792449462203")
        with self.assertRaises(ValueError):
            parse_failed_host_stop(forged)
    def test_forbid_fabricated_pcm_growth(self):
        forged=ORIGINAL_HOST.replace(b"after_wait,8732688",b"after_wait,8732692")
        with self.assertRaises(ValueError):
            parse_failed_host_stop(forged)
    def test_forbid_fabricated_stage360_age(self):
        altered=ORIGINAL_PROBE.replace(b"125833907",b"125833906")
        with self.assertRaises(ValueError):
            bound_source(altered,"probe")
    def test_forbid_fabricated_queue_count(self):
        altered=ORIGINAL_PROBE.replace(
            b"last_pre_submit_probe_queue_count,0",
            b"last_pre_submit_probe_queue_count,1")
        with self.assertRaises(ValueError):
            bound_source(altered,"probe")
    def test_receipt_allows_additive_derived_end_age(self):
        old={"original_guest_source_relative_path":"sdmc/switch/vandal-hearts-remake/audio-exit-probe-context-000.csv",
             "tail_observed":True,"last_pre_submit_probe_age_ns":125833907}
        new={"tail_observed":True,"last_pre_submit_probe_age_ns":125833907,
             "last_pre_submit_probe_age_at_tail_end_ns":131117292}
        receipt_equals(new,old,path=old["original_guest_source_relative_path"])
    def test_reject_wrong_receipt_source_path(self):
        with self.assertRaises(ValueError):
            receipt_equals({"tail_observed":True},
                {"tail_observed":True,"original_guest_source_relative_path":"other.csv"},
                path="sdmc/switch/vandal-hearts-remake/audio-exit-probe-context-000.csv")
    def test_reject_forged_receipt_bool_as_int(self):
        with self.assertRaises(ValueError):
            receipt_equals({"tail_observed":True},
                {"tail_observed":1,"original_guest_source_relative_path":"canonical.csv"},
                path="canonical.csv")
    def test_reject_ambiguous_original_archive_filename(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            for filename in FILES.values():
                (root/filename).write_bytes(b"test only\\n")
            self.assertEqual(set(archive_paths(root)),set(FILES))
            duplicate=root/"duplicate"
            duplicate.mkdir()
            (duplicate/FILES["probe"]).write_bytes(b"forged\\n")
            with self.assertRaises(ValueError):
                archive_paths(root)
    def test_reject_linked_original_archive_source(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            for filename in FILES.values():
                (root/filename).write_bytes(b"test only\\n")
            source=root/FILES["probe"]
            source.unlink()
            source.symlink_to(root/FILES["reason"])
            with self.assertRaises(ValueError):
                archive_paths(root)
    def test_reject_missing_receipt_field(self):
        with self.assertRaises(ValueError):
            receipt_equals({},{"tail_observed":True,
                "original_guest_source_relative_path":"canonical.csv"},
                path="canonical.csv")

if __name__=="__main__":
    unittest.main()
