"""Stage306: refuse duplicate/forged capture comparisons and audio overclaims."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
import compare_nexium_pcm_plus_capture_runs as stage306


def synthetic(sha: str = "a", onset: int | None = 200000) -> dict:
    total = 240000
    report = {
        "result": stage306.STAGE305_RESULT,
        "sample_rate_hz": 48000,
        "original_scene_pcm_frames": total,
        "original_scene_pcm_sha256": sha * 64,
        "all_original_stage299_through_stage304_evidence_replayed": True,
        "file_size_and_wall_time_snapshots_are_not_guest_input_timestamps": True,
        "temporal_overlap_is_not_plus_audio_causality": True,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
        "plus_hold_host_ms_between_snapshots": 300,
        "before_plus_500ms_baseline": {
            "start_frame": 175000, "end_frame_exclusive": 199000,
            "frames": 24000, "exact_zero_stereo_frames": 0,
            "nonzero_stereo_frames": 24000,
        },
        "plus_snapshot_control_window": {
            "start_frame": 199000, "end_frame_exclusive": 201000,
            "frames": 2000, "exact_zero_stereo_frames": 1000,
            "nonzero_stereo_frames": 1000,
        },
        "after_plus_500ms_window": {
            "start_frame": 201000, "end_frame_exclusive": 225000,
            "frames": 24000, "exact_zero_stereo_frames": 24000,
            "nonzero_stereo_frames": 0,
        },
        "terminal_exact_zero_onset": None,
    }
    if onset is not None:
        category = (
            "present_by_before_plus_snapshot" if onset <= 199000
            else "between_buffered_plus_snapshots" if onset <= 201000
            else "later_than_after_plus_snapshot" if onset > 201000
            else "ambiguous_partial_stereo_frame_boundary"
        )
        report["terminal_exact_zero_onset"] = {
            "start_frame": onset,
            "end_frame_exclusive": total,
            "frames": total - onset,
            "position_relative_to_buffered_snapshots": category,
            "frames_after_press_snapshot_min": onset - 199000,
            "frames_after_press_snapshot_max": onset - 199000,
            "frames_before_release_snapshot_min": 201000 - onset,
            "frames_before_release_snapshot_max": 201000 - onset,
            "sample_alignment_is_not_host_input_timestamp": True,
        }
    return report


class IndependentCaptureSynthetic(unittest.TestCase):
    def test_two_independent_inside_plus_and_no_causal_claim(self):
        x = stage306.compare_captures([(39134382535, synthetic("a")),
                                       (39135617807, synthetic("b"))])
        self.assertEqual(x["run_count"], 2)
        self.assertEqual(x["onset_class_counts"],
                         {"between_buffered_plus_snapshots": 2})
        self.assertTrue(x["all_terminating_zero_onsets_bracketed_by_host_Plus_snapshots"])
        self.assertFalse(x["original_music_or_audible_dropout_verified"])
        self.assertFalse(x["physical_Nintendo_Switch_audio_tested"])
        self.assertTrue(x["distinct_original_scene_pcm_sha256"])

    def test_independent_captures_can_disagree_without_false_failure(self):
        x = stage306.compare_captures([
            (39134382535, synthetic("a", 200000)),
            (39135617807, synthetic("b", 190000)),
        ])
        self.assertFalse(x["same_terminal_onset_class_across_runs"])
        self.assertFalse(x["all_terminating_zero_onsets_bracketed_by_host_Plus_snapshots"])
        self.assertEqual(sum(x["onset_class_counts"].values()), 2)

    def test_no_terminal_run_yields_explicit_nonrepeatability(self):
        r = stage306.compare_captures([
            (39134382535, synthetic("a")),
            (39135617807, synthetic("b", None)),
        ])
        self.assertEqual(r["onset_class_counts"]["no_terminal_zero_run"], 1)
        self.assertFalse(r["all_terminating_zero_onsets_bracketed_by_host_Plus_snapshots"])

    def test_duplicate_run_id_rejected(self):
        with self.assertRaises(VirtualPcmEvidenceError):
            stage306.compare_captures([(1, synthetic("a")), (1, synthetic("b"))])

    def test_same_pcm_sha_rejected_across_different_run_ids(self):
        with self.assertRaises(VirtualPcmEvidenceError):
            stage306.compare_captures([(1, synthetic("a")), (2, synthetic("a"))])

    def test_missing_or_excessive_runs_rejected(self):
        for inputs in ([ (1, synthetic("a")) ], []):
            with self.subTest(length=len(inputs)), self.assertRaises(VirtualPcmEvidenceError):
                stage306.compare_captures(inputs)
        with self.assertRaises(VirtualPcmEvidenceError):
            stage306.compare_captures([(i + 1, synthetic(chr(97 + i)))
                                       for i in range(9)])

    def test_falsified_scope_rejected(self):
        for field, new_value in (
            ("physical_Nintendo_Switch_audio_tested", True),
            ("original_soundtrack_or_audible_dropout_verified", True),
            ("temporal_overlap_is_not_plus_audio_causality", False),
            ("all_original_stage299_through_stage304_evidence_replayed", False),
        ):
            bad = synthetic("b")
            bad[field] = new_value
            with self.subTest(field=field), self.assertRaises(VirtualPcmEvidenceError):
                stage306.compare_captures([(1, synthetic("a")), (2, bad)])

    def test_source_frame_conservation_mutations_rejected(self):
        for field, value in (("frames", 1999),
                             ("exact_zero_stereo_frames", 2001),
                             ("end_frame_exclusive", 241000)):
            bad = synthetic("b")
            bad["plus_snapshot_control_window"][field] = value
            with self.subTest(field=field), self.assertRaises(VirtualPcmEvidenceError):
                stage306.compare_captures([(1, synthetic("a")), (2, bad)])

    def test_untrue_onset_class_or_source_frame_distance_rejected(self):
        for field, value in (
            ("position_relative_to_buffered_snapshots", "later_than_after_plus_snapshot"),
            ("frames_after_press_snapshot_min", 999),
            ("frames_before_release_snapshot_max", 2000),
        ):
            bad = synthetic("b")
            bad["terminal_exact_zero_onset"][field] = value
            with self.subTest(field=field), self.assertRaises(VirtualPcmEvidenceError):
                stage306.compare_captures([(1, synthetic("a")), (2, bad)])

    def test_invalid_digest_and_unknown_rate_rejected(self):
        for field, value in (
            ("original_scene_pcm_sha256", "0xz"),
            ("sample_rate_hz", 44100),
            ("plus_hold_host_ms_between_snapshots", 0),
        ):
            bad = synthetic("b")
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(VirtualPcmEvidenceError):
                stage306.compare_captures([(1, synthetic("a")), (2, bad)])

    def test_deterministic_comparison(self):
        pair=[(1,synthetic("a")), (2,synthetic("b"))]
        self.assertEqual(stage306.compare_captures(pair), stage306.compare_captures(pair))


if __name__ == "__main__":
    unittest.main()
