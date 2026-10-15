"""Synthetic regression for 20-slot PC-port SEQ allocator and long score mixing."""
import io
import json
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import parse_seq
from tools.mix_spu_stereo import (
    StereoVoice, render_stereo_timeline, render_stereo_voices,
)
from tools.seq_to_chord_schedule import (
    MAX_SEQ_NOTES, SEQ_VOICE_COUNT, seq_to_schedule,
)
from tools.render_ps1_seq import render_ps1_seq
from tools.render_vab_chord import render_vab_chord
from test_seq_to_chord_schedule import hdr, synthetic_vab


def serial_song(count=45):
    # 45 individual key-ons followed by key-offs, one tick per hold.
    events = bytearray([0, 0xC0, 7])
    for _ in range(count):
        events.extend([0, 0x90, 60, 110, 1, 0x80, 60, 0])
    events.extend([0, 0xFF, 0x2F])
    return hdr() + bytes(events)


def cluster_song():
    # All 20 slots filled at t=0. On the next tick, steal slot 0,
    # and one tick later steal slot 1. A stale NoteOff for slot 0's
    # first owner must not terminate the new owner of slot 0.
    events = bytearray([0, 0xC0, 7])
    for n in range(40, 60):
        events.extend([0, 0x90, n, 100])
    events.extend([1, 0x90, 60, 100])
    events.extend([0, 0x80, 40, 0])
    events.extend([1, 0x90, 61, 100])
    events.extend([1, 0xFF, 0x2F])
    return hdr() + bytes(events)


class SeqSlotTests(unittest.TestCase):
    def test_reference_20_slots_and_45_sequential_note_ons(self):
        self.assertEqual(SEQ_VOICE_COUNT, 20)
        scheduled = seq_to_schedule(parse_seq(serial_song()), release_frames=0)
        notes = scheduled["voices"]
        self.assertEqual(len(notes), 45)
        self.assertEqual({n["voice_slot"] for n in notes}, {0})
        self.assertTrue(all(n["hold_frames"] >= 1 for n in notes))
        self.assertTrue(all(n["tail_frames"] == 0 for n in notes))
        self.assertLessEqual(MAX_SEQ_NOTES, 2048)

    def test_round_robin_steals_and_late_noteoff_keeps_new_owner(self):
        scheduled = seq_to_schedule(parse_seq(cluster_song()), release_frames=4)
        notes = scheduled["voices"]
        self.assertEqual(len(notes), 22)
        self.assertEqual([n["voice_slot"] for n in notes[:20]], list(range(20)))
        self.assertEqual([n["voice_slot"] for n in notes[20:]], [0, 1])
        self.assertEqual(notes[0]["tail_frames"], 0)
        self.assertEqual(notes[0]["hold_frames"], 45)
        self.assertEqual(notes[1]["tail_frames"], 0)
        self.assertEqual(notes[1]["hold_frames"], 91)
        self.assertEqual(notes[20]["note"], 60)
        # Stale NoteOff 40 at tick1 cannot release the newly stolen voice.
        self.assertGreater(notes[20]["hold_frames"], 1)
        self.assertEqual(notes[20]["hold_frames"], 91)
        for note in notes:
            self.assertTrue(0 <= note["voice_slot"] < SEQ_VOICE_COUNT)

    def test_same_frame_steal_drops_inaudible_first_instance(self):
        events = bytearray([0, 0xC0, 7])
        for note in range(40, 61):
            events.extend([0, 0x90, note, 80])
        events.extend([1, 0xFF, 0x2F])
        notes = seq_to_schedule(parse_seq(hdr() + events),
                                release_frames=0)["voices"]
        self.assertEqual(len(notes), 20)
        self.assertNotIn(40, {n["note"] for n in notes})
        self.assertIn(60, {n["note"] for n in notes})
        self.assertEqual(
            len({n["voice_slot"] for n in notes}), SEQ_VOICE_COUNT
        )

    def test_vab_pipeline_renders_more_than_32_notes(self):
        song = serial_song()
        vh_raw, vb_raw = synthetic_vab()
        with tempfile.TemporaryDirectory() as folder:
            vh = Path(folder) / "bank.vh"
            vb = Path(folder) / "bank.vb"
            vh.write_bytes(vh_raw)
            vb.write_bytes(vb_raw)
            wav, result = render_ps1_seq(
                song, vh, vb, release_frames=0, interpolation="nearest"
            )
            self.assertEqual(result["mode"], "20_slot_seq_timeline")
            self.assertEqual(len(result["voices"]), 45)
            self.assertEqual(result["channels"], 2)
            with wave.open(io.BytesIO(wav), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertGreater(stream.getnframes(), 1800)
                self.assertLess(stream.getnframes(), 2500)
            self.assertEqual(vh.read_bytes(), vh_raw)
            self.assertEqual(vb.read_bytes(), vb_raw)

    def test_timeline_matches_existing_mixer_when_no_slots_overlap(self):
        pcm = struct.pack("<8h", *([12000] * 8))
        a = StereoVoice(pcm, 15, 0, 4096, 0, 8, 0, 4, 1,
                        1.0, 0.0, voice_slot=0)
        b = StereoVoice(pcm, 15, 0, 4096, 0, 8, 1, 4, 1,
                        0.0, 1.0, voice_slot=1)
        new_pcm, state = render_stereo_timeline(
            [a, b], frames=6, interpolation="nearest"
        )
        old_pcm, _ = render_stereo_voices(
            [a, b], frames=6, interpolation="nearest"
        )
        self.assertEqual(new_pcm, old_pcm)
        self.assertEqual(len(state), 2)

    def test_timeline_rejects_overlapping_same_slot_and_invalid_slot(self):
        pcm = struct.pack("<4h", 1000, 1000, 1000, 1000)
        a = StereoVoice(pcm, 0, 0, 4096, 0, 4, 0, 4, 0,
                        1.0, 1.0, voice_slot=0)
        overlap = StereoVoice(pcm, 0, 0, 4096, 0, 4, 2, 3, 0,
                              1.0, 1.0, voice_slot=0)
        with self.assertRaisesRegex(ValueError, "overlapping SEQ slot"):
            render_stereo_timeline([a, overlap], frames=5)
        invalid = StereoVoice(pcm, 0, 0, 4096, 0, 4, 0, 4, 0,
                              1.0, 1.0, voice_slot=20)
        with self.assertRaisesRegex(ValueError, "SEQ slot 0..19"):
            render_stereo_timeline([invalid], frames=4)

    def test_manual_unassigned_more_than_32_not_allowed(self):
        vh_raw, vb_raw = synthetic_vab()
        with tempfile.TemporaryDirectory() as folder:
            vh = Path(folder) / "v.vh"
            vb = Path(folder) / "v.vb"
            vh.write_bytes(vh_raw)
            vb.write_bytes(vb_raw)
            manual = [{"program": 7, "note": 60, "hold_frames": 1}] * 33
            with self.assertRaisesRegex(ValueError, "manual chord"):
                render_vab_chord(vh, vb, manual, interpolation="nearest")


if __name__ == "__main__":
    unittest.main()
