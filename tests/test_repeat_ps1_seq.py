"""Synthetic finite/infinite PlayStation SEQ replay and loop seam tests."""
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
from tools.inspect_ps1_seq import parse_seq
from tools.repeat_ps1_seq import expand_seq_repeats
from tools.seq_to_chord_schedule import seq_to_schedule
from tools.render_ps1_seq import render_ps1_seq
from test_seq_to_chord_schedule import hdr, synthetic_vab


def vlq(value):
    pieces = [value & 127]
    value >>= 7
    while value:
        pieces.insert(0, (value & 127) | 128)
        value >>= 7
    return bytes(pieces)


def held_across_seam():
    # At tick zero: an initially harmless NoteOff. At tick120 start the
    # note, and reach EOT at tick240. The note stays held across the
    # *first* EOT; next cycle's zero-delta NoteOff ends it.
    return (hdr() + bytes([0, 0x80, 60, 0])
            + vlq(120) + bytes([0x90, 60, 100])
            + vlq(120) + bytes([0xFF, 0x2F]))


def tempo_changes():
    # Cycle 1: first 120 ticks @ 500000, second 120 @ 250000.
    # In cycle 2 the inherited opening tempo is 250000.
    return (hdr() + bytes([0, 0x90, 60, 100])
            + vlq(120) + bytes([0xFF, 0x51, 0x03, 0xD0, 0x90])
            + vlq(120) + bytes([0x80, 60, 0])
            + bytes([0, 0xFF, 0x2F]))


def simple_loop():
    return (hdr() + bytes([0, 0x90, 60, 100])
            + vlq(480) + bytes([0xFF, 0x2F]))


class ReplayTests(unittest.TestCase):
    def test_single_repeat_keeps_existing_event_frames(self):
        original = parse_seq(held_across_seam())
        playback = expand_seq_repeats(original)
        self.assertEqual(
            [(e["type"], e["frame"]) for e in playback["events"]],
            [(e["type"], e["frame"]) for e in original["events"]]
        )
        self.assertEqual(playback["repeat_count_requested"], 1)
        self.assertEqual(playback["cycles_completed"], 1)
        self.assertFalse(playback["stopped_by_window"])

    def test_clean_seam_preserves_held_note_until_next_loop_noteoff(self):
        playback = expand_seq_repeats(
            parse_seq(held_across_seam()), repeat_count=2
        )
        self.assertEqual(playback["total_frames"], 22050)
        self.assertEqual(
            [(e["type"], e["frame"]) for e in playback["events"]],
            [
                ("note_off", 0), ("note_on", 5512),
                ("loop_boundary", 11025),
                ("note_off", 11025), ("note_on", 16537),
                ("end_of_track", 22050),
            ]
        )
        voices = seq_to_schedule(playback, release_frames=9)["voices"]
        self.assertEqual(len(voices), 2)
        self.assertEqual((voices[0]["start_frame"], voices[0]["hold_frames"]),
                         (5512, 5513))
        self.assertEqual((voices[1]["start_frame"], voices[1]["hold_frames"]),
                         (16537, 5513))

    def test_tempo_persists_across_cycles_without_cumulative_rounding(self):
        playback = expand_seq_repeats(
            parse_seq(tempo_changes()), repeat_count=2
        )
        self.assertEqual(
            [(e["type"], e["frame"]) for e in playback["events"]],
            [
                ("note_on", 0),
                ("tempo", 5512),
                ("note_off", 8268),
                ("loop_boundary", 8268),
                ("note_on", 8268),
                ("tempo", 11025),
                ("note_off", 13781),
                ("end_of_track", 13781),
            ]
        )

    def test_infinite_loop_must_have_finite_window(self):
        report = parse_seq(simple_loop())
        with self.assertRaisesRegex(ValueError, "explicit max_frames"):
            expand_seq_repeats(report, repeat_count=0)
        repeated = expand_seq_repeats(
            report, repeat_count=0, max_frames=30000
        )
        self.assertEqual(repeated["total_frames"], 30000)
        self.assertEqual(repeated["cycles_completed"], 1)
        self.assertTrue(repeated["stopped_by_window"])
        self.assertEqual(repeated["events"][-1]["type"], "end_of_track")
        self.assertTrue(repeated["events"][-1]["truncated_by_window"])
        self.assertEqual(
            [e["frame"] for e in repeated["events"] if e["type"] == "note_on"],
            [0, 22050],
        )
        voices = seq_to_schedule(repeated, release_frames=1000)["voices"]
        self.assertEqual(voices[-1]["tail_frames"], 0)
        self.assertEqual(voices[-1]["hold_frames"], 7950)
        self.assertEqual(voices[-1]["start_frame"], 22050)

    def test_rejects_zero_duration_infinite_and_bad_repeat_args(self):
        empty_time = (hdr()
                      + bytes([0, 0x90, 60, 100, 0, 0xFF, 0x2F]))
        with self.assertRaisesRegex(ValueError, "zero-duration"):
            expand_seq_repeats(parse_seq(empty_time),
                               repeat_count=0, max_frames=1000)
        parsed = parse_seq(simple_loop())
        for bad in (True, -1, 65, 2.5):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "repeat_count"):
                    expand_seq_repeats(parsed, repeat_count=bad)
        for bad in (True, 0, -1, 882001, 50.5):
            with self.subTest(window=bad):
                with self.assertRaisesRegex(ValueError, "max_frames"):
                    expand_seq_repeats(parsed, repeat_count=0, max_frames=bad)
        with self.assertRaisesRegex(ValueError, "finite SEQ exceeds"):
            expand_seq_repeats(parsed, repeat_count=2, max_frames=30000)

    def test_stereo_integration_two_repeats_and_infinite_window(self):
        with tempfile.TemporaryDirectory() as folder:
            vh, vb = Path(folder) / "test.vh", Path(folder) / "test.vb"
            vh_bytes, vb_bytes = synthetic_vab()
            vh.write_bytes(vh_bytes)
            vb.write_bytes(vb_bytes)
            wav, report = render_ps1_seq(
                held_across_seam(), vh, vb,
                repeat_count=2, release_frames=0,
                interpolation="nearest",
            )
            self.assertEqual(report["repeat_cycles_completed"], 2)
            self.assertEqual(len(report["voices"]), 2)
            self.assertEqual(report["seq_end_frame"], 22050)
            with wave.open(io.BytesIO(wav), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertEqual(stream.getnframes(), 22050)

            wav, report = render_ps1_seq(
                simple_loop(), vh, vb,
                repeat_count=0, max_frames=30000,
                release_frames=0, interpolation="nearest",
            )
            self.assertTrue(report["repeat_window_stop"])
            self.assertEqual(len(report["voices"]), 2)
            with wave.open(io.BytesIO(wav), "rb") as stream:
                self.assertEqual(stream.getnframes(), 30000)
            self.assertEqual(vh.read_bytes(), vh_bytes)
            self.assertEqual(vb.read_bytes(), vb_bytes)

    def test_repeat_cli_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "example.seq"
            data = held_across_seam()
            path.write_bytes(data)
            cmd = [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "tools/repeat_ps1_seq.py"),
                str(path), "--repeat-count", "2",
            ]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            report = json.loads(result.stdout)
            self.assertEqual(report["cycles_completed"], 2)
            self.assertEqual(path.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
