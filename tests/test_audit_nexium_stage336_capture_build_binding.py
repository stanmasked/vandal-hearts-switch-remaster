"""Stage336 source-replayed guest/host to identical-run NeXium NRO binding tests."""
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
from audit_nexium_stage334_capture_manifest import audit_original_capture
from audit_nexium_stage336_capture_build_binding import bind_sources,RESULT
from test_audit_nexium_stage334_capture_manifest import sample_source

SHA="a"*40
NRO_SHA="b"*64
RUN=39180000000


class SameRunSourceToNroBindingTests(unittest.TestCase):
    def setUp(self):
        self.src=sample_source()
        self.saved=audit_original_capture(self.src)
        self.preflight={
            "result":"SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
            "git_sha":SHA,
            "run_id":RUN,
            "run_attempt":1,
            "nro_filename":"vandal-hearts-prototype.nro",
            "nro_sha256":NRO_SHA,
            "nro_bytes":124000,
            "hardware_status":"HARDWARE NOT TESTED",
        }
        self.monitor={
            "source_nro_sha256":NRO_SHA,
            "hardware_status":"HARDWARE NOT TESTED",
            "recording":"virtual PulseAudio null-sink monitor; not audible playback",
            "sample_format":"s16le stereo 48000Hz",
            "raw_bytes":1024,
        }

    def verify(self,src=None,saved=None,preflight=None,monitor=None,sha=SHA,run=RUN,attempt=1):
        return bind_sources(
            self.src if src is None else src,
            self.saved if saved is None else saved,
            self.preflight if preflight is None else preflight,
            self.monitor if monitor is None else monitor,
            git_sha=sha,run_id=run,run_attempt=attempt)

    def test_source_original_exact_run_and_nro_identity_replayed(self):
        r=self.verify()
        self.assertEqual(r["result"],RESULT)
        self.assertEqual(r["github_run_id"],RUN)
        self.assertEqual(r["source_nro_sha256"],NRO_SHA)
        self.assertEqual(r["original_guest_last_software_duration_ns"],11225937)
        self.assertTrue(r["original_stage320_322_325_guest_host_receipts_replayed_again"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_genuine_slow_new_guest_call_does_not_fail_source_validation(self):
        src=sample_source(last_duration=41000000,prior_duration=30000000)
        r=self.verify(src=src,saved=audit_original_capture(src))
        self.assertEqual(r["original_guest_prior_lower_median_software_ns"],30000000)
        self.assertEqual(r["original_guest_last_first_possible_rank"],16)

    def test_forged_original_stage334_receipt_rejected(self):
        r=copy.deepcopy(self.saved)
        r["original_guest_last_call_duration_software_ns"]+=1
        with self.assertRaises(ExitTimelineError):
            self.verify(saved=r)

    def test_changed_original_guest_source_rejected(self):
        source=copy.deepcopy(self.src)
        source["history_csv"]+=b"CORRUPTED\n"
        with self.assertRaises(ExitTimelineError):
            self.verify(src=source)

    def test_wrong_commit_sha_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.verify(sha="f"*40)

    def test_wrong_run_number_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.verify(run=RUN+1)

    def test_wrong_run_attempt_rejected(self):
        with self.assertRaises(ExitTimelineError):
            self.verify(attempt=2)

    def test_tampered_preflight_nro_byte_count_rejected(self):
        fake=copy.deepcopy(self.preflight)
        fake["nro_bytes"]=123
        with self.assertRaises(ExitTimelineError):
            self.verify(preflight=fake)

    def test_monitor_nro_digest_mismatch_rejected(self):
        fake=copy.deepcopy(self.monitor)
        fake["source_nro_sha256"]="c"*64
        with self.assertRaises(ExitTimelineError):
            self.verify(monitor=fake)

    def test_monitor_speaker_claim_rejected(self):
        fake=copy.deepcopy(self.monitor)
        fake["hardware_status"]="REAL_HARDWARE_AUDIO_VERIFIED"
        with self.assertRaises(ExitTimelineError):
            self.verify(monitor=fake)

    def test_no_absolute_original_guest_or_host_timestamps_in_compact_witness(self):
        r=self.verify()
        data=json.dumps(r,sort_keys=True)
        for forbidden in ("begin_guest_ns","end_guest_ns","host_epoch_ms","123450000000","pcm_samples"):
            self.assertNotIn(forbidden,data)
        self.assertTrue(r["guest_software_timestamps_not_converted_to_host_pcm_clock"])


if __name__=="__main__":
    unittest.main()
