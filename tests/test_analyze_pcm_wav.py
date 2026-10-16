#!/usr/bin/env python3
"""Regression tests for host-side PCM WAV diagnostics."""
import importlib.util
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "analyze_pcm_wav.py"
SPEC = importlib.util.spec_from_file_location("analyze_pcm_wav", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_wav(path, channels, sample_rate, samples):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(struct.pack("<" + "h" * len(samples), *samples))


class PcmWavAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audio.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def test_zero_pcm_is_silent(self):
        write_wav(self.path, 1, 48000, [0] * 480)
        metrics = MODULE.analyze(self.path)
        self.assertEqual(metrics["duration_seconds"], 0.01)
        channel = metrics["per_channel"][0]
        self.assertTrue(channel["silent"])
        self.assertIsNone(channel["rms_dbfs"])
        self.assertEqual(channel["clipped_samples"], 0)

    def test_full_scale_clipping_is_counted(self):
        write_wav(self.path, 1, 48000, [32767, -32768] * 10)
        channel = MODULE.analyze(self.path)["per_channel"][0]
        self.assertEqual(channel["clipped_samples"], 20)
        self.assertEqual(channel["clipped_fraction"], 1)

    def test_stereo_channels_are_separate(self):
        data = [1000, -2000] * 100
        write_wav(self.path, 2, 48000, data)
        result = MODULE.analyze(self.path)
        self.assertEqual(result["frames"], 100)
        self.assertEqual(result["channels"], 2)
        self.assertAlmostEqual(result["per_channel"][0]["dc_offset"], 1000 / 32768, places=6)
        self.assertAlmostEqual(result["per_channel"][1]["dc_offset"], -2000 / 32768, places=6)

    def test_unexpected_rate_is_reported(self):
        write_wav(self.path, 1, 44100, [100] * 100)
        self.assertEqual(MODULE.analyze(self.path)["sample_rate_hz"], 44100)

    def test_empty_file_is_rejected(self):
        write_wav(self.path, 1, 48000, [])
        with self.assertRaisesRegex(ValueError, "Empty WAV"):
            MODULE.analyze(self.path)

    def test_8_bit_wav_rejected(self):
        with wave.open(str(self.path), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(1)
            f.setframerate(48000)
            f.writeframes(b"\x80" * 32)
        with self.assertRaisesRegex(ValueError, "16-bit"):
            MODULE.analyze(self.path)


if __name__ == "__main__":
    unittest.main()
