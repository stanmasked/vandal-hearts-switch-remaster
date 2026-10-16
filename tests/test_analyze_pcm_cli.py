#!/usr/bin/env python3
"""End-to-end CLI checks for PCM diagnostics using generated audio only."""
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "analyze_pcm_wav.py"


class PcmCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "synthetic.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, samples, rate=48000):
        with wave.open(str(self.path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    def run_tool(self, *args):
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(self.path), "--fail-on-silence", *args],
            capture_output=True, text=True, check=False, timeout=15
        )
        return proc.returncode, json.loads(proc.stdout)

    def test_healthy_440hz_tone_passes(self):
        self.write([round(8000 * math.sin(2 * math.pi * 440 * i / 48000))
                    for i in range(48000)])
        status, result = self.run_tool()
        self.assertEqual(status, 0)
        self.assertTrue(result["pass"])
        self.assertAlmostEqual(result["duration_seconds"], 1.0)
        self.assertFalse(result["per_channel"][0]["silent"])

    def test_silence_fails_closed(self):
        self.write([0] * 480)
        status, result = self.run_tool()
        self.assertEqual(status, 1)
        self.assertIn("channel 0: silent", result["violations"])

    def test_clipping_fails_closed(self):
        self.write([32767, -32768] * 240)
        status, result = self.run_tool()
        self.assertEqual(status, 1)
        self.assertTrue(any("clipping" in entry for entry in result["violations"]))

    def test_dc_fails_closed(self):
        self.write([10000] * 480)
        status, result = self.run_tool()
        self.assertEqual(status, 1)
        self.assertTrue(any("DC threshold" in entry for entry in result["violations"]))

    def test_mismatched_rate_fails_closed(self):
        self.write([1000, -1000] * 240, rate=44100)
        status, result = self.run_tool()
        self.assertEqual(status, 1)
        self.assertIn("unexpected sample rate", result["violations"])


if __name__ == "__main__":
    unittest.main()
