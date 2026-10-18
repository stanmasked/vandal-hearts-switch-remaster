"""Stage301 synthetic negative and boundary controls; no proprietary PCM."""
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

import analyze_nexium_pcm_scene_silence as previous
import audit_nexium_pcm_marker_uncertainty as stage
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
from test_analyze_nexium_pcm_scene_silence import SceneSilenceSynthetic


class MarkerEnvelopeSynthetic(unittest.TestCase):
    def setUp(self):
        self.fixture = SceneSilenceSynthetic(
            methodName="test_reproducibility_and_never_claim_dropouts")
        self.fixture.setUp()
        self.stage300 = self.fixture.classify()

    def run_audit(self, raw=None, previous_report=None):
        return stage.audit_envelopes(
            self.fixture.raw if raw is None else raw,
            self.stage300 if previous_report is None else previous_report,
            rate=self.fixture.rate)

    def test_explicit_marker_envelope_overlap_counts(self):
        result = self.run_audit()
        profiles = result["profiles"]
        self.assertEqual([p["hypothetical_radius_ms"] for p in profiles],
                         [250, 500, 1000])
        self.assertEqual([p["exact_zero_frames_inside"] for p in profiles],
                         [450, 600, 900])
        self.assertEqual([p["exact_zero_frames_outside"] for p in profiles],
                         [4150, 4000, 3700])
        self.assertEqual([p["long_run_zero_frames_inside"] for p in profiles],
                         [450, 600, 900])
        self.assertEqual(profiles[0]["unique_zero_runs_intersecting_envelopes"], 1)
        self.assertEqual(profiles[2]["unique_zero_runs_intersecting_envelopes"], 2)
        self.assertEqual(result["exact_zero_frames_total"], 4600)
        self.assertTrue(result["all_source_frames_and_zero_runs_accounted"])

    def test_all_windows_disjoint_and_conserve_total(self):
        r = self.run_audit()
        for profile in r["profiles"]:
            self.assertEqual(profile["exact_zero_frames_inside"] +
                             profile["exact_zero_frames_outside"], 4600)
            self.assertEqual(profile["envelope_frames"] +
                             profile["outside_envelope_frames"], self.fixture.frames)
            self.assertEqual(profile["envelope_frames"],
                             sum(w["frames"] for w in profile["envelopes"]))
            self.assertEqual(profile["exact_zero_frames_inside"],
                             sum(w["exact_zero_frames"] for w in profile["envelopes"]))
            bounds = [(w["start_frame"], w["end_frame_exclusive"])
                      for w in profile["envelopes"]]
            self.assertTrue(all(a[1] <= b[0] for a, b in
                                zip(bounds, bounds[1:])))

    def test_source_scanner_handles_zero_run_on_eof_and_short_run(self):
        raw = b"\0\0\0\0" * 4 + struct.pack("<hh", 12, -12) * 2 + \
              b"\0\0\0\0" * 3
        self.assertEqual(stage.source_runs(raw), [(0, 4), (6, 9)])
        with self.assertRaises(VirtualPcmEvidenceError):
            stage.source_runs(raw + b"\0")
        with self.assertRaises(VirtualPcmEvidenceError):
            stage.source_runs(b"")

    def test_altered_report_counts_or_zone_boundaries_rejected(self):
        for kind in ("sha", "zone_start", "zone_count", "fraction",
                     "long_intersections", "total", "claim", "threshold", "marker"):
            with self.subTest(kind=kind), self.assertRaises(VirtualPcmEvidenceError):
                bad = copy.deepcopy(self.stage300)
                if kind == "sha":
                    bad["scene_pcm_sha256"] = "0" * 64
                elif kind == "zone_start":
                    bad["zones"][1]["start_frame"] += 1
                elif kind == "zone_count":
                    bad["zones"][1]["exact_zero_frames"] += 1
                elif kind == "fraction":
                    bad["zones"][1]["zero_fraction_of_zone"] = 0.99
                elif kind == "long_intersections":
                    bad["zones"][1]["long_run_intersections"] += 1
                elif kind == "total":
                    bad["exact_zero_frames_total"] += 1
                elif kind == "claim":
                    bad["audio_dropout_or_scene_causality_proven"] = True
                    bad["scene_input_or_music_transition_causality_proven"] = True
                elif kind == "threshold":
                    bad["long_run_minimum_frames"] = 101
                elif kind == "marker":
                    bad["approximate_scene_markers"][2]["approximate_frame_offset"] += 1
                self.run_audit(previous_report=bad)

    def test_changed_pcm_bytes_fail_source_binding(self):
        raw = self.fixture.raw[:-4] + struct.pack("<hh", 3, 3)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(raw=raw)

    def test_no_silence_and_scope_statements(self):
        raw = struct.pack("<hh", 100, -100) * self.fixture.frames
        capture = copy.deepcopy(self.fixture.stage299)
        report = copy.deepcopy(self.fixture.scene_report)
        digest = hashlib.sha256(raw).hexdigest()
        capture["scene_capture"]["pcm_sha256"] = digest
        capture["scene_capture"]["exact_zero_stereo_frames"] = 0
        capture["scene_capture"]["exact_zero_stereo_runs"] = 0
        capture["scene_capture"]["longest_exact_zero_stereo_run_frames"] = 0
        report["pcm_sha256"] = digest
        classified = previous.classify_silence(raw, capture, report, rate=self.fixture.rate)
        r = stage.audit_envelopes(raw, classified, rate=self.fixture.rate)
        self.assertEqual(r["exact_zero_frames_total"], 0)
        self.assertEqual(r["long_run_zero_frames_total"], 0)
        self.assertTrue(all(p["exact_zero_frames_inside"] == 0 for p in r["profiles"]))
        self.assertIs(r["marker_offset_error_measured"], False)
        self.assertIs(r["hypothetical_windows_are_not_confidence_intervals"], True)
        self.assertIs(r["audio_dropout_or_scene_causality_proven"], False)
        self.assertIs(r["physical_speaker_output_or_original_soundtrack_verified"], False)

    def test_replay_deterministic(self):
        self.assertEqual(self.run_audit(), self.run_audit())


if __name__ == "__main__":
    unittest.main()
