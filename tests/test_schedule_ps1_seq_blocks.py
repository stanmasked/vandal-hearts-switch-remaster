"""Synthetic PC-port 512-frame SEQ advance-before-render regression suite."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import parse_seq
from tools.repeat_ps1_seq import expand_seq_repeats
from tools.schedule_ps1_seq_blocks import (
    SPU_BLOCK_FRAMES, schedule_seq_audio_blocks,
)
from tools.render_ps1_seq import render_ps1_seq
from test_seq_to_chord_schedule import hdr, synthetic_vab


def vlq(number):
    parts = [number & 127]
    number >>= 7
    while number:
        parts.insert(0, (number & 127) | 128)
        number >>= 7
    return bytes(parts)


def stepped_song():
    # Note-on at tick0, note-off at tick10, NoteOn tick30, EOT tick30.
    return (hdr() + bytes([0, 0x90, 60, 100])
            + vlq(10) + bytes([0x80, 60, 0])
            + vlq(20) + bytes([0x90, 60, 100])
            + bytes([0, 0xFF, 0x2F]))


def changed_tempo_song():
    # 10 ticks at 500k tempo -> FF51 during first block; subsequent
    # blocks use new 250k tempo for entire 512-frame advance.
    return (hdr() + bytes([0, 0x90, 60, 100])
            + vlq(10) + bytes([0xFF, 0x51, 0x03, 0xD0, 0x90])
            + vlq(20) + bytes([0x80, 60, 0])
            + vlq(20) + bytes([0xFF, 0x2F]))


def repeating_song():
    return (hdr() + bytes([0, 0x90, 60, 100])
            + vlq(10) + bytes([0x80, 60, 0])
            + vlq(10) + bytes([0xFF, 0x2F]))


class SpuBlockSchedulerTests(unittest.TestCase):
    def test_dispatch_at_start_of_next_render_block(self):
        data = parse_seq(stepped_song())
        self.assertEqual(SPU_BLOCK_FRAMES, 512)
        ideal = expand_seq_repeats(data)
        scheduled = schedule_seq_audio_blocks(data)
        self.assertEqual(
            [(item["type"], item["frame"]) for item in scheduled["events"]],
            [("note_on", 0), ("note_off", 0),
             ("note_on", 1024), ("end_of_track", 1024)],
        )
        self.assertEqual(
            [item["frame"] for item in ideal["events"]],
            [0, 459, 1378, 1378],
        )
        self.assertEqual(scheduled["timing_mode"], "pc_block512")
        self.assertEqual(scheduled["spu_block_frames"], 512)
        self.assertEqual(scheduled["serviced_blocks"], 3)

    def test_mid_block_tempo_change_applies_to_subsequent_blocks(self):
        scheduled = schedule_seq_audio_blocks(parse_seq(changed_tempo_song()))
        self.assertEqual(
            [(item["type"], item["frame"]) for item in scheduled["events"]],
            [("note_on", 0), ("tempo", 0),
             ("note_off", 512), ("end_of_track", 1024)]
        )
        self.assertEqual(scheduled["cycles_completed"], 1)

    def test_finite_two_passes_reset_budget_and_keep_previous_tempo(self):
        scheduled = schedule_seq_audio_blocks(
            parse_seq(repeating_song()), repeat_count=2
        )
        self.assertEqual(
            [(item["type"], item["frame"], item["cycle"])
             for item in scheduled["events"]],
            [
                ("note_on", 0, 0), ("note_off", 0, 0),
                ("loop_boundary", 512, 0),
                ("note_on", 512, 1), ("note_off", 1024, 1),
                ("end_of_track", 1536, 1),
            ]
        )
        self.assertEqual(scheduled["cycles_completed"], 2)
        self.assertFalse(scheduled["stopped_by_window"])

    def test_infinite_hard_stop_has_no_unbounded_output(self):
        data = parse_seq(repeating_song())
        with self.assertRaisesRegex(ValueError, "explicit max_frames"):
            schedule_seq_audio_blocks(data, repeat_count=0)
        playback = schedule_seq_audio_blocks(
            data, repeat_count=0, max_frames=1000
        )
        self.assertTrue(playback["stopped_by_window"])
        self.assertEqual(playback["total_frames"], 1000)
        self.assertEqual(playback["cycles_completed"], 1)
        self.assertEqual(playback["events"][-1]["frame"], 1000)
        self.assertTrue(playback["events"][-1]["truncated_by_window"])
        self.assertEqual(
            [e["frame"] for e in playback["events"] if e["type"] == "note_on"],
            [0, 512],
        )

    def test_limits_nonmonotonic_ticks_and_zero_duration_loop(self):
        data = parse_seq(repeating_song())
        for val in (True, -1, 65, 1.5):
            with self.subTest(repeat_count=val):
                with self.assertRaisesRegex(ValueError, "repeat_count"):
                    schedule_seq_audio_blocks(data, repeat_count=val)
        with self.assertRaisesRegex(ValueError, "max_frames"):
            schedule_seq_audio_blocks(data, max_frames=True)
        with self.assertRaisesRegex(ValueError, "finite SEQ cannot"):
            schedule_seq_audio_blocks(data, repeat_count=2, max_frames=800)
        corrupted = dict(data, events=[dict(event) for event in data["events"]])
        corrupted["events"][1]["tick"] = -1
        with self.assertRaisesRegex(ValueError, "nonmonotonic"):
            schedule_seq_audio_blocks(corrupted)
        zero = parse_seq(hdr() + bytes([0, 0x90, 60, 100, 0, 0xFF, 0x2F]))
        with self.assertRaisesRegex(ValueError, "zero-duration"):
            schedule_seq_audio_blocks(zero, repeat_count=0, max_frames=1024)

    def test_stereo_wav_output_and_adsr_mode_from_synthetic_seq_bank(self):
        data = repeating_song()
        vh_bytes, vb_bytes = synthetic_vab()
        with tempfile.TemporaryDirectory() as root:
            vh, vb = Path(root) / "bank.vh", Path(root) / "bank.vb"
            vh.write_bytes(vh_bytes)
            vb.write_bytes(vb_bytes)
            wav, report = render_ps1_seq(
                data, vh, vb, repeat_count=2, release_frames=0,
                interpolation="nearest", timing_mode="pc_block512",
                voice_lifetime="adsr",
            )
            self.assertEqual(report["seq_timing_mode"], "pc_block512")
            self.assertEqual(report["spu_block_frames"], 512)
            self.assertEqual(report["repeat_cycles_completed"], 2)
            self.assertEqual(len(report["voices"]), 2)
            self.assertEqual([n["start_frame"] for n in report["voices"]],
                             [0, 512])
            with wave.open(io.BytesIO(wav), "rb") as reader:
                self.assertEqual(reader.getnchannels(), 2)
                self.assertGreaterEqual(reader.getnframes(), 513)
            self.assertEqual(vh.read_bytes(), vh_bytes)
            self.assertEqual(vb.read_bytes(), vb_bytes)

    def test_standalone_readonly_cli(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "test.seq"
            raw = repeating_song()
            path.write_bytes(raw)
            proc = subprocess.run(
                [sys.executable,
                 str(Path(__file__).resolve().parents[1]
                     / "tools/schedule_ps1_seq_blocks.py"),
                 str(path), "--repeat-count", "2"],
                text=True, capture_output=True, check=True
            )
            result = json.loads(proc.stdout)
            self.assertEqual(result["cycles_completed"], 2)
            self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
