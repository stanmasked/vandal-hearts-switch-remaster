"""Stage303 synthetic recorder-stop snapshots; no owned soundtrack or hardware."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import analyze_nexium_pcm_scene_silence as s300
import audit_nexium_pcm_marker_uncertainty as s301
import audit_nexium_pcm_terminal_silence as s302
import audit_nexium_pcm_recorder_stop as s303
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
from test_analyze_nexium_pcm_scene_silence import SceneSilenceSynthetic


def lifecycle(pre, post, *, before=100000, after=100150, signal=1):
    return (f"event,pcm_bytes,host_epoch_ms,signal_success\n"
            f"before_sigint,{pre},{before},{signal}\n"
            f"after_wait,{post},{after},{signal}\n").encode("ascii")


class RecorderStopSynthetic(unittest.TestCase):
    def setUp(self):
        fixture = SceneSilenceSynthetic(
            methodName="test_reproducibility_and_never_claim_dropouts")
        fixture.setUp()
        self.fixture = fixture
        self.raw = fixture.raw
        self.report300 = fixture.classify()
        self.report301 = s301.audit_envelopes(
            self.raw, self.report300, rate=fixture.rate)
        self.report302 = s302.classify_recording_edges(
            self.raw, self.report300, self.report301, rate=fixture.rate)

    def audit(self, csv=None, *, raw=None, p300=None, p301=None, p302=None):
        return s303.audit_recorder_stop(
            self.raw if raw is None else raw,
            self.report300 if p300 is None else p300,
            self.report301 if p301 is None else p301,
            self.report302 if p302 is None else p302,
            lifecycle(len(self.raw), len(self.raw)) if csv is None else csv,
            rate=self.fixture.rate)

    def build(self, raw, pre):
        previous = copy.deepcopy(self.fixture.stage299)
        scene = copy.deepcopy(self.fixture.scene_report)
        runs = s301.source_runs(raw)
        digest = hashlib.sha256(raw).hexdigest()
        cap = previous["scene_capture"]
        cap["pcm_sha256"] = digest
        cap["exact_zero_stereo_frames"] = sum(b - a for a, b in runs)
        cap["exact_zero_stereo_runs"] = len(runs)
        cap["longest_exact_zero_stereo_run_frames"] = max(
            (b - a for a, b in runs), default=0)
        scene["pcm_sha256"] = digest
        a = s300.classify_silence(raw, previous, scene, rate=self.fixture.rate)
        b = s301.audit_envelopes(raw, a, rate=self.fixture.rate)
        c = s302.classify_recording_edges(raw, a, b, rate=self.fixture.rate)
        return s303.audit_recorder_stop(raw, a, b, c, lifecycle(pre, len(raw)),
                                         rate=self.fixture.rate)

    def test_no_terminal_silence_and_zero_appended(self):
        report = self.audit()
        self.assertIsNone(report["terminal_exact_zero_run_stop_overlap"])
        self.assertEqual(report["buffered_bytes_appended_during_stop"], 0)
        self.assertEqual(report["stop_wall_interval_ms"], 150)
        self.assertIs(report["physical_Nintendo_Switch_audio_tested"], False)

    def test_aligned_stop_snapshot_in_middle_of_terminal_zero_run(self):
        raw = self.raw[:-4000] + b"\0" * 4000
        report = self.build(raw, 31500 * 4)
        tail = report["terminal_exact_zero_run_stop_overlap"]
        self.assertEqual(tail["start_frame"], 31000)
        self.assertEqual(tail["frames_before_signal_snapshot_min"], 500)
        self.assertEqual(tail["frames_before_signal_snapshot_max"], 500)
        self.assertEqual(tail["frames_after_signal_snapshot_min"], 500)
        self.assertEqual(tail["frames_after_signal_snapshot_max"], 500)
        self.assertTrue(tail["was_already_present_before_signal_snapshot"])

    def test_unaligned_snapshot_reports_one_frame_uncertainty(self):
        raw = self.raw[:-4000] + b"\0" * 4000
        report = self.build(raw, 31500 * 4 + 1)
        tail = report["terminal_exact_zero_run_stop_overlap"]
        self.assertEqual(tail["frames_before_signal_snapshot_min"], 500)
        self.assertEqual(tail["frames_before_signal_snapshot_max"], 501)
        self.assertEqual(tail["frames_after_signal_snapshot_min"], 499)
        self.assertEqual(tail["frames_after_signal_snapshot_max"], 500)
        self.assertTrue(report["stop_signal_snapshot_partial_stereo_frame"])

    def test_terminal_starts_after_stop_snapshot(self):
        raw = self.raw[:-4000] + b"\0" * 4000
        report = self.build(raw, 30000 * 4)
        tail = report["terminal_exact_zero_run_stop_overlap"]
        self.assertEqual(tail["frames_before_signal_snapshot_min"], 0)
        self.assertEqual(tail["frames_after_signal_snapshot_max"], 1000)
        self.assertFalse(tail["was_already_present_before_signal_snapshot"])

    def test_all_terminal_zeros_before_stop_snapshot(self):
        raw = self.raw[:-4000] + b"\0" * 4000
        report = self.build(raw, len(raw))
        tail = report["terminal_exact_zero_run_stop_overlap"]
        self.assertEqual(tail["frames_after_signal_snapshot_min"], 0)
        self.assertEqual(tail["frames_after_signal_snapshot_max"], 0)
        self.assertEqual(tail["frames_before_signal_snapshot_min"], 1000)

    def test_entire_silent_recording_accounted_once(self):
        raw = b"\0" * len(self.raw)
        r = self.build(raw, len(raw) // 2)
        tail = r["terminal_exact_zero_run_stop_overlap"]
        self.assertEqual(tail["classification"], "whole_recording")
        self.assertEqual(tail["frames_before_signal_snapshot_min"], 16000)
        self.assertEqual(tail["frames_after_signal_snapshot_min"], 16000)

    def test_reject_forged_or_noncanonical_lifecycle(self):
        total = len(self.raw)
        valid = lifecycle(total, total)
        invalid = [
            lifecycle(total, total, signal=0),
            lifecycle(total + 4, total),
            lifecycle(total - 4, total - 4),
            lifecycle(total, total, before=100200, after=100100),
            valid.replace(b"before_sigint", b"after_wait", 1),
            valid.replace(b"after_wait", b"before_sigint", 1),
            valid[:-1],
            valid.replace(b"\n", b"\r\n"),
            valid + b"after_wait,0,100151,1\n",
            valid.replace(b",1\n", b",01\n"),
            valid.replace(b",1\n", b",2\n"),
        ]
        for i, bad in enumerate(invalid):
            with self.subTest(i=i), self.assertRaises(VirtualPcmEvidenceError):
                self.audit(csv=bad)

    def test_source_and_previous_report_mutations_rejected(self):
        p = copy.deepcopy(self.report302)
        p["original_exact_zero_frames"] += 1
        with self.assertRaises(VirtualPcmEvidenceError):
            self.audit(p302=p)
        raw = self.raw[:-4] + struct.pack("<hh", 7, 8)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.audit(raw=raw)

    def test_determinism_and_causal_limits(self):
        a = self.audit()
        self.assertEqual(a, self.audit())
        self.assertTrue(a["host_stop_snapshots_not_sample_exact_guest_audio_times"])
        self.assertTrue(a["host_stop_signal_does_not_prove_guest_playback_end"])
        self.assertFalse(a["original_soundtrack_or_audible_dropout_verified"])


if __name__ == "__main__":
    unittest.main()
