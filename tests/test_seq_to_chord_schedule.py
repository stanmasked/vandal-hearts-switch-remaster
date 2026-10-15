"""Synthetic SEQ -> offline chord-schedule tests with no game assets."""
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
from tools.render_vab_chord import render_vab_chord
from tools.seq_to_chord_schedule import seq_to_schedule


def hdr():
    return b"pQES" + bytes(4) + (480).to_bytes(2, "big") + (500000).to_bytes(3, "big") + bytes(2)


def base_events():
    # Multiple channels, program change, channel CC07 and CC0A, tempo
    # change, running status, note-on with velocity zero, end-of-track.
    return (
        bytes([0, 0xC0, 7, 0, 0xB0, 7, 100, 0, 0xB0, 10, 0,
               0, 0x90, 60, 100, 0x78, 0x91, 64, 64,
               0, 0xB0, 7, 80, 0, 0xB0, 10, 127,
               0x78, 0x90, 60, 0,
               0, 0xFF, 0x51, 0x03, 0xD0, 0x90,
               0x78, 0x81, 64, 40,
               0, 0xFF, 0x2F])
    )


def synthetic_vab():
    h = bytearray(32)
    h[:4] = b"pBAV"
    struct.pack_into("<HHHH", h, 16, 0, 2, 2, 2)
    h[24] = 127
    p = bytearray(128 * 16)
    p[0], p[0 + 1], p[4] = 1, 127, 64
    p[7 * 16], p[7 * 16 + 1], p[7 * 16 + 4] = 1, 127, 64
    tones = bytearray(2 * 16 * 32)
    for pos, prog, vag, center in ((0, 0, 1, 64), (16 * 32, 7, 2, 60)):
        tones[pos + 2] = 127
        tones[pos + 3] = 64
        tones[pos + 4] = center
        tones[pos + 6] = 0
        tones[pos + 7] = 127
        struct.pack_into("<HHhh", tones, pos + 16, 15, 0, prog, vag)
    sizes = [0] * 256
    sizes[:3] = [2, 4, 4]
    vh = bytes(h + p + tones + struct.pack("<256H", *sizes))
    adpcm = bytes([12, 4] + [0x11] * 14) + bytes([12, 3] + [0x11] * 14)
    return vh, bytes(16) + adpcm * 2


class SeqScheduleTests(unittest.TestCase):
    def test_tempo_and_program_volume_snapshots(self):
        parsed = parse_seq(hdr() + base_events())
        scheduled = seq_to_schedule(parsed, release_frames=441)
        a, b = scheduled["voices"]
        self.assertEqual(len(scheduled["voices"]), 2)
        self.assertEqual((a["program"], a["note"], a["velocity"],
                          a["channel_volume"], a["channel_pan"]),
                         (7, 60, 100, 100, 0))
        self.assertEqual((a["start_frame"], a["hold_frames"], a["tail_frames"]),
                         (0, 11025, 441))
        self.assertEqual((b["program"], b["note"], b["velocity"],
                          b["channel_volume"], b["channel_pan"]),
                         (0, 64, 64, 127, 64))
        self.assertEqual((b["start_frame"], b["hold_frames"]),
                         (5512, 8269))
        self.assertEqual(a["channel_volume"], 100)
        self.assertEqual(b["channel_volume"], 127)

    def test_retrigger_and_channel_all_notes_off(self):
        data = hdr() + bytes([
            0, 0x90, 60, 90,
            10, 60, 100,  # running NOTE ON retriggers the same note
            5, 0xB0, 0x7B, 0,
            0, 0xFF, 0x2F,
        ])
        schedule = seq_to_schedule(parse_seq(data), release_frames=4)["voices"]
        self.assertEqual(len(schedule), 2)
        self.assertEqual(schedule[0]["hold_frames"], 459)
        self.assertEqual(schedule[1]["start_frame"], 459)
        self.assertEqual(schedule[1]["hold_frames"], 230)
        self.assertEqual([s["tail_frames"] for s in schedule], [4, 4])

    def test_end_track_releases_all_and_same_frame_note_minimum(self):
        result = seq_to_schedule(parse_seq(
            hdr() + bytes([0, 0x90, 60, 100, 0, 0xFF, 0x2F])),
            release_frames=0
        )
        self.assertEqual(result["voices"][0]["hold_frames"], 1)
        self.assertEqual(result["voices"][0]["tail_frames"], 0)
        with self.assertRaisesRegex(ValueError, "no note-on"):
            seq_to_schedule(parse_seq(hdr() + bytes([0, 0xFF, 0x2F])))

    def test_voice_cap_and_release_bounds(self):
        events = bytes([0, 0x90, 60, 100, 0, 0x80, 60, 0]) * 33
        parsed = parse_seq(hdr() + events + bytes([0, 0xFF, 0x2F]))
        with self.assertRaisesRegex(ValueError, "32-note"):
            seq_to_schedule(parsed)
        with self.assertRaisesRegex(ValueError, "release_frames"):
            seq_to_schedule(parsed, release_frames=True)
        with self.assertRaisesRegex(ValueError, "release_frames"):
            seq_to_schedule(parsed, release_frames=-1)
        # Valid short sequence positioned at the very end of the 20 s limit
        # cannot carry a release tail beyond the allowed window.
        delayed = (hdr() + bytes([0x87, 0xA0, 0,  # delta 122880 ticks (128*? sanity)
                                 0x90, 60, 100, 0, 0xFF, 0x2F]))
        # Use a controlled report so this tests the boundary independently
        # from the parser's VLQ arithmetic.
        seq = parse_seq(hdr() + bytes([0, 0x90, 60, 100, 0, 0xFF, 0x2F]))
        seq["events"][0]["frame"] = 882000
        seq["events"][1]["frame"] = 882000
        with self.assertRaisesRegex(ValueError, "release exceeds"):
            seq_to_schedule(seq, release_frames=0)

    def test_cli_and_interoperation_with_existing_stereo_chord_renderer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seq = root / "input.seq"
            destination = root / "voices.json"
            vh = root / "bank.vh"
            vb = root / "bank.vb"
            seq_bytes = hdr() + bytes([0, 0xC0, 7,
                                       0, 0x90, 60, 100,
                                       1, 0x80, 60, 0,
                                       0, 0xFF, 0x2F])
            seq.write_bytes(seq_bytes)
            vh_bytes, vb_bytes = synthetic_vab()
            vh.write_bytes(vh_bytes)
            vb.write_bytes(vb_bytes)
            command = [
                sys.executable,
                str(Path(__file__).resolve().parents[1]
                    / "tools/seq_to_chord_schedule.py"),
                str(seq), str(destination), "--release-frames", "4",
            ]
            proc = subprocess.run(command, text=True, capture_output=True,
                                  check=True)
            self.assertEqual(json.loads(proc.stdout)["voice_count"], 1)
            schedule = json.loads(destination.read_text())
            self.assertEqual(schedule["voices"][0]["program"], 7)
            wav, diagnostic = render_vab_chord(
                vh, vb, schedule["voices"], interpolation="nearest"
            )
            self.assertEqual(diagnostic["voices"][0]["selected_program"], 7)
            with wave.open(io.BytesIO(wav), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertGreater(stream.getnframes(), 1)
            self.assertNotEqual(subprocess.run(
                command, text=True, capture_output=True
            ).returncode, 0)
            self.assertEqual(seq.read_bytes(), seq_bytes)
            self.assertEqual(vh.read_bytes(), vh_bytes)
            self.assertEqual(vb.read_bytes(), vb_bytes)


if __name__ == "__main__":
    unittest.main()
