"""Stage304 synthetic Plus exit control snapshots; only host-buffered evidence."""
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
import audit_nexium_pcm_exit_controls as s304
from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError
from test_analyze_nexium_pcm_scene_silence import SceneSilenceSynthetic


def control_csv(byte_sizes=(124000,126000,128000),
                epochs=(141000,142000,143000)):
    return ("event,pcm_bytes,host_epoch_ms\n" + "".join(
        f"{name},{size},{epoch}\n"
        for name, size, epoch in zip(s304.EVENT_NAMES, byte_sizes, epochs)
    )).encode("ascii")


class ExitControlSynthetic(unittest.TestCase):
    def setUp(self):
        fixture = SceneSilenceSynthetic(
            methodName="test_reproducibility_and_never_claim_dropouts")
        fixture.setUp()
        self.fixture = fixture
        self.raw = fixture.raw[:-4000] + b"\0" * 4000
        report299 = copy.deepcopy(fixture.stage299)
        scene = copy.deepcopy(fixture.scene_report)
        runs = s301.source_runs(self.raw)
        digest = hashlib.sha256(self.raw).hexdigest()
        cap = report299["scene_capture"]
        cap["pcm_sha256"] = digest
        cap["exact_zero_stereo_frames"] = sum(b - a for a, b in runs)
        cap["exact_zero_stereo_runs"] = len(runs)
        cap["longest_exact_zero_stereo_run_frames"] = max(
            (b - a for a, b in runs), default=0)
        scene["pcm_sha256"] = digest
        self.report300 = s300.classify_silence(
            self.raw, report299, scene, rate=fixture.rate)
        self.report301 = s301.audit_envelopes(
            self.raw, self.report300, rate=fixture.rate)
        self.report302 = s302.classify_recording_edges(
            self.raw, self.report300, self.report301, rate=fixture.rate)
        self.stop = s303_stop = (
            "event,pcm_bytes,host_epoch_ms,signal_success\n"
            f"before_sigint,{len(self.raw)},150000,1\n"
            f"after_wait,{len(self.raw)},150050,1\n"
        ).encode("ascii")
        self.report303 = s303.audit_recorder_stop(
            self.raw, self.report300, self.report301, self.report302,
            s303_stop, rate=fixture.rate)

    def run_audit(self, events=None, *, pcm=None, p300=None, p301=None,
                  p302=None, p303=None, stop=None):
        return s304.audit_controls(
            self.raw if pcm is None else pcm,
            self.report300 if p300 is None else p300,
            self.report301 if p301 is None else p301,
            self.report302 if p302 is None else p302,
            self.report303 if p303 is None else p303,
            self.stop if stop is None else stop,
            control_csv() if events is None else events,
            rate=self.fixture.rate)

    def test_real_host_control_order_and_exact_terminal_overlap(self):
        r = self.run_audit()
        self.assertEqual([x["event"] for x in r["exit_control_snapshots"]],
                         list(s304.EVENT_NAMES))
        self.assertEqual([x["terminal_zero_frames_observed_by_snapshot_min"]
                          for x in r["exit_control_snapshots"]], [0,500,1000])
        self.assertEqual([x["terminal_zero_frames_observed_by_snapshot_max"]
                          for x in r["exit_control_snapshots"]], [0,500,1000])
        self.assertEqual(r["first_plus_control_vs_scene_marker_host_ms"], 1000)
        self.assertEqual(r["last_control_vs_recorder_stop_host_ms"], 7000)
        self.assertIs(r["audio_dropout_or_original_soundtrack_verified"], False)

    def test_snapshot_partial_frame_is_bounded_not_assumed_exact(self):
        r = self.run_audit(control_csv(byte_sizes=(124001,126001,127999)))
        snapshots = r["exit_control_snapshots"]
        self.assertEqual([x["terminal_zero_frames_observed_by_snapshot_min"]
                          for x in snapshots], [0,500,999])
        self.assertEqual([x["terminal_zero_frames_observed_by_snapshot_max"]
                          for x in snapshots], [1,501,1000])
        self.assertTrue(all(x["partial_stereo_frame_snapshot"] for x in snapshots))

    def test_early_or_late_controls_rejected(self):
        invalid = [
            control_csv(epochs=(139999,142000,143000)),
            control_csv(epochs=(141000,142000,150001)),
            control_csv(byte_sizes=(99999,126000,128000)),
            control_csv(byte_sizes=(124000,126000,128001)),
            control_csv(byte_sizes=(124000,123999,128000)),
            control_csv(epochs=(141000,141000,143000)),
            control_csv(epochs=(141000,143000,142000)),
        ]
        for i, csv in enumerate(invalid):
            with self.subTest(case=i), self.assertRaises(VirtualPcmEvidenceError):
                self.run_audit(csv)

    def test_bad_csv_rejected(self):
        valid=control_csv()
        invalid = [
            valid[:-1],
            valid.replace(b"\n", b"\r\n"),
            valid.replace(b"before_plus_down", b"after_plus_up", 1),
            valid.replace(b"124000", b"0124000", 1),
            valid.replace(b"124000", b"bad", 1),
            valid + b"extra,128000,144000\n",
            valid.replace(b"event,pcm_bytes", b"name,pcm_bytes", 1),
        ]
        for i,csv in enumerate(invalid):
            with self.subTest(case=i), self.assertRaises(VirtualPcmEvidenceError):
                self.run_audit(csv)

    def test_stage303_snapshot_mismatch_rejected(self):
        bad = copy.deepcopy(self.report303)
        bad["buffered_bytes_appended_during_stop"] += 1
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(p303=bad)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(stop=self.stop.replace(b"150000", b"150001"))

    def test_source_pcm_mismatch_rejected(self):
        raw = self.raw[:-4] + struct.pack("<hh", 9, 9)
        with self.assertRaises(VirtualPcmEvidenceError):
            self.run_audit(pcm=raw)

    def test_no_terminal_zeros_keeps_scope(self):
        raw = self.fixture.raw
        doc299 = self.fixture.stage299
        scene = self.fixture.scene_report
        a = s300.classify_silence(raw, doc299, scene, rate=self.fixture.rate)
        b = s301.audit_envelopes(raw, a, rate=self.fixture.rate)
        c = s302.classify_recording_edges(raw, a, b, rate=self.fixture.rate)
        d = s303.audit_recorder_stop(raw, a, b, c, self.stop,
                                     rate=self.fixture.rate)
        r = s304.audit_controls(raw, a, b, c, d, self.stop, control_csv(),
                                rate=self.fixture.rate)
        self.assertIsNone(r["original_terminal_zero_run"])
        self.assertTrue(all(
            "terminal_zero_frames_observed_by_snapshot_min" not in x
            for x in r["exit_control_snapshots"]))
        self.assertFalse(r["plus_input_to_guest_music_stop_causality_proven"])

    def test_determinism(self):
        self.assertEqual(self.run_audit(), self.run_audit())


if __name__ == "__main__":
    unittest.main()
