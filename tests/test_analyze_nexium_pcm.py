#!/usr/bin/env python3
"""Synthetic regression tests for audio measurements, never device acceptance."""
import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import analyze_nexium_pcm as pcm


class TestNexiumPcm(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "capture.pcm"

    def store(self, samples):
        self.path.write_bytes(b"".join(struct.pack("<hh", *v) for v in samples))

    def test_nonzero_stereo_and_dc(self):
        samples = [(int(1200 * math.sin(2 * math.pi * i / 96)),
                    int(1000 * math.sin(2 * math.pi * i / 96 + 0.5)))
                   for i in range(9600)]
        self.store(samples)
        report = pcm.analyze(self.path, expected_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(report["observation"], "NONZERO_MONITOR_PCM")
        self.assertEqual(report["window_count"], 2)
        self.assertEqual(report["longest_contiguous_low_rms_seconds"], 0)
        self.assertGreater(report["channel_difference_rms"], 100)
        self.assertTrue(-1 < report["channel_correlation"] < 1)
        self.assertEqual(report["full_scale_clipped_samples_by_channel"], [0, 0])
        self.assertFalse(report["audible_music_confirmed"])

    def test_silence_runs_and_partial_window(self):
        self.store([(0, 0)] * 9600 + [(500, -500)] * 100)
        report = pcm.analyze(self.path)
        self.assertEqual(report["window_count"], 3)
        self.assertEqual(report["low_rms_window_count"], 2)
        self.assertEqual(report["longest_contiguous_low_rms_seconds"], 0.2)

    def test_clipped_values_and_identical_channels(self):
        self.store([(32767, 32767), (-32768, -32768)])
        report = pcm.analyze(self.path)
        self.assertEqual(report["full_scale_clipped_samples_by_channel"], [2, 2])
        self.assertEqual(report["channel_difference_rms"], 0)
        self.assertEqual(report["channel_correlation"], 1)

    def test_malformed_and_wrong_hash_rejected(self):
        self.path.write_bytes(bytes(3))
        with self.assertRaises(pcm.PcmFormatError):
            pcm.analyze(self.path)
        self.path.write_bytes(bytes(4))
        with self.assertRaises(pcm.PcmFormatError):
            pcm.analyze(self.path, expected_sha256="a" * 64)
        self.path.write_bytes(b"")
        with self.assertRaises(pcm.PcmFormatError):
            pcm.analyze(self.path)

    def test_symlink_rejected(self):
        second = self.path.with_name("link.pcm")
        self.path.write_bytes(bytes(4))
        second.symlink_to(self.path)
        with self.assertRaises(pcm.PcmFormatError):
            pcm.analyze(second)


if __name__ == "__main__":
    unittest.main()
