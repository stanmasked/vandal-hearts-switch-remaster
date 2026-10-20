#!/usr/bin/env python3
"""Stage363 synthetic source forgery controls; original-run replay is in CI."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from audit_nexium_recorder_stop_dual_clock_stage362 import audit as audit_host
from audit_nexium_stage363_authentic_guest_host_dual import (
    RUN_ID,PINS,FILES,archive_files,host_source_check,compare_receipt
)

PCM=b"\x00\x00\x00\x00"*4
LEGACY=(b"event,pcm_bytes,host_epoch_ms,signal_success\n"
        b"before_sigint,16,1000,1\n"
        b"after_wait,16,1021,1\n")
PAIRED=(b"event,pcm_bytes,host_epoch_ms,host_monotonic_ns,signal_success\n"
        b"before_sigint,16,1000,1000000000,1\n"
        b"after_wait,16,1021,1020788687,1\n")

def synthetic():
    report362=audit_host(LEGACY,PAIRED)
    report303={
        "result":"SOURCE_BOUND_HOST_RECORDER_STOP_SNAPSHOT_RECONCILED",
        "stop_events":[{"event":"before_sigint","pcm_bytes":16,"host_epoch_ms":1000,
                        "signal_success":1},
                       {"event":"after_wait","pcm_bytes":16,"host_epoch_ms":1021,
                        "signal_success":1}],
        "stop_wall_interval_ms":21,
        "buffered_bytes_appended_during_stop":0,
        "scene_pcm_frames":4,
        "scene_pcm_sha256":hashlib.sha256(PCM).hexdigest(),
        "stage302_original_zero_run_classes_conserved":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_soundtrack_or_audible_dropout_verified":False,
    }
    return report362,report303

class Stage363Tests(unittest.TestCase):
    def test_original_pin_is_specific_neXium_run(self):
        self.assertEqual(RUN_ID,39340120727)
        self.assertEqual(
            PINS["paired"],
            "4695e9c91a74e4c236b7569d60f0d2b98356667ae5280c83980d88bce5d9a76e")
        self.assertEqual(len(PINS),len(FILES))
    def test_host_helper_rejects_fake_pcm_bytes(self):
        a,b=synthetic()
        with self.assertRaises(ValueError):
            host_source_check(LEGACY,PAIRED,a,b,PCM+b"\x00\x00\x00\x00")
    def test_host_helper_rejects_forged_positive_stage303(self):
        a,b=synthetic()
        b["stop_wall_interval_ms"]=20
        with self.assertRaises(ValueError):
            host_source_check(LEGACY,PAIRED,a,b,PCM)
    def test_host_helper_rejects_forged_clock_receipt(self):
        a,b=synthetic()
        a["host_monotonic_elapsed_ns"]+=1
        with self.assertRaises(ValueError):
            host_source_check(LEGACY,PAIRED,a,b,PCM)
    def test_host_helper_rejects_forged_hardware_claim(self):
        a,b=synthetic()
        b["physical_Nintendo_Switch_audio_tested"]=True
        with self.assertRaises(ValueError):
            host_source_check(LEGACY,PAIRED,a,b,PCM)
    def test_guest_receipt_rejects_int_for_true(self):
        with self.assertRaises(ValueError):
            compare_receipt({"tail_observed":True},
                {"tail_observed":1,"original_guest_source_relative_path":"test.csv"},
                "test.csv")
    def test_guest_receipt_rejects_missing_original_path(self):
        with self.assertRaises(ValueError):
            compare_receipt({"stage351_reason_code":7},
                {"stage351_reason_code":7},
                "sdmc/switch/vandal-hearts-remake/test.csv")
    def test_duplicate_raw_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in FILES.values():
                (root/name).write_bytes(b"synthetic only\n")
            self.assertEqual(set(archive_files(root)),set(FILES))
            duplicate=root/"extra"
            duplicate.mkdir()
            (duplicate/FILES["paired"]).write_bytes(b"fake\n")
            with self.assertRaises(ValueError):
                archive_files(root)
    def test_symlinked_original_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in FILES.values():
                (root/name).write_bytes(b"synthetic only\n")
            link=root/FILES["legacy"]
            link.unlink()
            link.symlink_to(root/FILES["paired"])
            with self.assertRaises(ValueError):
                archive_files(root)

if __name__=="__main__":
    unittest.main()
