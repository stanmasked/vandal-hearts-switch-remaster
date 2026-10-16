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
              no_note_on=False, program_change_retrigger=False,
              delayed_program_change=False, accelerated_tempo=False):
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
    if program_change_retrigger:
        # Four due note-ons, two for the same pitch (voice retrigger).
        # Program 9 must fall back to program 7; key 110 is outside
        # the only tone's 40..100 range, exercising nearest-key fallback.
        # Delay EOT beyond the first 16 blocks to leave voices active.
        files["music.seq"] = files["music.seq"][:15] + bytes([
            0, 0xC0, 7,
            0, 0x90, 60, 100,
            0, 0x90, 60, 100,
            0, 0xC0, 9,
            0, 0x90, 61, 110,
            0, 0xC0, 7,
            0, 0x90, 110, 110,
            0x81, 0x70, 0x80, 60, 0,
            0, 0x80, 61, 0,
            0, 0x80, 110, 0,
            0, 0xFF, 0x2F,
        ])
    if accelerated_tempo and not delayed_program_change:
        raise ValueError("accelerated tempo requires a delayed-program sequence")
    if delayed_program_change:
        # At 480 PPQN and 500000 us/quarter, each 512-frame block
        # supplies about 11.145 MIDI ticks. At delta 45, the retrigger
        # and cross-program fallback become due in block 5. At total
        # tick 135, the nearest-key fallback and explicit Note Off
        # become due in block 13 (not in any earlier block).
        # EOT is beyond the 16-block observation window.
        lead = bytes([0, 0xC0, 7, 0, 0x90, 60, 100])
        # FF51 in native Sony SEQ contains 3 raw tempo bytes with no
        # extra SMF length. 250000 us/quarter doubles ticks per block,
        # starting with the block AFTER the FF51 event was dispatched.
        tempo_change = (bytes([0, 0xFF, 0x51, 0x03, 0xD0, 0x90])
                        if accelerated_tempo else b"")
        tail = bytes([
            45, 0x90, 60, 100,
            0, 0xC0, 9,
            0, 0x90, 61, 110,
            90, 0xC0, 7,
            0, 0x90, 110, 110,
            0, 0x80, 60, 0,
            0x81, 0x70, 0x80, 61, 0,
            0, 0x80, 110, 0,
            0, 0xFF, 0x2F,
        ])
        files["music.seq"] = files["music.seq"][:15] + lead + tempo_change + tail
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
            self.assertTrue(all(x["cross_program_fallback_notes"] ==
                                x["fallback_notes"] if i % 2 else
                                x["cross_program_fallback_notes"] == 0
                                for i, x in enumerate(readings)))
            self.assertTrue(all(x["out_of_range_fallback_notes"] == 0
                                for x in readings))
            self.assertTrue(all(x["note_offs"] >= 0 for x in readings))
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
            for item in readings:
                for side in ("left", "right"):
                    mean = item[f"mean_pcm16_{side}"]
                    rms = item[f"rms_pcm16_{side}"]
                    self.assertGreater(rms, 0)
                    self.assertLessEqual(abs(mean), rms + 0.002)
                    self.assertLessEqual(rms, item["peak_pcm16"] + 0.002)
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
            self.assertEqual(early["cross_program_fallback_notes"], 0)
            self.assertEqual(early["out_of_range_fallback_notes"],
                             early["resolved_notes"])
            self.assertEqual(early["direct_match_notes"], 0)
            self.assertEqual(early["unresolved_notes"], 0)
            self.assertEqual(later["fallback_notes"], 0)
            self.assertEqual(later["direct_match_notes"],
                             later["resolved_notes"])
            self.assertNotIn(str(tmp), result.stdout)

    def test_program_changes_and_retrigger_route_notes_correctly(self):
        # A switches 7 -> 9 -> 7 within a single SEQ block and
        # retriggers pitch 60 without an explicit Note Off. B remains
        # an independent plain sequence to test the next bank transition.
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "program-events", Path(tmp) / "plain"
            original_a = synth_dir(a, program_change_retrigger=True)
            original_b = synth_dir(b, bank_b=True)
            cmd = [str(PROGRAM), str(a), str(b), "4", "16"]
            first = subprocess.run(cmd, capture_output=True, text=True)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            data = json.loads(first.stdout)
            a0, b0, a1, b1 = data["measurements"]
            for active in (a0, a1):
                self.assertEqual(active["note_requests"], 4)
                self.assertEqual(active["resolved_notes"], 4)
                self.assertEqual(active["unresolved_notes"], 0)
                self.assertEqual(active["note_offs"], 1)
                self.assertEqual(active["direct_match_notes"], 2)
                self.assertEqual(active["cross_program_fallback_notes"], 1)
                self.assertEqual(active["out_of_range_fallback_notes"], 1)
                self.assertEqual(active["fallback_notes"], 2)
                self.assertGreater(active["nonzero_samples"], 0)
                self.assertEqual(active["zero_gain_notes"], 0)
            for plain in (b0, b1):
                self.assertGreater(plain["note_requests"], 0)
                self.assertEqual(plain["fallback_notes"], 0)
                self.assertEqual(plain["cross_program_fallback_notes"], 0)
                self.assertEqual(plain["out_of_range_fallback_notes"], 0)
            self.assertEqual(data["input_frames"], 4 * 16 * 512)
            self.assertEqual(data["output_frames"],
                             (4 * 16 * 512 - 1) * 48000 // 44100 + 1)
            self.assertNotIn(str(tmp), first.stdout)
            for folder, before in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, before)

    def test_delayed_program_change_is_due_only_in_correct_audio_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "delayed-a", Path(tmp) / "ordinary-b"
            saved_a = synth_dir(a, delayed_program_change=True)
            saved_b = synth_dir(b, bank_b=True)
            expected = {
                4: (1, 0, 0, 0, 0, 1),
                8: (3, 1, 1, 0, 5, 5),
                12: (3, 1, 1, 0, 5, 5),
                16: (4, 2, 1, 1, 5, 13),
            }
            for blocks, (notes, offs, cross, outside, first_off,
                         last_note) in expected.items():
                with self.subTest(blocks=blocks):
                    cmd = [str(PROGRAM), str(a), str(b), "2", str(blocks)]
                    first = subprocess.run(cmd, capture_output=True, text=True)
                    second = subprocess.run(cmd, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, second.stdout)
                    report = json.loads(first.stdout)
                    cue, other = report["measurements"]
                    self.assertEqual(cue["note_requests"], notes)
                    self.assertEqual(cue["resolved_notes"], notes)
                    self.assertEqual(cue["unresolved_notes"], 0)
                    self.assertEqual(cue["note_offs"], offs)
                    self.assertEqual(cue["cross_program_fallback_notes"], cross)
                    self.assertEqual(cue["out_of_range_fallback_notes"], outside)
                    self.assertEqual(cue["fallback_notes"], cross + outside)
                    self.assertEqual(cue["first_note_block"], 1)
                    self.assertEqual(cue["last_note_block"], last_note)
                    self.assertEqual(cue["first_note_off_block"], first_off)
                    self.assertEqual(cue["first_cross_program_block"],
                                     5 if cross else 0)
                    self.assertEqual(cue["first_out_of_range_block"],
                                     13 if outside else 0)
                    self.assertGreater(cue["nonzero_samples"], 0)
                    self.assertEqual(other["first_note_block"], 1)
                    self.assertEqual(other["cross_program_fallback_notes"], 0)
                    self.assertEqual(other["out_of_range_fallback_notes"], 0)
                    total_input = 2 * blocks * 512
                    self.assertEqual(report["input_frames"], total_input)
                    self.assertEqual(report["output_frames"],
                                     (total_input - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(tmp), first.stdout)
            for folder, original in ((a, saved_a), (b, saved_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, original)

    def test_native_tempo_change_moves_delayed_events_without_clock_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular, faster, other = (root / "regular", root / "faster",
                                      root / "other")
            original_regular = synth_dir(regular, delayed_program_change=True)
            original_faster = synth_dir(
                faster, delayed_program_change=True, accelerated_tempo=True)
            original_other = synth_dir(other)
            for bank, cross_at, outside_at in ((regular, 5, 13),
                                               (faster, 3, 7)):
                with self.subTest(bank=bank.name):
                    result = subprocess.run(
                        [str(PROGRAM), str(bank), str(other), "2", "16"],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    first, second = json.loads(result.stdout)["measurements"]
                    self.assertEqual(first["note_requests"], 4)
                    self.assertEqual(first["resolved_notes"], 4)
                    self.assertEqual(first["note_offs"], 2)
                    self.assertEqual(first["first_note_block"], 1)
                    self.assertEqual(first["last_note_block"], outside_at)
                    self.assertEqual(first["first_note_off_block"], cross_at)
                    self.assertEqual(first["first_cross_program_block"], cross_at)
                    self.assertEqual(first["first_out_of_range_block"], outside_at)
                    self.assertEqual(first["fallback_notes"], 2)
                    self.assertEqual(first["cross_program_fallback_notes"], 1)
                    self.assertEqual(first["out_of_range_fallback_notes"], 1)
                    self.assertEqual(first["unresolved_notes"], 0)
                    self.assertEqual(second["first_note_block"], 1)
                    self.assertEqual(second["fallback_notes"], 0)
                    self.assertEqual(json.loads(result.stdout)["output_frames"],
                                     (2 * 16 * 512 - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(root), result.stdout)
            for folder, saved in ((regular, original_regular),
                                  (faster, original_faster),
                                  (other, original_other)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, saved)

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
            for side in ("left", "right"):
                self.assertEqual(muted[f"mean_pcm16_{side}"], 0)
                self.assertEqual(muted[f"rms_pcm16_{side}"], 0)
            self.assertGreater(audible["resolved_notes"], 0)
            self.assertEqual(audible["zero_gain_notes"], 0)
            self.assertFalse(audible["silent_pcm"])
            self.assertGreater(audible["nonzero_samples"], 0)
            self.assertGreater(audible["peak_pcm16"], 0)
            self.assertLessEqual(audible["peak_pcm16"], 32768)
            self.assertEqual(audible["clipped_samples"], 0)
            for side in ("left", "right"):
                self.assertGreater(audible[f"rms_pcm16_{side}"], 0)
                self.assertLessEqual(abs(audible[f"mean_pcm16_{side}"]),
                                     audible[f"rms_pcm16_{side}"] + 0.002)
            self.assertNotIn(str(tmp), result.stdout)
            for folder, expected in ((a, originals_a), (b, originals_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, expected)

    def test_wet_tail_survives_transition_into_zero_gain_bank(self):
        # When the A voice fed STUDIO_C, muting every B voice must not
        # erase A's already accumulated reverberation. The B resolver
        # can still report note-ons even though its dry gains are zero.
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "wet-source", Path(tmp) / "muted-target"
            files_a = synth_dir(a, wet=True)
            files_b = synth_dir(b, mute_master=True)
            command = [str(PROGRAM), str(a), str(b), "2", "32"]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            early, later = json.loads(result.stdout)["measurements"]
            self.assertGreater(early["reverb_send_notes"], 0)
            self.assertGreater(early["nonzero_samples"], 0)
            self.assertEqual(later["resolved_notes"], later["zero_gain_notes"])
            self.assertGreater(later["resolved_notes"], 0)
            self.assertEqual(later["reverb_send_notes"], 0)
            self.assertEqual(later["unresolved_notes"], 0)
            self.assertGreater(later["nonzero_samples"], 0)
            self.assertGreater(later["peak_pcm16"], 0)
            self.assertFalse(later["silent_pcm"])
            self.assertNotIn(str(tmp), result.stdout)
            for folder, expected in ((a, files_a), (b, files_b)):
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
            for side in ("left", "right"):
                self.assertEqual(silent[f"mean_pcm16_{side}"], 0)
                self.assertEqual(silent[f"rms_pcm16_{side}"], 0)
            self.assertGreater(sounding["note_requests"], 0)
            self.assertGreater(sounding["resolved_notes"], 0)
            self.assertFalse(sounding["silent_pcm"])

    def test_maximum_scene_count_long_pcm_soak(self):
        # 32 scenes stress the maximum supported transition count. Use
        # 32 blocks/scene (>0.5m source frames) to exercise fractional
        # resampler phase, wet-tail carry and repeatable per-scene stats.
        scenes, blocks = 32, 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "bank-a", root / "bank-b"
            originals_a = synth_dir(a, wet=True)
            originals_b = synth_dir(b, bank_b=True, fallback_program=True)
            cmd = [str(PROGRAM), str(a), str(b),
                   str(scenes), str(blocks)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertNotIn(str(root), first.stdout)
            data = json.loads(first.stdout)
            self.assertEqual(data["scenes"], scenes)
            self.assertEqual(data["blocks_per_scene"], blocks)
            source_frames = scenes * blocks * 512
            self.assertEqual(data["input_frames"], source_frames)
            self.assertEqual(data["output_frames"],
                             (source_frames - 1) * 48000 // 44100 + 1)
            measures = data["measurements"]
            self.assertEqual(len(measures), scenes)
            self.assertEqual(sum(x["output_frames"] for x in measures),
                             data["output_frames"])
            self.assertEqual(sum(x["input_frames"] for x in measures),
                             source_frames)
            self.assertEqual([x["scene"] for x in measures],
                             list(range(scenes)))
            self.assertEqual([x["bank"] for x in measures],
                             ["A", "B"] * (scenes // 2))
            self.assertTrue(all(x["note_requests"] == x["resolved_notes"] +
                                 x["unresolved_notes"] for x in measures))
            self.assertTrue(all(x["resolved_notes"] > 0 for x in measures))
            self.assertTrue(all(x["unresolved_notes"] == 0 for x in measures))
            self.assertTrue(all(x["zero_gain_notes"] == 0 for x in measures))
            self.assertTrue(all(x["nonzero_samples"] > 0 for x in measures))
            self.assertTrue(all(x["events"] >= x["resolved_notes"] for x in measures))
            self.assertEqual([x["reverb_send_seen"] for x in measures],
                             [True, False] * (scenes // 2))
            self.assertEqual([x["fallback_notes"] == x["resolved_notes"]
                              for x in measures], [False, True] * (scenes // 2))
            self.assertEqual([x["direct_match_notes"] ==
                              x["resolved_notes"] for x in measures],
                             [True, False] * (scenes // 2))
            self.assertTrue(all(0 <= x["resampler_boundary_fraction"] < 48000
                                for x in measures))
            for folder, original in ((a, originals_a), (b, originals_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, original)

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

    def test_corrupt_music_files_fail_closed_without_leaking_private_content(self):
        # Every case is a *single* malformed component alongside a
        # complete, valid synthetic second bank. Both entry positions
        # are checked; no partial JSON is allowed on any load failure.
        tone = TONE_OFFSET
        original = make_synthetic_files()
        mutations = {
            "seq_bad_magic": ("music.seq", b"X" + original["music.seq"][1:]),
            "seq_truncated_header": ("music.seq", original["music.seq"][:14]),
            "seq_no_eot": ("music.seq", original["music.seq"][:-2]),
            "seq_invalid_running_status": (
                "music.seq",
                original["music.seq"][:16] + b"\\x7f" +
                original["music.seq"][17:]),
            "seq_empty": ("music.seq", b""),
            "vh_bad_magic": ("music.vh", b"X" + original["music.vh"][1:]),
            "vh_truncated_header": ("music.vh", original["music.vh"][:31]),
            "vh_invalid_range": (
                "music.vh",
                original["music.vh"][:tone + 6] + b"\\x69" +
                original["music.vh"][tone + 7:]),
            "vh_out_of_range_sample": (
                "music.vh",
                original["music.vh"][:tone + 22] + b"\\x02" +
                original["music.vh"][tone + 23:]),
            "vb_invalid_adpcm_filter": (
                "music.vb",
                original["music.vb"][:16] + b"\\x50" +
                original["music.vb"][17:]),
            "vb_invalid_adpcm_flags": (
                "music.vb",
                original["music.vb"][:17] + b"\\x80" +
                original["music.vb"][18:]),
            "vb_truncated": ("music.vb", original["music.vb"][:32]),
            "vb_empty": ("music.vb", b""),
        }
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            a, b = root / "bank-a", root / "bank-b"
            for position in (0, 1):
                for title, (name, altered) in mutations.items():
                    with self.subTest(position=position, corruption=title):
                        for directory in (a, b):
                            directory.mkdir(exist_ok=True)
                            for filename, content in original.items():
                                (directory / filename).write_bytes(content)
                        damaged = (a, b)[position] / name
                        damaged.write_bytes(altered)
                        first = subprocess.run(
                            [str(PROGRAM), str(a), str(b), "2", "4"],
                            capture_output=True, text=True)
                        self.assertEqual(first.returncode, 3, (title, first.stderr))
                        self.assertEqual(first.stdout, "")
                        self.assertIn("Invalid, incomplete", first.stderr)
                        self.assertNotIn(str(root), first.stderr)
                        self.assertNotIn(str(root), first.stdout)
                        self.assertEqual(damaged.read_bytes(), altered)
                        # Loading a damaged component must not touch the
                        # other local bank or any of its original bytes.
                        other = (b, a)[position]
                        self.assertEqual(
                            {f.name: f.read_bytes() for f in other.iterdir()},
                            original)

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
