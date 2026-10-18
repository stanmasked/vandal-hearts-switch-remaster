"""Stage302 synthetic source-run edge censoring and report forgery regressions."""
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
import analyze_nexium_pcm_scene_silence as stage300
import audit_nexium_pcm_marker_uncertainty as stage301
import audit_nexium_pcm_terminal_silence as stage302
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
from test_analyze_nexium_pcm_scene_silence import SceneSilenceSynthetic


class BoundaryCensoredSynthetic(unittest.TestCase):
    def setUp(self):
        self.fixture = SceneSilenceSynthetic(
            methodName="test_reproducibility_and_never_claim_dropouts")
        self.fixture.setUp()
        self.raw = self.fixture.raw
        self.report300 = self.fixture.classify()
        self.report301 = stage301.audit_envelopes(
            self.raw, self.report300, rate=self.fixture.rate)

    def audit(self, raw=None, s300=None, s301=None):
        return stage302.classify_recording_edges(
            self.raw if raw is None else raw,
            self.report300 if s300 is None else s300,
            self.report301 if s301 is None else s301,
            rate=self.fixture.rate)

    def build(self, raw):
        """Regenerate synthetic pinned evidence for a different PCM source."""
        previous = copy.deepcopy(self.fixture.stage299)
        scene = copy.deepcopy(self.fixture.scene_report)
        runs = stage301.source_runs(raw)
        digest = hashlib.sha256(raw).hexdigest()
        capture = previous["scene_capture"]
        capture["pcm_sha256"] = digest
        capture["exact_zero_stereo_frames"] = sum(b - a for a, b in runs)
        capture["exact_zero_stereo_runs"] = len(runs)
        capture["longest_exact_zero_stereo_run_frames"] = max(
            (b - a for a, b in runs), default=0)
        scene["pcm_sha256"] = digest
        s300 = stage300.classify_silence(
            raw, previous, scene, rate=self.fixture.rate)
        s301 = stage301.audit_envelopes(raw, s300, rate=self.fixture.rate)
        return stage302.classify_recording_edges(
            raw, s300, s301, rate=self.fixture.rate)

    def test_prefix_and_three_interior_runs_conserved(self):
        report = self.audit()
        parts = report["counts_by_recording_boundary"]
        self.assertEqual(parts["recording_start"]["run_count"], 1)
        self.assertEqual(parts["recording_start"]["frames"], 300)
        self.assertEqual(parts["interior"]["run_count"], 3)
        self.assertEqual(parts["interior"]["frames"], 4300)
        self.assertEqual(parts["recording_end"]["run_count"], 0)
        self.assertEqual(parts["whole_recording"]["run_count"], 0)
        self.assertIsNone(report["terminal_run"])
        self.assertIsNone(report["terminal_run_starts_after_last_host_marker"])
        self.assertTrue(report["every_original_zero_frame_accounted_once"])

    def test_explicit_trailing_run_must_not_count_as_internal(self):
        raw = self.raw[:-4000] + b"\0" * 4000
        report = self.build(raw)
        parts = report["counts_by_recording_boundary"]
        self.assertEqual(parts["recording_end"]["frames"], 1000)
        self.assertEqual(parts["recording_end"]["run_count"], 1)
        self.assertEqual(parts["recording_end"]["long_run_count"], 1)
        self.assertEqual(parts["interior"]["frames"], 4300)
        self.assertEqual(report["terminal_run"]["start_frame"], 31000)
        self.assertTrue(report["terminal_run_starts_after_last_host_marker"])

    def test_whole_recording_zero_counted_once(self):
        report = self.build(b"\0" * len(self.raw))
        parts = report["counts_by_recording_boundary"]
        self.assertEqual(parts["whole_recording"]["frames"], self.fixture.frames)
        self.assertEqual(parts["whole_recording"]["run_count"], 1)
        self.assertEqual(parts["recording_start"]["frames"], 0)
        self.assertEqual(parts["recording_end"]["frames"], 0)
        self.assertEqual(parts["interior"]["frames"], 0)
        self.assertEqual(report["terminal_run"]["classification"], "whole_recording")
        self.assertFalse(report["terminal_run_starts_after_last_host_marker"])

    def test_zero_silence_has_no_terminal_run(self):
        raw = struct.pack("<hh", 1, -1) * self.fixture.frames
        report = self.build(raw)
        self.assertEqual(report["original_exact_zero_frames"], 0)
        self.assertEqual(report["original_exact_zero_runs"], 0)
        self.assertIsNone(report["terminal_run"])
        self.assertEqual(sum(p["frames"] for p in
                             report["counts_by_recording_boundary"].values()), 0)

    def test_pinned_stage301_and_top20_mutations_rejected(self):
        for kind in ("stage301", "longest_run_start", "longest_run_length",
                     "longest_run_seconds", "longest_count", "claim"):
            with self.subTest(kind=kind), self.assertRaises(VirtualPcmEvidenceError):
                p300 = copy.deepcopy(self.report300)
                p301 = copy.deepcopy(self.report301)
                if kind == "stage301":
                    p301["exact_zero_frames_total"] += 1
                elif kind == "longest_run_start":
                    p300["longest_zero_runs_top20"][0]["start_frame"] += 1
                elif kind == "longest_run_length":
                    p300["longest_zero_runs_top20"][0]["frames"] += 1
                elif kind == "longest_run_seconds":
                    p300["longest_zero_runs_top20"][0]["seconds"] += 0.5
                elif kind == "longest_count":
                    p300["longest_zero_runs_top20"] = []
                elif kind == "claim":
                    p301["audio_dropout_or_scene_causality_proven"] = True
                self.audit(s300=p300, s301=p301)

    def test_pcm_bytes_tamper_rejected(self):
        altered = self.raw[:-4] + struct.pack("<hh", 9, 9)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.audit(raw=altered)

    def test_reproducibility_and_scope(self):
        first = self.audit()
        self.assertEqual(first, self.audit())
        self.assertIs(first["virtual_monitor_end_cannot_establish_gameplay_or_audio_end"], True)
        self.assertIs(first["audible_dropout_or_music_scene_causality_verified"], False)
        self.assertIs(first["physical_Nintendo_Switch_audio_tested"], False)


if __name__ == "__main__":
    unittest.main()
