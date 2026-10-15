"""Synthetic SPU ADSR/position timing tests (no game sound data)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.simulate_spu_voice import (
    RATE, SpuEnvelope, SpuSampleCursor, _trunc_zero,
)


class EnvelopeTests(unittest.TestCase):
    def test_rate_and_word_validation(self):
        self.assertEqual(RATE, 44100)
        self.assertEqual(_trunc_zero(-9, 4), -2)
        self.assertEqual(_trunc_zero(-1, 4), 0)
        self.assertEqual(_trunc_zero(9, 4), 2)
        for a, b in ((-1, 0), (65536, 0), (0, 65536),
                     (0, -1), (True, 0), (0, False)):
            with self.subTest(a=a, b=b):
                with self.assertRaises(ValueError):
                    SpuEnvelope(a, b)

    def test_adsr_field_decoding(self):
        # AR = 126 -> shift 31, step 2; DR=10; SL=15.
        # SR=93 -> shift 23, step 1; release shift=18.
        env = SpuEnvelope(0xFEAF, 0xC000 | (93 << 6) | 0x32)
        self.assertEqual((env.ar_shift, env.ar_step), (31, 2))
        self.assertTrue(env.attack_exp)
        self.assertEqual(env.dr_shift, 10)
        self.assertEqual(env.sl_target, 0x7fff)
        self.assertEqual((env.sr_shift, env.sr_step), (23, 1))
        self.assertTrue(env.sustain_exp)
        self.assertTrue(env.sustain_decrease)
        self.assertEqual(env.rr_shift, 18)
        self.assertTrue(env.release_exp)

    def test_fast_attack_decay_sustain_release(self):
        env = SpuEnvelope(0, 0)
        self.assertEqual((env.level, env.phase, env.counter), (0, "attack", 0))
        self.assertTrue(env.advance())
        self.assertEqual((env.level, env.phase), (14336, "attack"))
        env.advance()
        self.assertEqual((env.level, env.phase), (28672, "attack"))
        env.advance()
        self.assertEqual((env.level, env.phase), (32767, "decay"))
        env.advance()
        self.assertEqual((env.level, env.phase), (16384, "decay"))
        env.advance()
        self.assertEqual((env.level, env.phase), (8192, "decay"))
        env.advance()
        env.advance()
        self.assertEqual((env.level, env.phase), (2048, "sustain"))
        env.key_off()
        self.assertEqual(env.phase, "release")
        self.assertFalse(env.advance())
        self.assertEqual((env.level, env.phase), (0, "off"))
        self.assertFalse(env.advance())

    def test_slow_attack_counter_and_rate_all_ones(self):
        # Attack rate 0x7e = shift31, step2 -> increment=1 per
        # output sample, a single envelope step after 32768 ticks.
        slow = SpuEnvelope(0x7E00, 0)
        for _ in range(32767):
            self.assertTrue(slow.advance())
        self.assertEqual((slow.level, slow.counter), (0, 32767))
        slow.advance()
        self.assertEqual((slow.level, slow.counter), (5, 0))
        frozen = SpuEnvelope(0x7F00, 0)
        for _ in range(100):
            self.assertTrue(frozen.advance())
        self.assertEqual((frozen.level, frozen.phase), (0, "attack"))

    def test_sustain_decrease_can_finish_voice(self):
        env = SpuEnvelope(0, 0x4000)
        for _ in range(20):
            if env.phase == "sustain":
                break
            env.advance()
        self.assertEqual(env.phase, "sustain")
        self.assertFalse(env.advance())
        self.assertEqual((env.level, env.phase), (0, "off"))

    def test_exponential_release_always_ends_at_zero(self):
        env = SpuEnvelope(0, 0x20)
        for _ in range(3):
            env.advance()
        self.assertEqual(env.level, 32767)
        env.key_off()
        for _ in range(200):
            if not env.advance():
                break
        self.assertEqual((env.level, env.phase), (0, "off"))


class CursorTests(unittest.TestCase):
    def test_unity_one_shot(self):
        cursor = SpuSampleCursor(3, -1, -1, 0x1000)
        self.assertEqual([cursor.index, cursor.fraction], [0, 0])
        self.assertTrue(cursor.advance())
        self.assertEqual(cursor.index, 1)
        self.assertTrue(cursor.advance())
        self.assertEqual(cursor.index, 2)
        self.assertFalse(cursor.advance())
        self.assertEqual(cursor.index, 3)
        self.assertFalse(cursor.active)

    def test_loop_point_wrap_and_fast_pitch(self):
        cursor = SpuSampleCursor(6, 2, 4, 0x1000)
        visited = []
        for _ in range(7):
            visited.append(cursor.index)
            self.assertTrue(cursor.advance())
        self.assertEqual(visited, [0, 1, 2, 3, 2, 3, 2])
        self.assertTrue(cursor.looped)
        fast = SpuSampleCursor(6, 1, 3, 0x4000)
        self.assertTrue(fast.advance())
        self.assertEqual(fast.index, 2)
        self.assertTrue(fast.looped)

    def test_fraction_and_clamped_pitch(self):
        half = SpuSampleCursor(4, -1, -1, 0x800)
        self.assertEqual((half.index, half.fraction), (0, 0))
        half.advance()
        self.assertEqual((half.index, half.fraction), (0, 2048))
        half.advance()
        self.assertEqual((half.index, half.fraction), (1, 0))
        self.assertEqual(SpuSampleCursor(4, -1, -1, 0).pitch_step, 1)
        self.assertEqual(SpuSampleCursor(4, -1, -1, 999999).pitch_step, 0x4000)

    def test_invalid_bounds(self):
        for length, lo, hi, step in (
            (0, -1, -1, 4096), (4, 2, 5, 4096), (4, -1, 2, 4096),
            (4, 3, 8, 4096), (True, -1, -1, 4096),
            (4, -1, -1, 4096.0)
        ):
            with self.subTest(length=length, lo=lo, hi=hi, step=step):
                with self.assertRaises(ValueError):
                    SpuSampleCursor(length, lo, hi, step)


if __name__ == "__main__":
    unittest.main()
