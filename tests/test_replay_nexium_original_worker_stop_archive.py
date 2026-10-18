"""Stage318 independent worker stop original guest CSV and optical CRC tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import SUBDIR
from audit_nexium_guest_optical_exit_clock import audit_guest_clocks
from audit_nexium_guest_worker_stop_observed import (
    audit_worker_stop_csv, FILE as STOP_FILE,
)
from replay_nexium_original_guest_exit_archive import reconstructed_stage310
from replay_nexium_original_audout_exit_archive import (
    reconstruct_page_report,reconstruct_stage314,
)
from replay_nexium_original_worker_stop_archive import (
    audit_original_worker_stop,read_archive,STAGE317,RESULT,
)
from test_compare_nexium_guest_exit_cohort import fixture


def build_sources(index=0):
    run,png,guest,exit_raw,_=fixture(index)
    t=guest["guest_monotonic_timestamps_ns"]
    page=t["stop_requested"]+100
    tail=t["worker_cleanup_entered"]+40
    original_page=("event,value\n"
        "page_return_count,380\n"
        f"last_page_return_guest_ns,{page}\n"
        "last_page_frames,128\n"
        f"tail_attempt_guest_ns,{tail}\n"
        f"tail_success_return_guest_ns,{tail+100}\n").encode()
    optical=audit_guest_clocks(png,guest)
    third=reconstructed_stage310(exit_raw,optical)
    s313=reconstruct_page_report(original_page,guest)
    s314=reconstruct_stage314(original_page,exit_raw,s313)
    stop_time=t["stop_requested"]+500
    original_stop=(f"event,guest_monotonic_ns\n"
                   f"worker_stop_observed,{stop_time}\n").encode()
    stage317=audit_worker_stop_csv(original_stop,guest,s313)
    stage317["original_worker_stop_source_observed"]=True
    stage317["original_worker_stop_source_path"]=str(SUBDIR/STOP_FILE)
    stage317["original_worker_stop_csv_bytes_preserved"]=True
    return (
        (exit_raw,original_page,png,guest,optical,third,s313,s314),
        original_stop,stage317,run
    )


class OriginalGuestWorkerStopTests(unittest.TestCase):
    def setUp(self):
        self.originals,self.stop,self.receipt,self.run=build_sources()
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        files={
            "audio-exit-timeline-000.csv":self.originals[0],
            "audio-exit-output-000.csv":self.originals[1],
            "scene-optical-trace.png":self.originals[2],
            STOP_FILE:self.stop,
        }
        for name,data in files.items():
            (self.root/name).write_bytes(data)
        names=("guest-audio-exit-timeline-stage307.json",
               "guest-optical-exit-clock-stage308.json",
               "guest-original-exit-source-stage310.json",
               "guest-last-audout-release-stage313.json",
               "guest-original-audout-last-page-stage314.json")
        for name,data in zip(names,self.originals[3:]):
            (self.root/name).write_text(json.dumps(data,sort_keys=True)+"\n")
        (self.root/STAGE317).write_text(
            json.dumps(self.receipt,sort_keys=True)+"\n")

    def replay(self,originals=None,stop=None,receipt=None):
        return audit_original_worker_stop(
            self.originals if originals is None else originals,
            self.stop if stop is None else stop,
            self.receipt if receipt is None else receipt,
            self.run)

    def test_source_original_worker_stop_replays_every_prior_receipt(self):
        r=self.replay()
        self.assertEqual(r["result"],RESULT)
        self.assertTrue(r["original_guest_worker_stop_source_bytes_independently_reaudited"])
        self.assertTrue(r["original_guest_exit_and_last_page_bytes_independently_reaudited"])
        self.assertTrue(r["original_guest_crc_optical_frame_independently_replayed"])
        self.assertTrue(r["original_stage317_receipt_reproduced"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])
        self.assertEqual(r["guest_last_page_return_to_worker_stop_observed_ns"],400)
        self.assertEqual(r["guest_worker_stop_observed_to_cleanup_ns"],700)

    def test_all_original_sources_remain_colocated(self):
        original,raw,report=read_archive(self.root)
        self.assertEqual(original,self.originals)
        self.assertEqual(raw,self.stop)
        self.assertEqual(report,self.receipt)

    def test_independent_replay_deterministic(self):
        self.assertEqual(self.replay(),self.replay())

    def test_missing_original_worker_stop_csv_fails_not_json_fallback(self):
        (self.root/STOP_FILE).unlink()
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_duplicate_original_worker_stop_csv_rejected(self):
        duplicate=self.root/"duplicate"
        duplicate.mkdir()
        (duplicate/STOP_FILE).write_bytes(self.stop)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_symlink_guest_original_marker_rejected(self):
        path=self.root/STOP_FILE
        real=self.root/"real-worker-stop"
        real.write_bytes(self.stop)
        path.unlink()
        path.symlink_to(real)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_original_worker_stop_source_separated_from_audout_csv_rejected(self):
        child=self.root/"disconnected"
        child.mkdir()
        (self.root/STOP_FILE).rename(child/STOP_FILE)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_changed_raw_worker_stop_timestamp_rejected(self):
        broken=self.stop.replace(
            b"worker_stop_observed,5000800",b"worker_stop_observed,5000900")
        self.assertNotEqual(broken,self.stop)
        with self.assertRaises(TraceError):
            self.replay(stop=broken)

    def test_forged_stage317_sha_rejected(self):
        altered=copy.deepcopy(self.receipt)
        altered["original_guest_worker_stop_csv_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.replay(receipt=altered)

    def test_forged_last_page_original_bytes_rejected(self):
        args=list(self.originals)
        args[1]=args[1].replace(b"page_return_count,380",
                                 b"page_return_count,381")
        with self.assertRaises(TraceError):
            self.replay(originals=tuple(args))

    def test_forged_exit_original_bytes_rejected(self):
        args=list(self.originals)
        args[0]=args[0].replace(b"stop_requested",b"STOP_REQUESTED")
        with self.assertRaises((TraceError,ValueError)):
            self.replay(originals=tuple(args))

    def test_optical_guest_original_crc_source_tamper_rejected(self):
        other=build_sources(1)
        args=list(self.originals)
        args[2]=other[0][2]
        with self.assertRaises(TraceError):
            self.replay(originals=tuple(args))

    def test_missing_worker_observation_zero_is_not_pass(self):
        raw=b"event,guest_monotonic_ns\nworker_stop_observed,0\n"
        with self.assertRaises(TraceError):
            self.replay(stop=raw)

    def test_audio_hardware_claim_remains_false(self):
        r=self.replay()
        self.assertTrue(r["guest_audout_buffer_return_not_last_audible_sample"])
        self.assertTrue(r["guest_mailbox_stop_not_physical_DAC_stop"])
        self.assertTrue(r["guest_monotonic_not_synchronized_with_host_PCM"])
        self.assertIs(r["plus_causes_audible_dropout_verified"],False)

if __name__=="__main__":
    unittest.main()
