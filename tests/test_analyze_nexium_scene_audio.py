#!/usr/bin/env python3
"""Synthetic five-scene NeXium event analysis regressions."""
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

class TestSceneAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = Path(self.tmp.name) / "scene.pcm"
        self.events = Path(self.tmp.name) / "scene.csv"
        patch = mock.patch.object(scene, "RATE", 1000)
        patch.start()
        self.addCleanup(patch.stop)

    def generate(self, frequencies=(61, 106, 61, 106, 61), labels=scene.EXPECTED):
        signal = bytearray()
        markers = []
        for index, freq in enumerate(frequencies):
            markers.append((labels[index], len(signal), 1000 * (index * 10 + 1)))
            for i in range(6200):
                v = round(1100 * math.sin(2 * math.pi * freq * i / 1000))
                signal.extend(struct.pack("<hh", v, round(0.85 * v)))
        self.audio.write_bytes(signal)
        with self.events.open("w", newline="", encoding="ascii") as stream:
            wr = csv.writer(stream)
            wr.writerow(("scene", "pcm_bytes", "epoch_ms"))
            wr.writerows(markers)
        return markers

    def test_repeated_focus_separates_from_field(self):
        self.generate()
        result = scene.analyze(self.audio, self.events)
        self.assertEqual(result["result"], "REPEATED_SCENE_CORRELATED_PCM_CHANGE")
        self.assertGreater(result["focus_to_field_zero_crossing_ratio"], 1.3)
        self.assertTrue(result["consistent_frequency_class_separation"])
        self.assertFalse(result["scene_change_proven_causal"])

    def test_identical_scenes_are_not_proven(self):
        self.generate(frequencies=(61,) * 5)
        result = scene.analyze(self.audio, self.events)
        self.assertEqual(result["result"], "SCENE_PCM_CHANGE_NOT_ESTABLISHED")

    def test_wrong_scene_sequence_rejected(self):
        self.generate(labels=("field_initial", "focus_1", "field_1", "field_2", "focus_2"))
        with self.assertRaises(scene.SceneEvidenceError):
            scene.analyze(self.audio, self.events)

    def test_bad_marker_alignment_rejected(self):
        markers = self.generate()
        markers[1] = (markers[1][0], markers[1][1] + 1, markers[1][2])
        with self.events.open("w", newline="", encoding="ascii") as stream:
            writer = csv.writer(stream)
            writer.writerow(("scene", "pcm_bytes", "epoch_ms"))
            writer.writerows(markers)
        with self.assertRaises(scene.SceneEvidenceError):
            scene.analyze(self.audio, self.events)

    def test_symlink_and_short_audio_rejected(self):
        self.generate()
        link = self.audio.with_name("link.pcm")
        link.symlink_to(self.audio)
        with self.assertRaises(scene.SceneEvidenceError):
            scene.analyze(link, self.events)
        self.audio.write_bytes(bytes(100))
        with self.assertRaises(scene.SceneEvidenceError):
            scene.analyze(self.audio, self.events)

if __name__ == "__main__":
    unittest.main()
