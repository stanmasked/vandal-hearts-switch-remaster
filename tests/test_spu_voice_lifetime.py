"""Synthetic ADSR-based SEQ voice occupancy versus fixed-tail allocation."""
import io
import json
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.spu_voice_lifetime import SpuVoiceClock, SpuVoiceSpec
from tools.seq_to_chord_schedule import seq_to_schedule
from tools.render_ps1_seq import render_ps1_seq
from test_seq_to_chord_schedule import hdr, synthetic_vab


LOOP = SpuVoiceSpec(0x000F, 0x0000, 56, 0x1000, 0, 56)
ONE_SHOT = SpuVoiceSpec(0x000F, 0x0000, 3, 0x1000, None, None)
AUTO_FADE = SpuVoiceSpec(0x000F, 0x4000, 56, 0x1000, 0, 56)


def note_on(channel, note, frame):
    return dict(type="note_on", channel=channel, note=note,
                velocity=100, frame=frame)


def note_off(channel, note, frame):
    return dict(type="note_off", channel=channel, note=note,
                velocity=0, frame=frame)


def report(events):
    return {"format": "PS1 SEQ", "events": events}


class VoiceLifetimeTests(unittest.TestCase):
    def test_one_shot_cursor_exhaustion_is_exclusive_frame(self):
        clock = SpuVoiceClock(ONE_SHOT, 10)
        self.assertIsNone(clock.advance_to(12))
        self.assertEqual(clock.advance_to(25), 13)
        self.assertEqual(clock.terminal_frame, 13)
        self.assertEqual(clock.advance_to(25), 13)
        self.assertEqual(clock.key_off(25), 13)

    def test_release_zero_before_first_release_sample(self):
        clock = SpuVoiceClock(LOOP, 0)
        self.assertIsNone(clock.advance_to(3))
        self.assertIsNone(clock.key_off(3))
        self.assertIsNone(clock.advance_to(4))
        self.assertEqual(clock.advance_to(5), 4)
        self.assertEqual(clock.terminal_frame, 4)

    def test_auto_sustain_fade_releases_still_held_voice(self):
        song = report([
            note_on(0, 40, 0),
            note_on(0, 41, 30),
            note_off(0, 41, 40),
            {"type": "end_of_track", "frame": 40},
        ])
        modeled = seq_to_schedule(
            song, release_frames=100,
            voice_spec_for_note=lambda program, note:
                AUTO_FADE if note == 40 else LOOP,
        )["voices"]
        fixed = seq_to_schedule(song, release_frames=100)["voices"]
        self.assertEqual([v["voice_slot"] for v in modeled], [0, 0])
        self.assertEqual([v["voice_slot"] for v in fixed], [0, 1])
        self.assertLess(modeled[0]["hold_frames"], 30)
        self.assertEqual(modeled[0]["tail_frames"], 0)

    def test_one_shot_end_and_same_stale_noteoff(self):
        song = report([
            note_on(0, 40, 0),
            note_on(0, 41, 20),
            note_off(0, 40, 25),
            note_off(0, 41, 30),
            {"type": "end_of_track", "frame": 30},
        ])
        modeled = seq_to_schedule(
            song, release_frames=70,
            voice_spec_for_note=lambda p, n: ONE_SHOT if n == 40 else LOOP,
        )["voices"]
        self.assertEqual([v["voice_slot"] for v in modeled], [0, 0])
        self.assertEqual(modeled[0]["hold_frames"], 3)
        self.assertEqual(modeled[0]["tail_frames"], 0)
        self.assertEqual(modeled[1]["hold_frames"], 10)

    def test_free_release_slot_changes_round_robin_steal(self):
        events = [note_on(0, n, 0) for n in range(40, 60)]
        events += [
            note_off(0, 40, 5),
            note_on(0, 60, 20),
            note_on(0, 61, 20),
            {"type": "end_of_track", "frame": 35},
        ]
        modeled = seq_to_schedule(
            report(events), release_frames=100,
            voice_spec_for_note=lambda _p, _n: LOOP,
        )["voices"]
        fixed = seq_to_schedule(report(events), release_frames=100)["voices"]
        self.assertEqual(modeled[-1]["note"], 61)
        self.assertEqual(modeled[-1]["voice_slot"], 0)
        self.assertEqual(fixed[-1]["voice_slot"], 1)
        self.assertEqual(modeled[0]["hold_frames"], 5)
        self.assertEqual(modeled[0]["tail_frames"], 1)
        self.assertEqual(fixed[0]["tail_frames"], 15)

    def test_invalid_spec_and_clock_limits(self):
        bad = report([note_on(0, 60, 0), {"type": "end_of_track", "frame": 5}])
        with self.assertRaisesRegex(ValueError, "SpuVoiceSpec"):
            seq_to_schedule(bad, voice_spec_for_note=lambda p, n: None)
        with self.assertRaisesRegex(ValueError, "start out of range"):
            SpuVoiceClock(LOOP, -1)
        clock = SpuVoiceClock(LOOP, 0)
        with self.assertRaisesRegex(ValueError, "target out of range"):
            clock.advance_to(True)

    def test_integrated_local_vh_vb_adsr_vs_fixed_tail(self):
        seq = (hdr()
               + bytes([0, 0xC0, 7, 0, 0x90, 60, 100,
                        1, 0x80, 60, 0, 0, 0xFF, 0x2F]))
        raw_vh, raw_vb = synthetic_vab()
        with tempfile.TemporaryDirectory() as folder:
            vh, vb = Path(folder) / "voice.vh", Path(folder) / "voice.vb"
            vh.write_bytes(raw_vh)
            vb.write_bytes(raw_vb)
            fixed_wav, fixed = render_ps1_seq(
                seq, vh, vb, voice_lifetime="fixed",
                release_frames=500, interpolation="nearest"
            )
            adsr_wav, adsr = render_ps1_seq(
                seq, vh, vb, voice_lifetime="adsr",
                release_frames=500, interpolation="nearest"
            )
            self.assertEqual(fixed["voice_lifetime_model"], "fixed")
            self.assertEqual(adsr["voice_lifetime_model"], "adsr")
            self.assertEqual(adsr["voices"][0]["tail_frames"], 1)
            self.assertEqual(fixed["voices"][0]["tail_frames"], 500)
            self.assertEqual(adsr["frames"], 46)
            self.assertEqual(fixed["frames"], 545)
            with wave.open(io.BytesIO(adsr_wav), "rb") as reader:
                self.assertEqual(reader.getnframes(), 46)
            self.assertEqual(vh.read_bytes(), raw_vh)
            self.assertEqual(vb.read_bytes(), raw_vb)


if __name__ == "__main__":
    unittest.main()
