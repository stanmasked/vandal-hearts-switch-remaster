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
              delayed_program_change=False, accelerated_tempo=False,
              multiple_tempo_loop=False, polyphony_notes=0,
              release_overlap=None, release_waves=None,
              adsr2_release=None):
    directory.mkdir()
    files = make_synthetic_files()
    vh = bytearray(files["music.vh"])
    vb = bytearray(files["music.vb"])
    if wet:
        vh[TONE_OFFSET + 1] = 4  # Valid VAB reverb-send mode.
    if mute_master:
        vh[24] = 0  # Every note resolves, but both output gains are zero.
    if adsr2_release is not None:
        if not 0 <= adsr2_release <= 0xFFFF:
            raise ValueError("ADSR2 release must fit a 16-bit VAB tone")
        # The native importer must propagate these actual VagAtr bits
        # through the normal VAB tone resolver into the SPU voice.
        vh[TONE_OFFSET + 18] = adsr2_release & 0xFF
        vh[TONE_OFFSET + 19] = adsr2_release >> 8
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
    if polyphony_notes:
        if polyphony_notes not in (20, 23):
            raise ValueError("polyphony fixture needs exactly 20 or 23 voices")
        # All notes are simultaneous and distinct (key 40..62) in a
        # single SEQ block, retaining their looped VAB samples.
        # When the 21st note arrives, the 20-voice allocator must
        # round-robin steal. Later Note Offs for keys 40 and 41 are
        # stale and must not release the stolen voice owners.
        melody = bytearray([0, 0xC0, 7])
        for key in range(40, 40 + polyphony_notes):
            melody.extend((0, 0x90, key, 110))
        if polyphony_notes == 23:
            melody.extend((0, 0x80, 40, 0, 0, 0x80, 41, 0))
        melody.extend((0x81, 0x70, 0xFF, 0x2F))
        files["music.seq"] = files["music.seq"][:15] + bytes(melody)
    if release_waves is not None:
        if release_waves not in ("immediate", "after_release"):
            raise ValueError("unsupported release-wave fixture")
        # Four waves, each releasing three *distinct* held voices.
        # Immediate replacement steals 3 Release slots per wave;
        # delayed replacement allows the SPU renderer to retire them
        # to inactive/free slots before the next Note On arrives.
        melody = bytearray((0, 0xC0, 7))
        for key in range(40, 60):
            melody.extend((0, 0x90, key, 110))
        for wave in range(4):
            first_key = 40 + wave * 3
            melody.extend((45, 0x80, first_key, 0))
            for key in range(first_key + 1, first_key + 3):
                melody.extend((0, 0x80, key, 0))
            delta = 0 if release_waves == "immediate" else 45
            for key in range(60 + wave * 3, 63 + wave * 3):
                melody.extend((delta, 0x90, key, 110))
                delta = 0
        # 600 ticks, enough to prevent EOT from stopping any new voice
        # during the 40-block observation window.
        melody.extend((0x84, 0x58, 0xFF, 0x2F))
        files["music.seq"] = files["music.seq"][:15] + bytes(melody)
    if release_overlap is not None:
        if release_overlap not in ("immediate", "after_release"):
            raise ValueError("unsupported release-overlap fixture")
        melody = bytearray((0, 0xC0, 7))
        for key in range(40, 60):
            melody.extend((0, 0x90, key, 110))
        melody.extend((45, 0x80, 40, 0,
                       0, 0x80, 41, 0,
                       0, 0x80, 42, 0))
        # Tick45 = block5. The immediate variant keys on all three
        # while the old slots still occupy the ADSR_RELEASE phase;
        # waiting another 45 ticks allows that release to finish.
        melody.extend((0 if release_overlap=="immediate" else 45,
                       0x90, 60, 110,
                       0, 0x90, 61, 110,
                       0, 0x90, 62, 110,
                       0, 0x80, 40, 0,
                       0, 0x80, 41, 0,
                       0x81, 0x70, 0xFF, 0x2F))
        files["music.seq"] = files["music.seq"][:15] + bytes(melody)
    if multiple_tempo_loop:
        # Two native FF51 events (250000 and 750000 us/quarter) inside
        # each cycle. EOT is 90 ticks after entry. The production SEQ
        # retains its final tempo at EOT until the tick-zero FF51
        # on the next cycle, so event positions must stay deterministic.
        files["music.seq"] = files["music.seq"][:15] + bytes([
            0, 0xC0, 7,
            0, 0x90, 60, 100,
            0, 0xFF, 0x51, 0x03, 0xD0, 0x90,
            30, 0x90, 61, 110,
            0, 0xFF, 0x51, 0x0B, 0x71, 0xB0,
            30, 0x90, 62, 110,
            30, 0x80, 60, 0,
            0, 0x80, 61, 0,
            0, 0x80, 62, 0,
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

    def test_two_ff51_tempos_and_repeated_end_of_track_cycles(self):
        # Independently calculated from 480 PPQN / 44.1-kHz
        # 512-frame budgets. Tempo updates are applied to *later*
        # blocks, and EOT resets tick_budget while retaining tempo.
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "loop-a", Path(tmp) / "ordinary-b"
            original_a = synth_dir(a, multiple_tempo_loop=True, wet=True)
            original_b = synth_dir(b)
            expected = {
                # blocks: notes, completed cycles, last note,
                # observed end-of-block tempo transitions, final tempo
                4: (2, 0, 2, 2, 750000),
                8: (3, 0, 6, 2, 750000),
                16: (6, 1, 15, 4, 750000),
                32: (11, 3, 30, 8, 750000),
            }
            for blocks, (notes, cycles, last_note, transitions,
                         ending_tempo) in expected.items():
                with self.subTest(blocks=blocks):
                    cmd = [str(PROGRAM), str(a), str(b), "2", str(blocks)]
                    first = subprocess.run(cmd, capture_output=True, text=True)
                    repeat = subprocess.run(cmd, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, repeat.stdout)
                    report = json.loads(first.stdout)
                    a_scene, b_scene = report["measurements"]
                    self.assertEqual(a_scene["note_requests"], notes)
                    self.assertEqual(a_scene["resolved_notes"], notes)
                    self.assertEqual(a_scene["unresolved_notes"], 0)
                    self.assertEqual(a_scene["fallback_notes"], 0)
                    self.assertEqual(a_scene["first_note_block"], 1)
                    self.assertEqual(a_scene["last_note_block"], last_note)
                    self.assertEqual(a_scene["cycles_completed"], cycles)
                    self.assertEqual(a_scene["first_cycle_block"],
                                     10 if cycles else 0)
                    self.assertEqual(a_scene["last_cycle_block"],
                                     (0, 10, 19, 28)[cycles])
                    self.assertEqual(a_scene["observed_tempo_changes"],
                                     transitions)
                    self.assertEqual(a_scene["first_tempo_change_block"], 1)
                    self.assertEqual(a_scene["last_tempo_change_block"],
                                     {4: 2, 8: 2, 16: 12, 32: 30}[blocks])
                    self.assertEqual(a_scene["final_tempo_us_per_quarter"],
                                     ending_tempo)
                    self.assertGreater(a_scene["nonzero_samples"], 0)
                    self.assertEqual(b_scene["first_note_block"], 1)
                    self.assertEqual(b_scene["observed_tempo_changes"], 0)
                    self.assertEqual(b_scene["cycles_completed"], 0)
                    self.assertEqual(b_scene["final_tempo_us_per_quarter"],
                                     500000)
                    total = 2 * blocks * 512
                    self.assertEqual(report["input_frames"], total)
                    self.assertEqual(report["output_frames"],
                                     (total - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(tmp), first.stdout)
            for folder, saved in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, saved)

    def test_multi_tempo_loop_state_resets_for_32_alternating_scenes(self):
        # Each A scene completes three EOT cycles and retains its own
        # two-tempo timeline. Every B scene starts with its independent
        # initial tempo despite STUDIO_C tails surviving both switches.
        scenes, blocks = 32, 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "two-tempos", root / "fallback-b"
            original_a = synth_dir(a, multiple_tempo_loop=True, wet=True)
            original_b = synth_dir(b, bank_b=True, fallback_program=True)
            cmd = [str(PROGRAM), str(a), str(b), str(scenes), str(blocks)]
            run = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(run.stdout)
            measures = report["measurements"]
            self.assertEqual(len(measures), scenes)
            self.assertEqual([m["bank"] for m in measures],
                             ["A", "B"] * (scenes // 2))
            for i, measure in enumerate(measures):
                self.assertEqual(measure["scene"], i)
                self.assertEqual(measure["unresolved_notes"], 0)
                self.assertGreater(measure["nonzero_samples"], 0)
                self.assertEqual(measure["input_frames"], blocks * 512)
                if i % 2 == 0:
                    self.assertEqual(measure["note_requests"], 11)
                    self.assertEqual(measure["cycles_completed"], 3)
                    self.assertEqual(measure["first_cycle_block"], 10)
                    self.assertEqual(measure["last_cycle_block"], 28)
                    self.assertEqual(measure["observed_tempo_changes"], 8)
                    self.assertEqual(measure["first_tempo_change_block"], 1)
                    self.assertEqual(measure["last_tempo_change_block"], 30)
                    self.assertEqual(measure["final_tempo_us_per_quarter"],
                                     750000)
                    self.assertEqual(measure["fallback_notes"], 0)
                    self.assertTrue(measure["reverb_send_seen"])
                else:
                    self.assertEqual(measure["note_requests"], 1)
                    self.assertEqual(measure["cycles_completed"], 0)
                    self.assertEqual(measure["observed_tempo_changes"], 0)
                    self.assertEqual(measure["final_tempo_us_per_quarter"],
                                     500000)
                    self.assertEqual(measure["cross_program_fallback_notes"],
                                     measure["resolved_notes"])
                    self.assertEqual(measure["out_of_range_fallback_notes"],
                                     0)
                    self.assertFalse(measure["reverb_send_seen"])
            total = scenes * blocks * 512
            self.assertEqual(report["input_frames"], total)
            self.assertEqual(report["output_frames"],
                             (total - 1) * 48000 // 44100 + 1)
            self.assertEqual(sum(x["output_frames"] for x in measures),
                             report["output_frames"])
            self.assertNotIn(str(tmp), run.stdout)
            for folder, original in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {p.name: p.read_bytes() for p in folder.iterdir()}, original)

    def test_twenty_voice_capacity_and_saturated_allocator_reuse(self):
        # Capacity without stealing (20), then three excess notes (23).
        # All note-ons occur at tick zero in the same SEQ audio block,
        # so end-of-block active counts alone would miss the pressure.
        # The second bank is a plain independent cue.
        for voices, expected_saturated in ((20, 0), (23, 3)):
            with self.subTest(voices=voices):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    a, b = root / "polyphonic", root / "ordinary"
                    originals_a = synth_dir(a, polyphony_notes=voices)
                    originals_b = synth_dir(b, bank_b=True)
                    cmd = [str(PROGRAM), str(a), str(b), "4", "4"]
                    first = subprocess.run(cmd, capture_output=True, text=True)
                    again = subprocess.run(cmd, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, again.stdout)
                    metrics = json.loads(first.stdout)["measurements"]
                    for high in (metrics[0], metrics[2]):
                        self.assertEqual(high["note_requests"], voices)
                        self.assertEqual(high["resolved_notes"], voices)
                        self.assertEqual(high["unresolved_notes"], 0)
                        self.assertEqual(high["fallback_notes"], 0)
                        self.assertEqual(high["peak_active_voices"], 20)
                        self.assertEqual(high["saturated_note_requests"],
                                         expected_saturated)
                        self.assertEqual(
                            high["first_saturated_note_block"],
                            1 if expected_saturated else 0)
                        self.assertEqual(high["first_note_block"], 1)
                        self.assertEqual(high["last_note_block"], 1)
                        self.assertEqual(high["note_offs"], 0)
                        self.assertGreater(high["nonzero_samples"], 0)
                    for low in (metrics[1], metrics[3]):
                        self.assertEqual(low["note_requests"], 1)
                        self.assertEqual(low["saturated_note_requests"], 0)
                        self.assertEqual(low["first_saturated_note_block"], 0)
                        self.assertEqual(low["peak_active_voices"], 1)
                    result = json.loads(first.stdout)
                    total_input = 4 * 4 * 512
                    self.assertEqual(result["input_frames"], total_input)
                    self.assertEqual(result["output_frames"],
                                     (total_input - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(root), first.stdout)
                    for folder, before in ((a, originals_a), (b, originals_b)):
                        self.assertEqual(
                            {p.name: p.read_bytes() for p in folder.iterdir()},
                            before)

    def test_vab_adsr2_release_rates_drive_actual_spu_retirement(self):
        # This is an end-to-end importer/resolver/sequencer/SPU test.
        # A synthetic pQES note lasts to tick 240 (block 22); each
        # release code is loaded from the VAB tone table, not injected
        # directly into the SPU. EOT at tick 480 is beyond block 42.
        cases = (
            (0x0000, 22),   # fast linear
            (0x0005, 22),   # 64 PCM frames
            (0x000A, 25),   # 2048 frames = 4 render blocks
            (0x0020, 22),   # fast exponential
            (0x0025, 22),   # 496 frames
            (0x002A, 39),   # 8842 frames = 18 render blocks
            (0x001F, 0),    # no release level step (held)
        )
        for rate, retirement_block in cases:
            with self.subTest(adsr2=hex(rate)):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    a, b = root / "release-variant", root / "control"
                    original_a = synth_dir(a, adsr2_release=rate)
                    original_b = synth_dir(b, bank_b=True)
                    cmd = [str(PROGRAM), str(a), str(b), "2", "42"]
                    first = subprocess.run(cmd, capture_output=True, text=True)
                    again = subprocess.run(cmd, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, again.stdout)
                    report = json.loads(first.stdout)
                    target, control = report["measurements"]
                    self.assertEqual(target["note_requests"], 1)
                    self.assertEqual(target["resolved_notes"], 1)
                    self.assertEqual(target["note_offs"], 1)
                    self.assertEqual(target["first_note_off_block"], 22)
                    self.assertEqual(target["unresolved_notes"], 0)
                    self.assertEqual(target["fallback_notes"], 0)
                    self.assertEqual(target["peak_active_voices"], 1)
                    self.assertEqual(target["adsr_release_slot_retirements"],
                                     1 if retirement_block else 0)
                    self.assertEqual(target["first_release_retirement_block"],
                                     retirement_block)
                    self.assertEqual(target["last_release_retirement_block"],
                                     retirement_block)
                    self.assertGreaterEqual(
                        target["peak_releasing_voices_before_render"], 1)
                    self.assertEqual(control["adsr_release_slot_retirements"], 1)
                    self.assertEqual(control["first_release_retirement_block"], 22)
                    self.assertEqual(control["last_release_retirement_block"], 22)
                    self.assertEqual(control["note_requests"], 1)
                    self.assertEqual(control["saturated_note_requests"], 0)
                    self.assertEqual(report["input_frames"], 2 * 42 * 512)
                    self.assertEqual(report["output_frames"],
                                     (2 * 42 * 512 - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(root), first.stdout)
                    self.assertNotIn(str(root), first.stderr)
                    for directory, original in ((a, original_a), (b, original_b)):
                        self.assertEqual(
                            {f.name: f.read_bytes() for f in directory.iterdir()},
                            original)

    def test_bank_switch_clears_borrowed_slow_release_pcm_without_wiping_reverb(self):
        # 16 scenes / 15 boundaries: A sends STUDIO_C and has a slow
        # exponential ADSR2 release still active at block 32. B has
        # zero dry gain and the default fast release, so its rendered
        # PCM can only reflect the previous wet history.
        scenes, blocks = 16, 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "wet-slow-release", root / "muted-fast-release"
            original_a = synth_dir(a, wet=True, adsr2_release=0x002A)
            original_b = synth_dir(b, mute_master=True)
            cmd = [str(PROGRAM), str(a), str(b), str(scenes), str(blocks)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            repeat = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, repeat.stdout)
            report = json.loads(first.stdout)
            measures = report["measurements"]
            self.assertEqual(len(measures), scenes)
            self.assertEqual([m["bank"] for m in measures],
                             ["A", "B"] * (scenes // 2))
            for index, cue in enumerate(measures):
                self.assertEqual(cue["scene"], index)
                self.assertEqual(cue["resolved_notes"], 1)
                self.assertEqual(cue["note_offs"], 1)
                self.assertEqual(cue["first_note_off_block"], 22)
                self.assertEqual(cue["unresolved_notes"], 0)
                self.assertEqual(cue["fallback_notes"], 0)
                self.assertEqual(cue["input_frames"], blocks * 512)
                self.assertEqual(cue["adsr_release_slot_retirements"],
                                 0 if index % 2 == 0 else 1)
                self.assertEqual(cue["prior_bank_active_voices"],
                                 1 if index % 2 else 0)
                self.assertEqual(cue["prior_bank_release_voices"],
                                 1 if index % 2 else 0)
                # Renderer retires a fast-Release voice by clearing
                # its active flag but leaves its borrowed PCM pointer
                # intact until the next bank reset. This is harmless
                # while the source bank remains loaded; switch_scene
                # must clear even these inactive stale pointers.
                self.assertEqual(cue["prior_bank_pcm_references"],
                                 1 if index else 0)
                self.assertEqual(cue["prior_bank_voices_cleared"], index != 0)
                self.assertEqual(cue["reverb_history_preserved_on_switch"],
                                 index != 0)
                if index % 2 == 0:
                    self.assertEqual(cue["zero_gain_notes"], 0)
                    self.assertTrue(cue["reverb_send_seen"])
                    self.assertGreater(cue["nonzero_samples"], 0)
                    self.assertEqual(cue["first_release_retirement_block"], 0)
                else:
                    self.assertEqual(cue["zero_gain_notes"], 1)
                    self.assertFalse(cue["reverb_send_seen"])
                    self.assertGreater(cue["nonzero_samples"], 0)
                    self.assertEqual(cue["first_release_retirement_block"], 22)
            total = scenes * blocks * 512
            self.assertEqual(report["input_frames"], total)
            self.assertEqual(report["output_frames"],
                             (total - 1) * 48000 // 44100 + 1)
            self.assertEqual(sum(x["output_frames"] for x in measures),
                             report["output_frames"])
            self.assertNotIn(str(root), first.stdout)
            self.assertNotIn(str(root), first.stderr)
            for folder, original in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {f.name: f.read_bytes() for f in folder.iterdir()}, original)

    def test_switch_from_nonretiring_release_to_note_off_only_bank_keeps_wet_tail(self):
        # Release shift 31 never reaches ADSR Off in the software model.
        # B contains no positive-velocity notes at all, so its nonzero
        # PCM (if any) must come from A's retained STUDIO_C history.
        # The two B->A switches must not inherit A's held PCM pointer.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "held-wet-release", root / "silent-seq"
            original_a = synth_dir(a, wet=True, adsr2_release=0x001F)
            original_b = synth_dir(b, no_note_on=True)
            command = [str(PROGRAM), str(a), str(b), "4", "32"]
            first = subprocess.run(command, capture_output=True, text=True)
            repeat = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, repeat.stdout)
            report = json.loads(first.stdout)
            metrics = report["measurements"]
            self.assertEqual([m["bank"] for m in metrics], ["A", "B", "A", "B"])
            for i, m in enumerate(metrics):
                self.assertEqual(m["scene"], i)
                self.assertEqual(m["adsr_release_slot_retirements"], 0)
                self.assertEqual(m["unresolved_notes"], 0)
                self.assertEqual(m["prior_bank_voices_cleared"], i > 0)
                self.assertEqual(m["reverb_history_preserved_on_switch"], i > 0)
                self.assertEqual(m["prior_bank_active_voices"],
                                 1 if i % 2 else 0)
                self.assertEqual(m["prior_bank_release_voices"],
                                 1 if i % 2 else 0)
                self.assertEqual(m["prior_bank_pcm_references"],
                                 1 if i % 2 else 0)
                if i % 2 == 0:
                    self.assertEqual(m["note_requests"], 1)
                    self.assertEqual(m["resolved_notes"], 1)
                    self.assertEqual(m["note_offs"], 1)
                    self.assertEqual(m["first_note_off_block"], 22)
                    self.assertTrue(m["reverb_send_seen"])
                    self.assertEqual(m["peak_releasing_voices_before_render"], 1)
                else:
                    self.assertEqual(m["note_requests"], 0)
                    self.assertEqual(m["resolved_notes"], 0)
                    self.assertEqual(m["note_offs"], 0)
                    self.assertEqual(m["peak_active_voices"], 0)
                    self.assertFalse(m["reverb_send_seen"])
                    self.assertGreater(m["nonzero_samples"], 0)
            n = 4 * 32 * 512
            self.assertEqual(report["input_frames"], n)
            self.assertEqual(report["output_frames"],
                             (n - 1) * 48000 // 44100 + 1)
            self.assertNotIn(str(root), first.stdout)
            self.assertNotIn(str(root), first.stderr)
            for folder, old in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {f.name: f.read_bytes() for f in folder.iterdir()}, old)

    def test_repeated_release_waves_retire_or_steal_slots(self):
        # Long synthetic high-polyphony stress: start 20 voices, then
        # issue 4 waves of 3 Note Offs followed by 3 replacements.
        # Distinguish voices *actually* becoming inactive in SPU render
        # from release-phase voices overwritten before rendering.
        for kind in ("immediate", "after_release"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    a, b = root / "release-waves", root / "independent-bank"
                    original_a = synth_dir(a, release_waves=kind, wet=True)
                    original_b = synth_dir(b, bank_b=True)
                    cmd = [str(PROGRAM), str(a), str(b), "4", "40"]
                    first = subprocess.run(cmd, capture_output=True, text=True)
                    repeat = subprocess.run(cmd, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, repeat.stdout)
                    report = json.loads(first.stdout)
                    stages = report["measurements"]
                    self.assertEqual([m["bank"] for m in stages],
                                     ["A", "B", "A", "B"])
                    for scene in (stages[0], stages[2]):
                        self.assertEqual(scene["note_requests"], 32)
                        self.assertEqual(scene["resolved_notes"], 32)
                        self.assertEqual(scene["note_offs"], 12)
                        self.assertEqual(scene["unresolved_notes"], 0)
                        self.assertEqual(scene["fallback_notes"], 0)
                        self.assertEqual(scene["cycles_completed"], 0)
                        self.assertEqual(scene["peak_active_voices"], 20)
                        self.assertEqual(scene["first_note_block"], 1)
                        self.assertGreater(scene["nonzero_samples"], 0)
                        if kind == "immediate":
                            self.assertEqual(scene["last_note_block"], 17)
                            self.assertEqual(scene["saturated_note_requests"], 12)
                            self.assertEqual(scene["notes_while_release_active"], 12)
                            self.assertEqual(scene["saturated_with_release_requests"], 12)
                            self.assertEqual(scene["first_saturated_note_block"], 5)
                            self.assertEqual(scene["first_release_overlap_block"], 5)
                            self.assertEqual(scene["adsr_release_slot_retirements"], 0)
                            self.assertEqual(scene["first_release_retirement_block"], 0)
                            self.assertEqual(scene["peak_releasing_voices_before_render"], 0)
                        else:
                            self.assertEqual(scene["last_note_block"], 33)
                            self.assertEqual(scene["saturated_note_requests"], 0)
                            self.assertEqual(scene["notes_while_release_active"], 0)
                            self.assertEqual(scene["saturated_with_release_requests"], 0)
                            self.assertEqual(scene["adsr_release_slot_retirements"], 12)
                            self.assertEqual(scene["first_release_retirement_block"], 5)
                            self.assertEqual(scene["last_release_retirement_block"], 29)
                            self.assertEqual(scene["peak_releasing_voices_before_render"], 3)
                    for scene in (stages[1], stages[3]):
                        self.assertEqual(scene["note_requests"], 1)
                        self.assertEqual(scene["saturated_note_requests"], 0)
                        self.assertEqual(scene["notes_while_release_active"], 0)
                        self.assertEqual(scene["peak_active_voices"], 1)
                    input_frames = 4 * 40 * 512
                    self.assertEqual(report["input_frames"], input_frames)
                    self.assertEqual(report["output_frames"],
                                     (input_frames - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(root), first.stdout)
                    for directory, old_files in ((a, original_a), (b, original_b)):
                        self.assertEqual(
                            {f.name: f.read_bytes() for f in directory.iterdir()},
                            old_files)

    def test_release_slot_retirement_counters_reset_across_16_scenes(self):
        # Alternate a bank that waits for natural ADSR retirement with a
        # bank that steals the Release slots before rendering. This
        # forces 15 transitions through two high-polyphony SEQ sources
        # and proves per-scene counters cannot carry over.
        scenes, blocks = 16, 40
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, b = root / "wait-for-release", root / "steal-on-release"
            original_a = synth_dir(a, release_waves="after_release", wet=True)
            original_b = synth_dir(b, release_waves="immediate", bank_b=True)
            command = [str(PROGRAM), str(a), str(b),
                       str(scenes), str(blocks)]
            first = subprocess.run(command, capture_output=True, text=True)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            report = json.loads(first.stdout)
            stages = report["measurements"]
            self.assertEqual([m["bank"] for m in stages],
                             ["A", "B"] * (scenes // 2))
            for i, cue in enumerate(stages):
                self.assertEqual(cue["scene"], i)
                self.assertEqual(cue["input_frames"], blocks * 512)
                self.assertEqual(cue["note_requests"], 32)
                self.assertEqual(cue["resolved_notes"], 32)
                self.assertEqual(cue["note_offs"], 12)
                self.assertEqual(cue["fallback_notes"], 0)
                self.assertEqual(cue["unresolved_notes"], 0)
                self.assertEqual(cue["peak_active_voices"], 20)
                self.assertGreater(cue["nonzero_samples"], 0)
                self.assertGreater(cue["peak_pcm16"], 0)
                if i % 2 == 0:
                    self.assertEqual(cue["saturated_note_requests"], 0)
                    self.assertEqual(cue["notes_while_release_active"], 0)
                    self.assertEqual(cue["adsr_release_slot_retirements"], 12)
                    self.assertEqual(cue["first_release_retirement_block"], 5)
                    self.assertEqual(cue["last_release_retirement_block"], 29)
                    self.assertTrue(cue["reverb_send_seen"])
                else:
                    self.assertEqual(cue["saturated_note_requests"], 12)
                    self.assertEqual(cue["notes_while_release_active"], 12)
                    self.assertEqual(cue["saturated_with_release_requests"], 12)
                    self.assertEqual(cue["adsr_release_slot_retirements"], 0)
                    self.assertEqual(cue["first_release_retirement_block"], 0)
                    self.assertEqual(cue["first_saturated_note_block"], 5)
                    self.assertFalse(cue["reverb_send_seen"])
            input_frames = scenes * blocks * 512
            self.assertEqual(report["input_frames"], input_frames)
            self.assertEqual(report["output_frames"],
                             (input_frames - 1) * 48000 // 44100 + 1)
            self.assertEqual(sum(x["output_frames"] for x in stages),
                             report["output_frames"])
            self.assertNotIn(str(root), first.stdout)
            for directory, before in ((a, original_a), (b, original_b)):
                self.assertEqual(
                    {f.name: f.read_bytes() for f in directory.iterdir()}, before)

    def test_releasing_voices_are_occupied_until_adsr_finishes(self):
        # Both sequences start 20 held notes, then NoteOff 3 of them
        # at tick45 (block5). The immediate cue keys on three new
        # notes in that same block: released slots remain occupied.
        # The delayed cue keys on at tick90 (block9), after their
        # native ADSR release has reached zero and become reusable.
        for kind, expected_saturated, first_note_block in (
                ("immediate", 3, 5), ("after_release", 0, 0)):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    a, b = root / "release-a", root / "plain-b"
                    original_a = synth_dir(a, release_overlap=kind)
                    original_b = synth_dir(b, bank_b=True)
                    command = [str(PROGRAM), str(a), str(b), "4", "12"]
                    first = subprocess.run(command, capture_output=True, text=True)
                    again = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(first.returncode, 0, first.stderr)
                    self.assertEqual(first.stdout, again.stdout)
                    report = json.loads(first.stdout)
                    for cue in (report["measurements"][0],
                                report["measurements"][2]):
                        self.assertEqual(cue["note_requests"], 23)
                        self.assertEqual(cue["resolved_notes"], 23)
                        self.assertEqual(cue["note_offs"], 3)
                        self.assertEqual(cue["peak_active_voices"], 20)
                        self.assertEqual(cue["unresolved_notes"], 0)
                        self.assertEqual(cue["fallback_notes"], 0)
                        self.assertEqual(cue["saturated_note_requests"],
                                         expected_saturated)
                        self.assertEqual(cue["first_saturated_note_block"],
                                         first_note_block)
                        self.assertEqual(cue["notes_while_release_active"],
                                         3 if kind == "immediate" else 0)
                        self.assertEqual(cue["saturated_with_release_requests"],
                                         expected_saturated)
                        self.assertEqual(cue["peak_releasing_voices"],
                                         3 if kind == "immediate" else 0)
                        self.assertEqual(cue["first_release_overlap_block"],
                                         first_note_block)
                        self.assertEqual(cue["first_note_block"], 1)
                        self.assertEqual(cue["last_note_block"],
                                         5 if kind == "immediate" else 9)
                        self.assertEqual(cue["first_note_off_block"], 5)
                        self.assertGreater(cue["nonzero_samples"], 0)
                    for cue in (report["measurements"][1],
                                report["measurements"][3]):
                        self.assertEqual(cue["note_requests"], 1)
                        self.assertEqual(cue["saturated_note_requests"], 0)
                        self.assertEqual(cue["notes_while_release_active"], 0)
                        self.assertEqual(cue["peak_releasing_voices"], 0)
                    frames = 4 * 12 * 512
                    self.assertEqual(report["output_frames"],
                                     (frames - 1) * 48000 // 44100 + 1)
                    self.assertNotIn(str(root), first.stdout)
                    for folder, original in ((a, original_a), (b, original_b)):
                        self.assertEqual(
                            {f.name: f.read_bytes() for f in folder.iterdir()},
                            original)

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
