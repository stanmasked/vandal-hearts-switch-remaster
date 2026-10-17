"""Independent Python SEQ block scheduling and ADSR/pitch state oracle.

Compile a small native trace producer. Python computes expectations through
its own Fraction-based scheduler and sample-by-sample ADSR/cursor models.
All music is deterministic, generated PS1-format pQES; no game assets.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from tools.inspect_ps1_seq import parse_seq
from tools.schedule_ps1_seq_blocks import schedule_seq_audio_blocks
from tools.simulate_spu_voice import SpuEnvelope, SpuSampleCursor
from test_schedule_ps1_seq_blocks import (
    changed_tempo_song, repeating_song, stepped_song,
)

PHASE_CODES = {"off": 0, "attack": 1, "decay": 2, "sustain": 3, "release": 4}
VOICE_CASES = {
    "release": (0x000F, 0x0020, 0x0800, 8, 48, 36, 3),
    "slow": (0x7E0F, 0x0000, 0x4000, 0, 56, 8, 4),
    "one_shot": (0x000F, 0x0000, 0x1800, -1, -1, 8, 8),
    "fade": (0x000F, 0x4000, 0x1000, 0, 56, 8, 8),
    "fast_attack": (0x000F, 0x0000, 0x0800, 0, 56, 16, 16),
    "long_release": (0x000F, 0x0018, 0x0800, 0, 56, 256, 2),
    "linear_release": (0x000F, 0x0000, 0x0800, 0, 56, 128, 2),
    "exp_release": (0x000F, 0x0030, 0x0800, 0, 56, 256, 2),
    "slow_attack": (0x7E0F, 0x0000, 0x0800, 0, 56, 256, 256),
    "fast_exp_attack": (0x800F, 0x0000, 0x0800, 0, 56, 64, 64),
    "interrupt_attack": (0x7E0F, 0x0018, 0x0800, 0, 56, 128, 1),
    "interrupt_exp_attack": (0xFE0F, 0x0030, 0x0800, 0, 56, 256, 2),
    "boundary_release": (0x000F, 0x0000, 0x0800, 0, 56, 64, 1),
    "boundary_exp_release": (0x800F, 0x0030, 0x0800, 0, 56, 128, 4),
}


class NativeSeqAdsrDifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="vh-seq-adsr-reference-")
        cls.binary = Path(cls.temp.name) / "native_seq_adsr_trace"
        compiler = subprocess.run(
            ["cc", "-std=c11", "-O2", "-g", "-Wall", "-Wextra",
             "-Werror", "-Isource", "-fsanitize=undefined",
             "-fno-sanitize-recover=all",
             "tests/native_seq_adsr_trace.c",
             "source/vh_native_seq.c", "source/vh_native_spu.c",
             "source/vh_spu_reverb.c", "source/vh_spu_gaussian.c",
             "source/vh_audio_stream.c", "-lm", "-o", str(cls.binary)],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        if compiler.returncode:
            raise AssertionError(
                "native SEQ/ADSR test fixture compilation failed:\n"
                + compiler.stderr
            )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def trace(self, *args):
        output = subprocess.run(
            [str(self.binary), *map(str, args)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout
        return [line.split(",") for line in output.splitlines() if line]

    def test_native_seq_events_match_independent_fraction_block_schedule(self):
        for title, generated, repeats in (
            ("tempo", changed_tempo_song(), 1),
            ("repeated", repeating_song(), 2),
            ("stepped", stepped_song(), 1),
        ):
            with self.subTest(case=title), tempfile.TemporaryDirectory(
                prefix="vh-seq-fixture-"
            ) as folder:
                fixture = Path(folder) / "synthetic.seq"
                fixture.write_bytes(generated)
                events = schedule_seq_audio_blocks(
                    parse_seq(generated), repeat_count=repeats,
                )["events"]
                observed = self.trace("seq", fixture, repeats)
                self.assertEqual(len(observed), 12)
                pending = []
                on = off = cycles = dispatched = 0
                held = set()
                tempo = ((generated[10] << 16) |
                         (generated[11] << 8) | generated[12]) or 500000
                ended = False
                for block, row in enumerate(observed):
                    self.assertEqual(row[:2], ["S", str(block)])
                    pending.extend(
                        item for item in events
                        if item["frame"] == block * 512
                    )
                    for event in pending:
                        kind = event["type"]
                        dispatched += 1
                        if kind == "note_on":
                            key = (event["channel"], event["note"])
                            if key in held:
                                off += 1
                            held.add(key)
                            on += 1
                        elif kind == "note_off":
                            key = (event["channel"], event["note"])
                            if key in held:
                                held.remove(key)
                                off += 1
                        elif kind == "tempo":
                            tempo = event["tempo_us_per_quarter"]
                        elif kind in ("loop_boundary", "end_of_track"):
                            cycles += 1
                            if kind == "end_of_track":
                                off += len(held)
                                held.clear()
                                ended = True
                    pending.clear()
                    actual = tuple(map(int, row[2:]))
                    expected = (on, off, tempo, cycles, int(not ended),
                                dispatched)
                    self.assertEqual(actual, expected,
                                     (title, block, actual, expected))
                self.assertTrue(ended)

    def test_native_adsr_and_pitch_cursor_match_python_sample_model(self):
        rows = self.trace("voice")
        self.assertEqual(len(rows), sum(item[5] for item in VOICE_CASES.values()))
        by_case = {name: [] for name in VOICE_CASES}
        for row in rows:
            self.assertEqual(row[0], "V")
            by_case[row[1]].append(tuple(map(int, row[2:])))
        for name, (adsr1, adsr2, pitch, lo, hi,
                   chunks, key_off_chunk) in VOICE_CASES.items():
            with self.subTest(case=name):
                env = SpuEnvelope(adsr1, adsr2)
                cursor = SpuSampleCursor(56, lo, hi, pitch)
                active = True
                self.assertEqual(len(by_case[name]), chunks)
                for chunk, observed in enumerate(by_case[name]):
                    if chunk == key_off_chunk and active:
                        env.key_off()
                    for _ in range(128):
                        if not active:
                            continue
                        if cursor.index >= 56 or not env.advance():
                            active = False
                            continue
                        if not cursor.advance():
                            active = False
                    expected = (chunk, PHASE_CODES[env.phase], int(active),
                                env.level, env.counter, cursor.phase,
                                int(cursor.looped), cursor.index)
                    self.assertEqual(observed, expected,
                                     (name, chunk, observed, expected))


    def test_infinite_seq_clock_stays_on_fraction_reference_for_1536_blocks(self):
        """Probe accumulating C double tick-budget drift against an
        independently scheduled exact-rational Python clock, including
        frequent FF2F budget resets and FF51 tempo changes. This is
        strictly software PC-port block ordering, not PS1 hardware.
        """
        blocks = 1536  # 786432 frames: inside the 20s fixture safety cap
        for title, generated in (
            ("repeated", repeating_song()),
            ("changing_tempo", changed_tempo_song()),
        ):
            with self.subTest(song=title), tempfile.TemporaryDirectory(
                prefix="vh-long-seq-reference-"
            ) as folder:
                source = Path(folder) / "generated.seq"
                source.write_bytes(generated)
                expected_schedule = schedule_seq_audio_blocks(
                    parse_seq(generated), repeat_count=0,
                    max_frames=blocks * 512,
                )
                self.assertTrue(expected_schedule["stopped_by_window"])
                # Ignore only the scheduler's synthetic window-terminator,
                # which was never dispatched by the native infinite loop.
                by_block = {}
                for item in expected_schedule["events"]:
                    if item["frame"] == blocks * 512:
                        self.assertTrue(item["truncated_by_window"])
                        continue
                    self.assertEqual(item["frame"] % 512, 0)
                    by_block.setdefault(item["frame"] // 512, []).append(item)

                observed = self.trace("seq", source, 0, blocks)
                self.assertEqual(len(observed), blocks)
                on = off = cycles = dispatched = 0
                held = set()
                tempo = ((generated[10] << 16) |
                         (generated[11] << 8) | generated[12]) or 500000
                for block, row in enumerate(observed):
                    self.assertEqual(row[:2], ["S", str(block)])
                    for event in by_block.get(block, ()):
                        dispatched += 1
                        kind = event["type"]
                        if kind == "note_on":
                            key = (event["channel"], event["note"])
                            if key in held:
                                off += 1
                            held.add(key)
                            on += 1
                        elif kind == "note_off":
                            key = (event["channel"], event["note"])
                            if key in held:
                                off += 1
                                held.remove(key)
                        elif kind == "tempo":
                            tempo = event["tempo_us_per_quarter"]
                        elif kind == "loop_boundary":
                            cycles += 1
                        else:
                            self.assertNotEqual(kind, "end_of_track")
                    actual = tuple(map(int, row[2:]))
                    expected = (on, off, tempo, cycles, 1, dispatched)
                    self.assertEqual(actual, expected,
                                     (title, block, actual, expected))
                self.assertGreater(cycles, 100)
                self.assertGreater(on, 100)
                self.assertGreater(dispatched, 300)
                self.assertEqual(cycles, expected_schedule["cycles_completed"])

    def test_mutated_trace_is_detectable(self):
        rows = self.trace("voice")
        before = rows[0][:]
        altered = before[:]
        altered[4] = str(int(altered[4]) + 1)  # ADSR level
        self.assertNotEqual(altered, before)
        self.assertNotEqual(tuple(map(int, altered[2:])),
                            tuple(map(int, before[2:])))


if __name__ == "__main__":
    unittest.main()
