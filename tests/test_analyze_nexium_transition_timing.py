#!/usr/bin/env python3
"""Host-only tests for buffered marker timing and safety boundaries."""
import csv
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import analyze_nexium_scene_audio as scene
import analyze_nexium_transition_timing as timing


class TestTransitionTiming(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = Path(self.tmp.name) / "scene.pcm"
        self.events = Path(self.tmp.name) / "scene.csv"
        for module in (scene, timing):
            patch = mock.patch.object(module, "RATE", 1000)
            patch.start()
            self.addCleanup(patch.stop)

    def generate(self, frequencies=(61, 106, 61, 106, 61), silence=None):
        samples = bytearray()
        events = []
        for idx, (label, hz) in enumerate(zip(scene.EXPECTED, frequencies)):
            events.append((label, len(samples), idx * 7000 + 1000))
            for n in range(6200):
                if silence and idx == silence[0] and n < silence[1]:
                    value = 0
                else:
                    value = int(1100 * math.sin(2 * math.pi * hz * n / 1000))
                samples.extend(struct.pack("<hh", value, round(value * .85)))
        self.audio.write_bytes(samples)
        with self.events.open("w", newline="", encoding="ascii") as stream:
            writer = csv.writer(stream)
            writer.writerow(("scene", "pcm_bytes", "epoch_ms"))
            writer.writerows(events)
        return events

    def test_controlled_alternating_scenes_confirm_after_marker(self):
        self.generate()
        report = timing.analyze(self.audio, self.events)
        self.assertEqual(report["scene_evidence"], "REPEATED_SCENE_CORRELATED_PCM_CHANGE")
        self.assertEqual(report["timing_result"], "HOST_RELATIVE_DETECTION_ONLY")
        self.assertEqual(len(report["transitions"]), 4)
        self.assertTrue(all(x["stable_expected_scene_detected"] for x in report["transitions"]))
        self.assertIsNone(report["actual_input_to_audio_latency_ms"])
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")

    def test_equal_scenes_abstain_instead_of_faking_latency(self):
        self.generate((61,) * 5)
        report = timing.analyze(self.audio, self.events)
        self.assertEqual(report["timing_result"], "INSUFFICIENT_SCENE_SEPARATION")
        self.assertTrue(all(not x["stable_expected_scene_detected"] for x in report["transitions"]))

    def test_inserted_silence_is_observation_not_underrun(self):
        self.generate(silence=(1, 200))
        report = timing.analyze(self.audio, self.events)
        focus = report["transitions"][0]
        self.assertGreaterEqual(focus["longest_contiguous_low_rms_ms"], 190)
        self.assertTrue(focus["low_rms_not_equivalent_to_underrun"])
        self.assertTrue(focus["audio_underruns_not_proven_or_excluded"])

    def test_bad_marker_and_misalignment_rejected(self):
        events = self.generate()
        events[2] = (events[2][0], events[2][1] + 1, events[2][2])
        with self.events.open("w", newline="", encoding="ascii") as stream:
            writer = csv.writer(stream)
            writer.writerow(("scene", "pcm_bytes", "epoch_ms"))
            writer.writerows(events)
        with self.assertRaises(scene.SceneEvidenceError):
            timing.analyze(self.audio, self.events)

    def test_no_hardware_or_pitch_claims_even_with_clean_signal(self):
        self.generate()
        report = timing.analyze(self.audio, self.events)
        self.assertFalse(report["music_pitch_accuracy_proven"])
        self.assertFalse(report["physical_switch_tested"])
        self.assertTrue(all(x["observed_full_scale_clipped_sample_values"] == 0
                            for x in report["transitions"]))


if __name__ == "__main__":
    unittest.main()
