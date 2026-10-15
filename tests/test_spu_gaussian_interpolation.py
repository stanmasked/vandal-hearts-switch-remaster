"""Synthetic exact integer PS1 SPU Gaussian coefficients/history regressions."""
import io
import struct
import sys
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.interpolate_spu_gaussian import gaussian_voice_sample
from tools.render_vab_note import render_pcm_note, wav_from_mono
from tools.simulate_spu_voice import SpuSampleCursor
from tools.spu_gaussian_table import GAUSS

SAMPLES = (4000, 8000, 12000, 16000, 20000, 24000, 28000)


class GaussianTests(unittest.TestCase):
    def test_reference_coefficient_table(self):
        self.assertEqual(len(GAUSS), 512)
        self.assertEqual(GAUSS[:16], (-1,) * 16)
        self.assertEqual(GAUSS[255], 4807)
        self.assertEqual(GAUSS[256], 4871)
        self.assertEqual(GAUSS[-1], 22963)
        self.assertTrue(all(-32768 <= coefficient <= 32767 for coefficient in GAUSS))

    def test_exact_per_tap_arithmetic_and_fractional_phases(self):
        cursor = SpuSampleCursor(7, 2, 5, 0x1000)
        expected = (
            (0, -1), (1, 593), (3, 7974)
        )
        for index, pcm in expected:
            with self.subTest(index=index):
                cursor.phase = index << 12
                self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), pcm)
        cursor.phase = (3 << 12) | 0x800
        self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), 9967)
        cursor.phase = (3 << 12) | 0x80F  # low four bits do not affect gi
        self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), 9967)

    def test_loop_history_changes_at_first_wrap(self):
        cursor = SpuSampleCursor(7, 2, 5, 0x1000)
        cursor.advance()
        cursor.advance()
        self.assertEqual((cursor.index, cursor.looped), (2, False))
        self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), 3991)
        cursor.advance()
        cursor.advance()
        cursor.advance()
        self.assertEqual((cursor.index, cursor.looped), (2, True))
        self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), 15944)
        cursor.phase = (2 << 12) | 0x800
        self.assertEqual(gaussian_voice_sample(SAMPLES, cursor), 17779)

    def test_render_uses_gaussian_by_default_and_nearest_is_optional(self):
        pcm = struct.pack("<7h", *SAMPLES)
        params = dict(
            adsr1=0x000F, adsr2=0, pitch_step=0x1000,
            loop_start=2, loop_end=5, hold_frames=7, tail_frames=0
        )
        gaussian_pcm, gaussian_report = render_pcm_note(pcm, **params)
        nearest_pcm, nearest_report = render_pcm_note(
            pcm, **params, interpolation="nearest"
        )
        self.assertEqual(gaussian_report["interpolation"], "gaussian")
        self.assertEqual(nearest_report["interpolation"], "nearest")
        self.assertNotEqual(gaussian_pcm, nearest_pcm)
        self.assertTrue(gaussian_report["looped"])
        self.assertEqual(len(gaussian_pcm), 14)
        with wave.open(io.BytesIO(wav_from_mono(gaussian_pcm)), "rb") as audio:
            self.assertEqual((audio.getframerate(), audio.getnframes()),
                             (44100, 7))
            self.assertEqual(audio.readframes(7), gaussian_pcm)

    def test_rejects_unrecognized_interpolation(self):
        with self.assertRaisesRegex(ValueError, "interpolation must be"):
            render_pcm_note(
                struct.pack("<h", 1000), adsr1=0, adsr2=0,
                pitch_step=0x1000, loop_start=None, loop_end=None,
                hold_frames=1, tail_frames=0, interpolation="linear"
            )


if __name__ == "__main__":
    unittest.main()
