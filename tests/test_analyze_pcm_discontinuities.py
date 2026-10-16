"""Checks PCM discontinuity diagnostics on generated stereo WAV."""
import importlib.util
import struct
import tempfile
import unittest
import wave
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pcm_jumps", Path(__file__).resolve().parents[1] / "tools/analyze_pcm_discontinuities.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PcmJumpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fixture.wav"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, left, right):
        with wave.open(str(self.path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(48000)
            flat = [x for pair in zip(left, right) for x in pair]
            wav.writeframes(struct.pack("<" + "h" * len(flat), *flat))

    def test_flat_signal_has_no_jumps(self):
        self.write([100] * 1600, [-200] * 1600)
        result = module.analyze(self.path)
        self.assertEqual(result["max_adjacent_delta"], [0, 0])
        self.assertGreaterEqual(result["boundaries_inspected"], 2)

    def test_step_on_block_boundary_is_reported(self):
        center = round(512 * 48000 / 44100)
        left = [0] * 1600
        right = [0] * 1600
        left[center:] = [12000] * (1600 - center)
        result = None
        self.write(left, right)
        result = module.analyze(self.path)
        self.assertEqual(result["max_adjacent_delta"], [12000, 0])
        self.assertEqual(result["max_boundary_window_delta"], [12000, 0])
        self.assertEqual(result["max_delta_frame"][0], center)

    def test_too_short_wav_rejected(self):
        self.write([0], [0])
        with self.assertRaisesRegex(ValueError, "too short"):
            module.analyze(self.path)


if __name__ == "__main__":
    unittest.main()
