"""Synthetic dry note renderer regressions: exact PCM, loop, ADSR, VH/VB CLI."""
import io
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.render_vab_note import render_pcm_note, render_vab_note


def make_fixture():
    vh_header = bytearray(32)
    vh_header[:4] = b"pBAV"
    struct.pack_into("<HHHH", vh_header, 16, 0, 1, 1, 1)
    programs = bytearray(128 * 16)
    programs[7 * 16] = 1
    tone_block = bytearray(16 * 32)
    tone_block[4] = 60
    tone_block[6] = 20
    tone_block[7] = 80
    struct.pack_into("<HHhh", tone_block, 16, 0x000F, 0, 7, 1)
    units = [0] * 256
    units[0], units[1] = 2, 4
    vh = bytes(vh_header + programs + tone_block
               + struct.pack("<256H", *units))
    # Predictor 0 / shift 0, +2 signed 4-bit on every nibble -> +8192 PCM.
    raw = bytes([0, 4] + [0x22] * 14) + bytes([0, 3] + [0x22] * 14)
    vb = bytes(16) + raw + bytes(9)
    return vh, vb


class RenderPcmTests(unittest.TestCase):
    def test_key_on_off_sample_order_and_release_silence(self):
        pcm = struct.pack("<8h", *([10000] * 8))
        result, report = render_pcm_note(
            pcm, adsr1=0x000F, adsr2=0, pitch_step=0x1000,
            loop_start=None, loop_end=None, hold_frames=5, tail_frames=2
        )
        self.assertEqual(struct.unpack("<7h", result),
                         (4375, 8750, 10000, 10000, 10000, 4999, 0))
        self.assertEqual(report["frames_active"], 6)
        self.assertEqual(report["final_adsr_phase"], "off")
        self.assertEqual(report["first_key_off_frame"], 5)

    def test_fractional_pitch_uses_pre_advance_index(self):
        pcm = struct.pack("<4h", 10000, 20000, 30000, 4000)
        result, report = render_pcm_note(
            pcm, adsr1=0x000F, adsr2=0,
            pitch_step=0x800, loop_start=None, loop_end=None,
            hold_frames=4, tail_frames=0
        )
        self.assertEqual(struct.unpack("<4h", result), (4375, 8750, 20000, 20000))
        self.assertEqual(report["effective_pitch_step"], 0x800)
        self.assertIsNone(report["first_key_off_frame"])

    def test_loop_wrap_vs_early_one_shot_end(self):
        pcm = struct.pack("<4h", 4000, 8000, 12000, 16000)
        result, report = render_pcm_note(
            pcm, adsr1=0x000F, adsr2=0, pitch_step=0x1000,
            loop_start=1, loop_end=3, hold_frames=6, tail_frames=0
        )
        self.assertEqual(struct.unpack("<6h", result),
                         (1750, 7000, 12000, 8000, 12000, 8000))
        self.assertTrue(report["looped"])
        result, report = render_pcm_note(
            pcm[:4], adsr1=0x000F, adsr2=0, pitch_step=0x1000,
            loop_start=None, loop_end=None, hold_frames=6, tail_frames=0
        )
        self.assertEqual(struct.unpack("<6h", result),
                         (1750, 7000, 0, 0, 0, 0))
        self.assertFalse(report["looped"])

    def test_input_validation_and_hard_duration_cap(self):
        pcm = struct.pack("<h", 8000)
        base = dict(adsr1=0, adsr2=0, pitch_step=0x1000,
                    loop_start=None, loop_end=None,
                    hold_frames=1, tail_frames=0)
        for data in (b"", bytes([1])):
            with self.assertRaises(ValueError):
                render_pcm_note(data, **base)
        for invalid in (-1, float("nan"), float("inf"), 2.0, True, "1"):
            with self.subTest(gain=invalid):
                with self.assertRaises(ValueError):
                    render_pcm_note(pcm, **base, gain=invalid)
        for hold, tail in ((0, 0), (1, -1), (882001, 0),
                           (441001, 441000), (True, 0)):
            with self.subTest(hold=hold, tail=tail):
                with self.assertRaises(ValueError):
                    render_pcm_note(pcm, **dict(base, hold_frames=hold,
                                                tail_frames=tail))


class RenderBankNoteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vh = self.root / "bank.vh"
        self.vb = self.root / "bank.vb"
        self.out = self.root / "tone.wav"
        self.original_vh, self.original_vb = make_fixture()
        self.vh.write_bytes(self.original_vh)
        self.vb.write_bytes(self.original_vb)

    def test_end_to_end_note_pcm_and_coverage(self):
        wav, info = render_vab_note(
            self.vh, self.vb, program=7, note=60,
            hold_frames=70, tail_frames=4
        )
        self.assertEqual((info["selected_program"], info["tone"], info["vag"]),
                         (7, 0, 1))
        self.assertEqual(info["effective_pitch_step"], 0x1000)
        self.assertEqual((info["loop_start_frame"], info["loop_end_frame"]),
                         (0, 56))
        self.assertTrue(info["looped"])
        self.assertTrue(info["vb_bounds_verified"])
        self.assertEqual(info["adpcm_offset_in_vb"], 16)
        self.assertEqual(info["adpcm_size_bytes"], 32)
        self.assertEqual(len(info["render_pcm_sha256"]), 64)
        with wave.open(io.BytesIO(wav), "rb") as reader:
            self.assertEqual(
                (reader.getnchannels(), reader.getsampwidth(),
                 reader.getframerate(), reader.getnframes()),
                (1, 2, 44100, 74))
            output = struct.unpack("<74h", reader.readframes(74))
        self.assertEqual(output[:3], (3584, 7168, 8192))
        self.assertEqual(output[70], 4095)
        self.assertEqual(output[71:], (0, 0, 0))
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_cli_output_is_exclusive_and_source_protected(self):
        executable = Path(__file__).resolve().parents[1] / "tools/render_vab_note.py"
        command = [
            sys.executable, str(executable), str(self.vh), str(self.vb),
            str(self.out), "--program", "7", "--note", "60",
            "--hold-frames", "70", "--tail-frames", "4",
        ]
        first = subprocess.run(command, capture_output=True, text=True, check=True)
        report = json.loads(first.stdout)
        self.assertEqual(report["frames"], 74)
        saved = self.out.read_bytes()
        repeated = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertEqual(self.out.read_bytes(), saved)
        for target in (self.vh, self.vb):
            rejected = subprocess.run(
                [*command[:4], str(target), *command[5:]],
                capture_output=True, text=True
            )
            self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.vh.read_bytes(), self.original_vh)
        self.assertEqual(self.vb.read_bytes(), self.original_vb)

    def test_corrupt_adpcm_and_truncated_vb_rejected(self):
        self.vb.write_bytes(self.original_vb[:-20])
        with self.assertRaisesRegex(ValueError, "VB is truncated"):
            render_vab_note(self.vh, self.vb, program=7, note=60,
                            hold_frames=3, tail_frames=2)
        broken = bytearray(self.original_vb)
        broken[16] = 0x50
        self.vb.write_bytes(broken)
        with self.assertRaisesRegex(ValueError, "invalid predictor"):
            render_vab_note(self.vh, self.vb, program=7, note=60,
                            hold_frames=3, tail_frames=2)
        self.assertEqual(self.vb.read_bytes(), broken)


if __name__ == "__main__":
    unittest.main()
