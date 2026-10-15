"""Synthetic tests for read-only stereo WAV signal diagnostics."""
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.analyze_cdxa_wav_quality import analyze_wav


class XaSignalDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def wav(self, name, frames, rate=37800):
        path = self.root / name
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b"".join(int(value).to_bytes(2, "little", signed=True)
                                     for frame in frames for value in frame))
        return path

    def test_silence(self):
        result = analyze_wav(self.wav("silent.wav", [(0, 0)] * 32))
        self.assertEqual(result["frames"], 32)
        self.assertEqual(result["rms_amplitude"], [0, 0])
        self.assertEqual(result["peak_abs_sample"], [0, 0])
        self.assertEqual(result["zero_sample_fraction"], [1, 1])
        self.assertEqual(result["silent_stereo_frame_fraction"], 1)
        self.assertEqual(result["full_scale_sample_count"], [0, 0])

    def test_peaks_rms_and_full_scale(self):
        result = analyze_wav(self.wav("signal.wav", [
            (0, 0), (32767, -32768), (-32768, 32767), (100, -100),
        ]))
        self.assertEqual(result["peak_abs_sample"], [32768, 32768])
        self.assertEqual(result["full_scale_sample_count"], [2, 2])
        self.assertEqual(result["zero_sample_fraction"], [0.25, 0.25])
        self.assertEqual(result["silent_stereo_frame_fraction"], 0.25)
        expected = math.sqrt((32767 ** 2 + 32768 ** 2 + 100 ** 2) / 4)
        self.assertAlmostEqual(result["rms_amplitude"][0], expected)
        self.assertAlmostEqual(result["rms_amplitude"][1], expected)

    def test_chunk_boundary(self):
        result = analyze_wav(self.wav("long.wav", [(0, 0)] * 4096 + [(5, -6)]))
        self.assertEqual(result["frames"], 4097)
        self.assertEqual(result["peak_abs_sample"], [5, 6])
        self.assertEqual(result["silent_stereo_frame_fraction"], 4096 / 4097)

    def test_invalid_rate_and_empty_audio(self):
        with self.assertRaisesRegex(ValueError, "37800"):
            analyze_wav(self.wav("wrong-rate.wav", [(1, 1)], rate=44100))
        with self.assertRaisesRegex(ValueError, "no PCM frames"):
            analyze_wav(self.wav("empty.wav", []))

    def test_rejects_truncated_pcm(self):
        path = self.wav("truncated.wav", [(1, 2)] * 2)
        with path.open("r+b") as stream:
            stream.truncate(path.stat().st_size - 1)
        with self.assertRaisesRegex(ValueError, "truncated PCM"):
            analyze_wav(path)


if __name__ == "__main__":
    unittest.main()
