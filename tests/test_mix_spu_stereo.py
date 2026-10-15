"""Independent synthetic stereo-volume, mix and local VH/VB chord regressions."""
import io
import json
import math
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.mix_spu_stereo import (
    StereoVoice, pan_factors, seq_voice_gains,
    render_stereo_voices, stereo_wav,
)
from tools.render_vab_chord import render_vab_chord


def full_gains(**overrides):
    fields = dict(
        velocity=127, channel_volume=127, bank_volume=127,
        program_volume=127, tone_volume=127,
        tone_pan=64, program_pan=64, channel_pan=64,
        trim=1.0,
    )
    fields.update(overrides)
    return seq_voice_gains(**fields)


def voice(source=10000, left=1.0, right=1.0, start=0, hold=5, tail=1):
    # Looping sample avoids accidental one-shot termination in mix tests.
    return StereoVoice(
        struct.pack("<8h", *([source] * 8)), 0x000F, 0,
        4096, 0, 8, start, hold, tail, left, right,
    )


def bank_fixture():
    header = bytearray(32)
    header[:4] = b"pBAV"
    struct.pack_into("<HHHH", header, 16, 0, 1, 2, 2)
    header[24] = 127
    programs = bytearray(128 * 16)
    programs[7 * 16] = 2
    programs[7 * 16 + 1] = 127
    programs[7 * 16 + 4] = 64
    tones = bytearray(16 * 32)
    for idx, (lo, hi, center, vag) in enumerate(
        ((40, 65, 60, 1), (66, 90, 72, 2))
    ):
        pos = idx * 32
        tones[pos + 2] = 127
        tones[pos + 3] = 64
        tones[pos + 4] = center
        tones[pos + 6] = lo
        tones[pos + 7] = hi
        struct.pack_into("<HHhh", tones, pos + 16, 15, 0, 7, vag)
    units = [0] * 256
    units[0:3] = [2, 4, 4]
    vh = bytes(header + programs + tones + struct.pack("<256H", *units))
    pos = bytes([12, 4] + [0x22] * 14) + bytes([12, 3] + [0x22] * 14)
    neg = bytes([12, 4] + [0xEE] * 14) + bytes([12, 3] + [0xEE] * 14)
    vb = bytes(16) + pos + neg + bytes(9)
    return vh, vb


class SeqGainTests(unittest.TestCase):
    def test_pan_extremes_and_asymmetric_center(self):
        self.assertEqual(pan_factors(0), (1.0, 0.0))
        self.assertEqual(pan_factors(64), (1.0, 1.0))
        self.assertEqual(pan_factors(127), (0.0, 1.0))
        self.assertEqual(pan_factors(32), (1.0, 32 / 63))
        self.assertEqual(pan_factors(96), (31 / 63, 1.0))
        self.assertEqual(full_gains(), (1.0, 1.0))
        self.assertEqual(full_gains(channel_pan=0), (1.0, 0.0))
        self.assertEqual(full_gains(channel_pan=127), (0.0, 1.0))
        l, r = full_gains(tone_pan=32, channel_pan=32)
        self.assertEqual((l, r), (1.0, (32 / 63) ** 4))
        self.assertEqual(full_gains(velocity=0), (0.0, 0.0))

    def test_integer_gain_stages_and_square_after_pan(self):
        values = dict(
            velocity=97, channel_volume=83, bank_volume=120,
            program_volume=89, tone_volume=77, tone_pan=96,
            program_pan=64, channel_pan=32, seq_left=96, seq_right=127,
            trim=1.0,
        )
        v = 97 * 83 // 127
        v = v * 120 // 127
        v = v * 89 // 127
        v = v * 77 // 127
        l = ((v * 96 // 127) / 127 * (31 / 63)) ** 2
        r = ((v * 127 // 127) / 127 * (32 / 63)) ** 2
        result = seq_voice_gains(**values)
        self.assertAlmostEqual(result[0], l)
        self.assertAlmostEqual(result[1], r)
        self.assertEqual(full_gains(trim=1.012), (1.012, 1.012))

    def test_invalid_volume_inputs(self):
        for invalid in (True, -1, 128, 64.0, "64"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    full_gains(tone_pan=invalid)
        for invalid in (-1, 2.1, float("nan"), True, "1"):
            with self.subTest(trim=invalid):
                with self.assertRaises(ValueError):
                    full_gains(trim=invalid)


class MixTests(unittest.TestCase):
    def test_two_hard_pan_voices_exact_output_and_release(self):
        data, info = render_stereo_voices(
            [voice(left=1, right=0), voice(source=-10000, left=0, right=1)],
            frames=6, interpolation="nearest",
        )
        expected = [
            (int(10000 * 14336 / 32767), -int(10000 * 14336 / 32767)),
            (int(10000 * 28672 / 32767), -int(10000 * 28672 / 32767)),
            (10000, -10000), (10000, -10000), (10000, -10000),
            (int(10000 * 16383 / 32767), -int(10000 * 16383 / 32767)),
        ]
        actual = list(struct.iter_unpack("<hh", data))
        self.assertEqual(actual, expected)
        self.assertEqual([x["active_frames"] for x in info], [6, 6])
        self.assertTrue(all(x["looped"] is False for x in info))
        with wave.open(io.BytesIO(stereo_wav(data)), "rb") as wav:
            self.assertEqual(
                (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                 wav.getnframes()), (2, 2, 44100, 6)
            )
            self.assertEqual(wav.readframes(6), data)

    def test_polyphonic_clipping_sums_before_truncating(self):
        left_only = [voice(source=30000, left=1.0, right=0.0, hold=4, tail=0)
                     for _ in range(4)]
        pcm, info = render_stereo_voices(
            left_only, frames=4, interpolation="nearest"
        )
        rows = list(struct.iter_unpack("<hh", pcm))
        self.assertEqual(rows[0], (32767, 0))  # 4x first attack already clips
        self.assertEqual(rows[-1], (32767, 0))
        self.assertEqual([x["active_frames"] for x in info], [4] * 4)

    def test_sequential_starts_and_silence_after_end(self):
        a = voice(left=1, right=0, start=0, hold=1, tail=0)
        b = voice(left=0, right=1, start=2, hold=1, tail=0)
        pcm, _ = render_stereo_voices([a, b], frames=4, interpolation="nearest")
        rows = list(struct.iter_unpack("<hh", pcm))
        self.assertNotEqual(rows[0][0], 0)
        self.assertEqual(rows[0][1], 0)
        self.assertEqual(rows[1], (0, 0))
        self.assertEqual(rows[2][0], 0)
        self.assertNotEqual(rows[2][1], 0)
        self.assertEqual(rows[3], (0, 0))

    def test_rejects_invalid_voice_count_timing_and_gain(self):
        with self.assertRaisesRegex(ValueError, "1..32"):
            render_stereo_voices([], frames=3)
        with self.assertRaisesRegex(ValueError, "1..32"):
            render_stereo_voices([voice()] * 33, frames=8)
        with self.assertRaisesRegex(ValueError, "timeline exceeds"):
            render_stereo_voices([voice(start=4)], frames=8)
        with self.assertRaisesRegex(ValueError, "gain must be finite"):
            render_stereo_voices([voice(left=float("nan"))], frames=6)
        for invalid in (True, 0, 882001):
            with self.assertRaises(ValueError):
                render_stereo_voices([voice()], frames=invalid)


class ChordTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.vh, self.vb = self.root / "bank.vh", self.root / "bank.vb"
        self.schedule, self.out = self.root / "voices.json", self.root / "song.wav"
        self.original_vh, self.original_vb = bank_fixture()
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb)
        self.notes = [
            {"program": 7, "note": 60, "channel_pan": 0,
             "start_frame": 0, "hold_frames": 6, "tail_frames": 2},
            {"program": 7, "note": 72, "channel_pan": 127,
             "start_frame": 1, "hold_frames": 6, "tail_frames": 2},
        ]

    def test_from_bank_to_stereo(self):
        wav_bytes, report = render_vab_chord(
            self.vh, self.vb, self.notes, interpolation="nearest"
        )
        self.assertEqual((report["frames"], report["channels"]), (9, 2))
        self.assertEqual([(x["vag"], x["selected_program"])
                          for x in report["voices"]], [(1, 7), (2, 7)])
        self.assertEqual([x["gain_right"] for x in report["voices"][:1]], [0])
        self.assertEqual(report["voices"][1]["gain_left"], 0)
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            self.assertEqual((wav.getnframes(), wav.getnchannels()), (9, 2))
            frames = list(struct.iter_unpack("<hh", wav.readframes(9)))
        self.assertGreater(frames[2][0], 0)
        self.assertLess(frames[2][1], 0)
        self.assertEqual(frames[0][1], 0)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_cli_read_only_inputs_and_no_existing_output_overwrite(self):
        self.schedule.write_text(json.dumps({"voices": self.notes}))
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "tools/render_vab_chord.py"),
            str(self.vh), str(self.vb), str(self.schedule), str(self.out),
            "--interpolation", "nearest",
        ]
        run = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(run.stdout)["frames"], 9)
        saved = self.out.read_bytes()
        repeated = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual(self.out.read_bytes(), saved)
        for source in (self.vh, self.vb, self.schedule):
            rejected = subprocess.run(
                [*command[:5], str(source), *command[6:]],
                capture_output=True, text=True
            )
            self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_bad_metadata_and_corrupted_audio(self):
        with self.assertRaises(ValueError):
            render_vab_chord(self.vh, self.vb, [{**self.notes[0], "velocity": True}])
        with self.assertRaises(ValueError):
            render_vab_chord(self.vh, self.vb, [{**self.notes[0], "oops": 5}])
        damaged = bytearray(self.original_vb)
        damaged[16] = 0x50
        self.vb.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "invalid predictor"):
            render_vab_chord(self.vh, self.vb, self.notes)
        self.assertEqual(self.vb.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()
