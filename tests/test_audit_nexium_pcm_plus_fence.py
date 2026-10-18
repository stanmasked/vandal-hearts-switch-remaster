"""Stage305 source-bound Plus file-snapshot bracket synthetic regressions."""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import audit_nexium_pcm_marker_uncertainty as s301
import audit_nexium_pcm_terminal_silence as s302
import audit_nexium_pcm_recorder_stop as s303
import audit_nexium_pcm_exit_controls as s304
import audit_nexium_pcm_plus_fence as s305
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
from test_audit_nexium_pcm_exit_controls import ExitControlSynthetic, control_csv


class PlusBufferedFenceSynthetic(unittest.TestCase):
    def setUp(self):
        self.fixture = ExitControlSynthetic(
            methodName="test_real_host_control_order_and_exact_terminal_overlap")
        self.fixture.setUp()

    def run_audit(self, before=123000, after=126000, end=128000,
                  *, override_stage304=None, override_pcm=None):
        f = self.fixture
        controls = control_csv(byte_sizes=(before, after, end))
        original304 = s304.audit_controls(
            f.raw, f.report300, f.report301, f.report302,
            f.report303, f.stop, controls, rate=f.fixture.rate)
        return s305.audit_plus_fence(
            f.raw if override_pcm is None else override_pcm,
            f.report300, f.report301, f.report302, f.report303,
            original304 if override_stage304 is None else override_stage304,
            f.stop, controls, rate=f.fixture.rate)

    def test_terminal_onset_inside_plus_fence_with_source_baselines(self):
        r = self.run_audit()
        onset = r["terminal_exact_zero_onset"]
        self.assertEqual(onset["start_frame"], 31000)
        self.assertEqual(onset["position_relative_to_buffered_snapshots"],
                         "between_buffered_plus_snapshots")
        self.assertEqual(onset["frames_after_press_snapshot_min"], 250)
        self.assertEqual(onset["frames_before_release_snapshot_min"], 500)
        bracket = r["plus_snapshot_control_window"]
        self.assertEqual(bracket["frames"], 750)
        self.assertEqual(bracket["exact_zero_stereo_frames"], 500)
        self.assertEqual(bracket["nonzero_stereo_frames"], 250)
        self.assertEqual(r["before_plus_500ms_baseline"]["exact_zero_stereo_frames"], 0)
        self.assertEqual(r["after_plus_500ms_window"]["exact_zero_stereo_frames"], 500)
        self.assertEqual(r["plus_hold_host_ms_between_snapshots"], 1000)
        self.assertEqual(r["sample_rate_hz"], 1000)

    def test_partial_frame_size_snapshots_produce_conservative_fence(self):
        r = self.run_audit(before=123001, after=126001)
        onset = r["terminal_exact_zero_onset"]
        self.assertEqual(onset["position_relative_to_buffered_snapshots"],
                         "between_buffered_plus_snapshots")
        self.assertEqual(onset["frames_after_press_snapshot_min"], 249)
        self.assertEqual(onset["frames_after_press_snapshot_max"], 250)
        self.assertEqual(onset["frames_before_release_snapshot_min"], 500)
        self.assertEqual(onset["frames_before_release_snapshot_max"], 501)
        self.assertEqual(r["plus_snapshot_control_window"]["frames"], 749)

    def test_onset_already_at_press_snapshot_is_not_inside_fence(self):
        r = self.run_audit(before=124000, after=126000)
        self.assertEqual(
            r["terminal_exact_zero_onset"]["position_relative_to_buffered_snapshots"],
            "present_by_before_plus_snapshot")

    def test_onset_later_than_release_snapshot_is_not_inside_fence(self):
        r = self.run_audit(before=120000, after=123500)
        self.assertEqual(
            r["terminal_exact_zero_onset"]["position_relative_to_buffered_snapshots"],
            "later_than_after_plus_snapshot")

    def test_partial_frame_touching_onset_is_ambiguous(self):
        r = self.run_audit(before=123999, after=126000)
        self.assertEqual(
            r["terminal_exact_zero_onset"]["position_relative_to_buffered_snapshots"],
            "ambiguous_partial_stereo_frame_boundary")

    def test_no_terminal_zero_run_still_preserves_raw_frame_windows(self):
        f = self.fixture
        raw = f.fixture.raw
        old300 = f.fixture.classify()
        old301 = s301.audit_envelopes(raw, old300, rate=f.fixture.rate)
        old302 = s302.classify_recording_edges(
            raw, old300, old301, rate=f.fixture.rate)
        old303 = s303.audit_recorder_stop(
            raw, old300, old301, old302, f.stop, rate=f.fixture.rate)
        events = control_csv(byte_sizes=(123000, 126000, 128000))
        old304 = s304.audit_controls(
            raw, old300, old301, old302, old303, f.stop,
            events, rate=f.fixture.rate)
        report = s305.audit_plus_fence(
            raw, old300, old301, old302, old303, old304,
            f.stop, events, rate=f.fixture.rate)
        self.assertIsNone(report["terminal_exact_zero_onset"])
        self.assertEqual(report["after_plus_500ms_window"]["exact_zero_stereo_frames"], 0)
        self.assertFalse(report["physical_Nintendo_Switch_audio_tested"])

    def test_changed_stage304_receipt_rejected(self):
        f = self.fixture
        source_csv = control_csv(byte_sizes=(123000,126000,128000))
        correct304 = s304.audit_controls(
            f.raw, f.report300, f.report301, f.report302,
            f.report303, f.stop, source_csv, rate=f.fixture.rate)
        fake304 = copy.deepcopy(correct304)
        fake304["exit_control_snapshots"][0]["pcm_bytes"] += 4
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(override_stage304=fake304)

    def test_altered_pcm_rejected_even_if_last_frame_nonzero(self):
        raw = self.fixture.raw[:-4] + struct.pack("<hh", 9, 9)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(override_pcm=raw)

    def test_reproducible_no_guest_causality_or_hardware_overclaim(self):
        a = self.run_audit()
        self.assertEqual(a, self.run_audit())
        self.assertIs(a["all_original_stage299_through_stage304_evidence_replayed"], True)
        self.assertIs(a["temporal_overlap_is_not_plus_audio_causality"], True)
        self.assertIs(a["file_size_and_wall_time_snapshots_are_not_guest_input_timestamps"], True)
        self.assertIs(a["original_soundtrack_or_audible_dropout_verified"], False)


if __name__ == "__main__":
    unittest.main()
