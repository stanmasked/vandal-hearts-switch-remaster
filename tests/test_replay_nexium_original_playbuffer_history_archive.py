"""Stage323 verify original last16 audout guest source on independent runner."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
sys.path.insert(0,str(ROOT/"tests"))

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import SUBDIR
from audit_nexium_guest_playbuffer_history import (
    HEADER, audit_source as audit_guest_history,
)
from replay_nexium_original_last_playbuffer_archive import read_archive as read_stage321
from replay_nexium_original_playbuffer_history_archive import (
    read_archive,replay_original_history,VERIFIED,SOURCE,CAPTURE,
)
from test_replay_nexium_original_last_playbuffer_archive import (
    OriginalLastServiceCallReplayer,
)


class Stage323OriginalRollingHistoryTests(unittest.TestCase):
    def setUp(self):
        # A source-authentic synthetic fixture; no retail music,
        # physical hardware or non-original-neXium claims.
        OriginalLastServiceCallReplayer.setUp(self)
        self.base=read_stage321(self.root)
        last=self.receipt["last_successful_PlayBuffer_begin_guest_ns"]
        first=last-15*1000
        self.history=HEADER+b"".join(
            f"380,{seq},{first+(seq-365)*1000},"
            f"{first+(seq-365)*1000+500},1\n".encode()
            for seq in range(365,380)
        )+(
            f"380,380,{last},"
            f"{self.receipt['last_successful_PlayBuffer_return_guest_ns']},1\n"
        ).encode()
        self.history_doc=audit_guest_history(self.history,self.receipt)
        self.history_doc["original_guest_history_source_observed"]=True
        self.history_doc["original_guest_history_source_path"]=str(SUBDIR/SOURCE)
        self.history_doc["original_guest_history_bytes_preserved"]=True
        (self.root/SOURCE).write_bytes(self.history)
        (self.root/CAPTURE).write_text(json.dumps(self.history_doc)+"\n")

    def replay(self,orig=None,history=None,receipt=None,run=None):
        return replay_original_history(
            self.base if orig is None else orig,
            self.history if history is None else history,
            self.history_doc if receipt is None else receipt,
            self.run if run is None else run)

    def test_all_original_sources_and_prior_baseline_reproduced(self):
        r=self.replay()
        self.assertEqual(r["result"],VERIFIED)
        self.assertTrue(r["original_stage322_history_CSV_and_receipt_replayed"])
        self.assertTrue(r["original_stage307_308_310_313_314_317_320_321_sources_replayed"])
        self.assertEqual(r["recent_original_service_call_count"],16)
        self.assertEqual(r["prior_successful_calls_in_window"],15)
        self.assertEqual(r["prior_successful_lower_median_duration_guest_ns"],500)
        self.assertEqual(r["last_minus_prior_lower_median_guest_ns"],
                         self.receipt["last_successful_PlayBuffer_software_duration_ns"]-500)
        self.assertTrue(r["has_source_verified_prior_call_baseline"])
        self.assertFalse(r["physical_Nintendo_Switch_audio_tested"])

    def test_read_archived_original_source_bytes_not_derived_json(self):
        sources,raw,report=read_archive(self.root)
        self.assertEqual(sources,self.base)
        self.assertEqual(raw,self.history)
        self.assertEqual(report,self.history_doc)

    def test_missing_original_csv_fails_no_JSON_fallback(self):
        (self.root/SOURCE).unlink()
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_duplicate_guest_original_history_fails(self):
        sub=self.root/"duplicate"
        sub.mkdir()
        (sub/SOURCE).write_bytes(self.history)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_original_history_symlink_is_untrusted(self):
        source=self.root/SOURCE
        backed=self.root/"real_history"
        backed.write_bytes(self.history)
        source.unlink()
        source.symlink_to(backed)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_original_receipt_separate_from_source_rejected(self):
        sub=self.root/"other"
        sub.mkdir()
        (self.root/CAPTURE).rename(sub/CAPTURE)
        with self.assertRaises(TraceError):
            read_archive(self.root)

    def test_changed_history_original_bytes_rejected(self):
        bad=self.history.replace(b"380,378,",b"380,377,")
        with self.assertRaises(TraceError):
            self.replay(history=bad)

    def test_changed_final_call_original_end_rejected(self):
        old=self.receipt["last_successful_PlayBuffer_return_guest_ns"]
        bad=self.history.replace(f"{old},1\n".encode(),
                                 f"{old-1},1\n".encode())
        with self.assertRaises(TraceError):
            self.replay(history=bad)

    def test_forged_capture_receipt_SHA_rejected(self):
        bad=copy.deepcopy(self.history_doc)
        bad["original_guest_history_csv_sha256"]="a"*64
        with self.assertRaises(TraceError):
            self.replay(receipt=bad)

    def test_swapped_original_last_call_source_rejected(self):
        old=list(self.base)
        old[3]=old[3].replace(b"successes,380",b"successes,379")
        with self.assertRaises(TraceError):
            self.replay(orig=tuple(old))

    def test_original_source_run_identity_required(self):
        with self.assertRaises(TraceError):
            self.replay(run=0)

    def test_no_baseline_cannot_be_fabricated(self):
        doc=copy.deepcopy(self.receipt)
        doc["PlayBuffer_call_attempt_count"]=1
        doc["successful_PlayBuffer_call_count"]=1
        doc["last_successful_PlayBuffer_attempt_index"]=1
        # A new original last-call summary has to match the raw last
        # call bytes; simply forging its metadata cannot pass Stage321.
        old=list(self.base)
        old[4]=doc
        with self.assertRaises(TraceError):
            self.replay(orig=tuple(old))

    def test_original_audio_scope_boundaries(self):
        r=self.replay()
        self.assertTrue(r["guest_software_call_is_NOT_DAC_or_speaker_sound"])
        self.assertIs(r["original_guest_to_host_PCM_clock_fit_verified"],False)
        self.assertIs(r["plus_caused_audible_dropout_verified"],False)

    def test_replay_is_deterministic(self):
        self.assertEqual(self.replay(),self.replay())

if __name__=="__main__":
    unittest.main()
