"""Stage321 original PlayBuffer source independent replay adversarial controls."""
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
from audit_nexium_guest_last_playbuffer import (
    audit_original, FILE as PLAYBUFFER_SOURCE,
)
from replay_nexium_original_last_playbuffer_archive import (
    independently_replay,read_archive,CAPTURE_RECEIPT,VERIFIED,
)
from test_replay_nexium_original_worker_stop_archive import build_sources


class OriginalLastServiceCallReplayer(unittest.TestCase):
    def setUp(self):
        self.originals,self.worker_raw,self.stage317,self.run=build_sources(0)
        stamps=self.originals[3]["guest_monotonic_timestamps_ns"]
        stop=stamps["stop_requested"]
        page=self.originals[6]["last_page_return_guest_ns"]
        begin=stop-1000
        end=page-10
        self.service_source=(f"event,value\n"
            "attempts,380\n"
            "successes,380\n"
            "failures,0\n"
            "last_success_attempt,380\n"
            f"last_success_begin_guest_ns,{begin}\n"
            f"last_success_end_guest_ns,{end}\n"
            "nonmonotonic_rejected,0\n").encode()
        self.receipt=audit_original(self.service_source,self.originals[3],
                                    self.originals[6],self.stage317)
        self.receipt["original_guest_playbuffer_source_observed"]=True
        self.receipt["original_guest_playbuffer_source_path"]=str(
            SUBDIR/PLAYBUFFER_SOURCE)
        self.receipt["original_source_bytes_preserved"]=True
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        binary={
            "audio-exit-timeline-000.csv":self.originals[0],
            "audio-exit-output-000.csv":self.originals[1],
            "scene-optical-trace.png":self.originals[2],
            "audio-exit-worker-stop-000.csv":self.worker_raw,
            PLAYBUFFER_SOURCE:self.service_source,
        }
        for name,raw in binary.items():
            (self.root/name).write_bytes(raw)
        names=("guest-audio-exit-timeline-stage307.json",
               "guest-optical-exit-clock-stage308.json",
               "guest-original-exit-source-stage310.json",
               "guest-last-audout-release-stage313.json",
               "guest-original-audout-last-page-stage314.json")
        for name,record in zip(names,self.originals[3:]):
            (self.root/name).write_text(json.dumps(record)+"\n")
        (self.root/"guest-worker-stop-observed-stage317.json").write_text(
            json.dumps(self.stage317)+"\n")
        (self.root/CAPTURE_RECEIPT).write_text(json.dumps(self.receipt)+"\n")

    def replay(self,source=None,receipt=None,originals=None):
        return independently_replay(
            self.originals if originals is None else originals,
            self.worker_raw,self.stage317,
            self.service_source if source is None else source,
            self.receipt if receipt is None else receipt,
            self.run)

    def test_full_original_source_chain_reproduced(self):
        result=self.replay()
        self.assertEqual(result["result"],VERIFIED)
        self.assertTrue(result["original_PlayBuffer_CSV_bytes_independently_reaudited"])
        self.assertTrue(result["capture_time_stage307_308_310_313_314_317_320_reproduced"])
        self.assertTrue(result["original_guest_optical_CRC_replayed"])
        self.assertEqual(result["last_call_position_relative_to_stop_request"],
                         "last_successful_PlayBuffer_spanned_stop_request")
        self.assertEqual(
            result["last_successful_PlayBuffer_overlap_after_stop_request_ns"],90)
        self.assertEqual(
            result["last_call_return_to_last_page_witness_guest_ns"],10)
        self.assertFalse(result["physical_Nintendo_Switch_audio_tested"])

    def test_separate_archive_replay_reads_actual_original_bytes(self):
        archive=read_archive(self.root)
        self.assertEqual(archive[3],self.service_source)
        self.assertEqual(archive[4],self.receipt)
        self.assertEqual(independently_replay(*archive,self.run),self.replay())

    def test_missing_original_never_falls_back_to_receipt(self):
        (self.root/PLAYBUFFER_SOURCE).unlink()
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_duplicate_original_source_rejected(self):
        child=self.root/"duplicate"
        child.mkdir()
        (child/PLAYBUFFER_SOURCE).write_bytes(self.service_source)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_symlink_original_guest_source_rejected(self):
        source=self.root/PLAYBUFFER_SOURCE
        outside=self.root/"other"
        outside.write_bytes(self.service_source)
        source.unlink()
        source.symlink_to(outside)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_source_receipt_must_be_co_located(self):
        child=self.root/"detached"
        child.mkdir()
        (self.root/CAPTURE_RECEIPT).rename(child/CAPTURE_RECEIPT)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_forged_stage320_receipt_source_sha_rejected(self):
        receipt=copy.deepcopy(self.receipt)
        receipt["original_last_playbuffer_csv_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.replay(receipt=receipt)

    def test_changed_original_PlayBuffer_bytes_rejected(self):
        source=self.service_source.replace(
            b"last_success_attempt,380",b"last_success_attempt,379")
        with self.assertRaises(TraceError):
            self.replay(source=source)

    def test_swapped_original_guest_scene_optical_png_rejected(self):
        _,_,_,_=build_sources(1)
        from test_compare_nexium_guest_exit_cohort import fixture
        original=list(self.originals)
        original[2]=fixture(1)[1]
        with self.assertRaises(TraceError):
            self.replay(originals=tuple(original))

    def test_empty_original_source_does_not_count(self):
        with self.assertRaises(TraceError):
            self.replay(source=b"")

    def test_original_source_run_identity_is_required(self):
        with self.assertRaises(TraceError):
            independently_replay(
                self.originals,self.worker_raw,self.stage317,
                self.service_source,self.receipt,0)

    def test_receipt_cannot_claim_speaker_output(self):
        receipt=copy.deepcopy(self.receipt)
        receipt["audible_dropout_verified"]=True
        with self.assertRaises(TraceError):
            self.replay(receipt=receipt)
        result=self.replay()
        self.assertTrue(result["guest_software_time_not_host_PCM_or_DAC_sample_clock"])
        self.assertTrue(result["last_service_call_is_not_entire_stop_delay_proof"])
        self.assertFalse(result["plus_causes_audible_dropout_verified"])

    def test_determinism(self):
        self.assertEqual(self.replay(),self.replay())


if __name__=="__main__":
    unittest.main()
