"""Synthetic tests for decoded-versus-reference WAV comparison."""
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.compare_cdxa_wavs import compare_wavs


class CompareXaWavsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_wav(self, name, samples, rate=37800):
        path = self.root / name
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b"".join(
                int(value).to_bytes(2, "little", signed=True)
                for frame in samples for value in frame
            ))
        return path

    def test_identical_samples_are_exact(self):
        a = self.make_wav("a.wav", [(1, -1), (2, -2)])
        b = self.make_wav("b.wav", [(1, -1), (2, -2)])
        result = compare_wavs(a, b)
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["different_frames"], 0)

    def test_reports_first_difference_and_two_channel_metrics(self):
        a = self.make_wav("a.wav", [(1, -1), (2, -2), (3, -3)])
        b = self.make_wav("b.wav", [(1, -1), (7, -2), (3, -5)])
        result = compare_wavs(a, b)
        self.assertFalse(result["exact_match"])
        self.assertEqual(result["first_different_frame"], 1)
        self.assertEqual(result["different_frames"], 2)
        self.assertEqual(result["different_channel_samples"], 2)
        self.assertEqual(result["max_absolute_sample_difference"], 5)
        self.assertAlmostEqual(result["mean_absolute_sample_difference"], 7 / 6)

    def test_compares_across_read_chunks(self):
        samples = [(0, 0)] * 8193
        altered = list(samples)
        altered[8192] = (-32768, 32767)
        a = self.make_wav("a.wav", samples)
        b = self.make_wav("b.wav", altered)
        result = compare_wavs(a, b)
        self.assertEqual(result["first_different_frame"], 8192)
        self.assertEqual(result["different_frames"], 1)
        self.assertEqual(result["max_absolute_sample_difference"], 32768)

    def test_rejects_incompatible_rate_and_frame_count(self):
        a = self.make_wav("a.wav", [(1, 1)])
        wrong_rate = self.make_wav("wrong.wav", [(1, 1)], rate=44100)
        wrong_count = self.make_wav("short.wav", [(1, 1), (1, 1)])
        with self.assertRaisesRegex(ValueError, "37800"):
            compare_wavs(a, wrong_rate)
        with self.assertRaisesRegex(ValueError, "frame count mismatch"):
            compare_wavs(a, wrong_count)

    def test_rejects_truncated_pcm(self):
        a = self.make_wav("a.wav", [(1, 1), (2, 2)])
        b = self.make_wav("b.wav", [(1, 1), (2, 2)])
        with b.open("r+b") as stream:
            stream.truncate(b.stat().st_size - 2)
        with self.assertRaisesRegex(ValueError, "truncated PCM"):
            compare_wavs(a, b)


if __name__ == "__main__":
    unittest.main()
