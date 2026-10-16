"""Local-only SEQ/VH/VB transition auditor, synthetic fixture tests.

The CLI does not transmit or serialize any original music source bytes.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.generate_ps1_music_sd_fixture import make_synthetic_files

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = Path(os.environ.get("VH_LOCAL_MUSIC_TRANSITION_PROBE",
                              str(ROOT / "build" / "vh_local_music_transition_probe")))
TONE_OFFSET = 32 + 128 * 16


def synth_dir(directory, wet=False, bank_b=False, fallback_program=False,
              out_of_range_note=False, mute_master=False,
              no_note_on=False):
    directory.mkdir()
    files = make_synthetic_files()
    vh = bytearray(files["music.vh"])
    vb = bytearray(files["music.vb"])
    if wet:
        vh[TONE_OFFSET + 1] = 4  # Valid VAB reverb-send mode.
    if mute_master:
        vh[24] = 0  # Every note resolves, but both output gains are zero.
    if bank_b:
        vb[18:32] = b"\x44" * 14
        vb[34:48] = b"\xDD" * 14
    files["music.vh"] = bytes(vh)
    files["music.vb"] = bytes(vb)
    if fallback_program or out_of_range_note or no_note_on:
        seq = bytearray(files["music.seq"])
        if fallback_program:
            # Program 9 is missing. The global resolver chooses program 7.
            program_event = seq.index(0xC0)
            assert seq[program_event + 1] == 7
            seq[program_event + 1] = 9
        if out_of_range_note:
            # Program 7 exists, but key 110 lies beyond tone's 40..100
            # range. This exercises closest-range fallback in same program.
            on = seq.index(0x90)
            off = seq.index(0x80)
            assert seq[on + 1] == 60 and seq[off + 1] == 60
            seq[on + 1] = 110
            seq[off + 1] = 110
        if no_note_on:
            on = seq.index(0x90)
            assert seq[on + 2] == 110
            # MIDI-style Note On velocity zero is Note Off; the SEQ
            # parser must not ask the bank to resolve this event.
            seq[on + 2] = 0
        files["music.seq"] = bytes(seq)
    for name, data in files.items():
        (directory / name).write_bytes(data)
    return files


@unittest.skipUnless(PROGRAM.is_file(), "build the native host tool first")
class NativeLocalMusicTransitionTests(unittest.TestCase):
    def test_private_banks_and_continuous_pcm(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "bank-a", Path(tmp) / "bank-b"
            originals_a = synth_dir(a, wet=True)
            originals_b = synth_dir(b, bank_b=True, fallback_program=True)
            cmd = [str(PROGRAM), str(a), str(b), "4", "16"]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertNotIn(str(tmp), first.stdout)
            self.assertNotIn(str(tmp), first.stderr)
            self.assertNotIn("pQES", first.stdout)
            self.assertNotIn("pBAV", first.stdout)
            result = json.loads(first.stdout)
            self.assertEqual(result["schema"], "vh_local_music_transition_v1")
            self.assertEqual(result["provenance"], "user-local")
            self.assertFalse(result["music_bytes_exported"])
            self.assertFalse(result["audible_audio_verified"])
            self.assertFalse(result["original_ps1_parity_verified"])
            self.assertEqual(result["sample_rate_hz"], 48000)
            self.assertEqual(result["scenes"], 4)
            self.assertEqual(result["input_frames"], 4 * 16 * 512)
            self.assertGreater(result["output_frames"], result["input_frames"])
            readings = result["measurements"]
            self.assertEqual([x["bank"] for x in readings], ["A", "B", "A", "B"])
            self.assertEqual([x["scene"] for x in readings], [0, 1, 2, 3])
            self.assertEqual([x["reverb_send_seen"] for x in readings],
                             [True, False, True, False])
            self.assertTrue(all(x["resolved_notes"] > 0 for x in readings))
            self.assertTrue(all(x["events"] >= x["resolved_notes"] for x in readings))
            self.assertTrue(all(x["note_requests"] == x["resolved_notes"] +
                                 x["unresolved_notes"] for x in readings))
            self.assertEqual([x["unresolved_notes"] for x in readings],
                             [0, 0, 0, 0])
            self.assertEqual([x["fallback_notes"] for x in readings],
                             [0, readings[1]["resolved_notes"], 0,
                              readings[3]["resolved_notes"]])
            self.assertEqual([x["direct_match_notes"] for x in readings],
                             [readings[0]["resolved_notes"], 0,
                              readings[2]["resolved_notes"], 0])
            self.assertEqual([x["reverb_send_notes"] for x in readings],
                             [readings[0]["resolved_notes"], 0,
                              readings[2]["resolved_notes"], 0])
            self.assertTrue(all(x["zero_gain_notes"] == 0 for x in readings))
            self.assertTrue(all(not x["silent_pcm"] for x in readings))
            self.assertTrue(all(x["nonzero_samples"] > 0 for x in readings))
            self.assertTrue(all(0 < x["peak_pcm16"] <= 32768 for x in readings))
            self.assertTrue(all(x["clipped_samples"] <=
                                x["output_frames"] * 2 for x in readings))
            self.assertEqual(sum(x["output_frames"] for x in readings),
                             result["output_frames"])
            self.assertTrue(all(x["input_frames"] == 8192 for x in readings))
            self.assertEqual(readings[0]["audout_boundary_delta_pcm16"], 0)
            self.assertTrue(all(x["spu_boundary_delta_pcm16"] >= 0
                                for x in readings))
            for folder, original in ((a, originals_a), (b, originals_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, original)

    def test_note_outside_tone_range_counts_as_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            synth_dir(a, out_of_range_note=True)
            synth_dir(b)
            result = subprocess.run(
                [str(PROGRAM), str(a), str(b), "2", "16"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            early, later = report["measurements"]
            self.assertGreater(early["resolved_notes"], 0)
            self.assertEqual(early["fallback_notes"], early["resolved_notes"])
            self.assertEqual(early["direct_match_notes"], 0)
            self.assertEqual(early["unresolved_notes"], 0)
            self.assertEqual(later["fallback_notes"], 0)
            self.assertEqual(later["direct_match_notes"],
                             later["resolved_notes"])
            self.assertNotIn(str(tmp), result.stdout)

    def test_resolved_notes_can_produce_silent_pcm_with_zero_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "mute", Path(tmp) / "audible"
            originals_a = synth_dir(a, mute_master=True)
            originals_b = synth_dir(b)
            cmd = [str(PROGRAM), str(a), str(b), "2", "16"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            muted, audible = report["measurements"]
            self.assertGreater(muted["resolved_notes"], 0)
            self.assertEqual(muted["zero_gain_notes"], muted["resolved_notes"])
            self.assertEqual(muted["unresolved_notes"], 0)
            self.assertTrue(muted["silent_pcm"])
            self.assertEqual(muted["peak_pcm16"], 0)
            self.assertEqual(muted["nonzero_samples"], 0)
            self.assertEqual(muted["clipped_samples"], 0)
            self.assertGreater(audible["resolved_notes"], 0)
            self.assertEqual(audible["zero_gain_notes"], 0)
            self.assertFalse(audible["silent_pcm"])
            self.assertGreater(audible["nonzero_samples"], 0)
            self.assertGreater(audible["peak_pcm16"], 0)
            self.assertLessEqual(audible["peak_pcm16"], 32768)
            self.assertEqual(audible["clipped_samples"], 0)
            self.assertNotIn(str(tmp), result.stdout)
            for folder, expected in ((a, originals_a), (b, originals_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, expected)

    def test_no_note_on_is_not_counted_as_missing_or_muted_instrument(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "note-off-only", Path(tmp) / "notes"
            synth_dir(a, no_note_on=True)
            synth_dir(b)
            result = subprocess.run(
                [str(PROGRAM), str(a), str(b), "2", "16"],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            silent, sounding = json.loads(result.stdout)["measurements"]
            self.assertGreater(silent["events"], 0)
            self.assertEqual(silent["note_requests"], 0)
            self.assertEqual(silent["resolved_notes"], 0)
            self.assertEqual(silent["unresolved_notes"], 0)
            self.assertEqual(silent["zero_gain_notes"], 0)
            self.assertTrue(silent["silent_pcm"])
            self.assertEqual(silent["nonzero_samples"], 0)
            self.assertGreater(sounding["note_requests"], 0)
            self.assertGreater(sounding["resolved_notes"], 0)
            self.assertFalse(sounding["silent_pcm"])

    def test_missing_bank_file_fails_without_partial_json_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            synth_dir(a)
            synth_dir(b)
            (b / "music.vb").unlink()
            result = subprocess.run(
                [str(PROGRAM), str(a), str(b)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 3)
            self.assertFalse(result.stdout)
            self.assertNotIn(str(tmp), result.stderr)
            self.assertIn("Invalid, incomplete", result.stderr)

    def test_invalid_numeric_options_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            for tail in (("1",), ("33",), ("4", "0"), ("4", "4097"),
                         ("4", "abc")):
                result = subprocess.run(
                    [str(PROGRAM), str(a), str(b), *tail],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(result.stdout)


if __name__ == "__main__":
    unittest.main()
