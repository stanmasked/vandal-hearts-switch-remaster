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
    changed_tempo_song, repeating_song, stepped_song, vlq,
)
from test_seq_to_chord_schedule import hdr

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
    "immediate_key_off": (0x7E0F, 0x0000, 0x0800, 0, 56, 32, 0),
    "short_key_off": (0x000F, 0x0020, 0x0800, 0, 56, 32, 1),
}


def rapid_tempo_note_boundary_song():
    """All timing data is synthetic; FF51 and note edges straddle nearby
    ticks (10/11/12 etc.). Loop seams retain tempo but reset tick budget.
    Deliberately mix 250/300/400/500 ms quarters across repeating cycles.
    """
    events = [
        (0, bytes([0x90, 60, 100])),
        (10, bytes([0xFF, 0x51, 0x03, 0xD0, 0x90])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 110])),
        (10, bytes([0xFF, 0x51, 0x04, 0x93, 0xE0])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 100])),
        (8, bytes([0xFF, 0x51, 0x07, 0xA1, 0x20])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 110])),
        (12, bytes([0xFF, 0x51, 0x06, 0x1A, 0x80])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 100])),
        (10, bytes([0xFF, 0x51, 0x03, 0xD0, 0x90])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 110])),
        (8, bytes([0xFF, 0x51, 0x07, 0xA1, 0x20])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 100])),
        (10, bytes([0xFF, 0x51, 0x04, 0x93, 0xE0])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 110])),
        (12, bytes([0xFF, 0x51, 0x06, 0x1A, 0x80])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0x90, 60, 100])),
        (16, bytes([0xFF, 0x51, 0x07, 0xA1, 0x20])),
        (1, bytes([0x80, 60, 0])),
        (1, bytes([0xFF, 0x2F])),
    ]
    return hdr() + b"".join(vlq(delta) + payload for delta, payload in events)


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
            ("rapid_tempo_note_edges", rapid_tempo_note_boundary_song()),
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
                if title == "rapid_tempo_note_edges":
                    self.assertGreater(on, 500)
                    tempo_events = [
                        item for item in expected_schedule["events"]
                        if item["type"] == "tempo"
                    ]
                    self.assertGreater(len(tempo_events), 500)
                    self.assertEqual(
                        {item["tempo_us_per_quarter"]
                         for item in tempo_events},
                        {250000, 300000, 400000, 500000},
                    )
                self.assertEqual(cycles, expected_schedule["cycles_completed"])

    def test_paced_ring_against_exact_fraction_event_clock(self):
        """A full 4096-frame FIFO, repeated blocked writes and underruns
        must NEVER advance SEQ time without an accepted 512-frame page.
        Calculate expected event dispatch independently using Fraction,
        and consumer queue accounting using integer frame counts.
        """
        requests = (0, 0, 32, 256, 0, 0, 0, 4096, 1, 511, 0, 64)
        attempts = 1536
        data = rapid_tempo_note_boundary_song()
        with tempfile.TemporaryDirectory(prefix="vh-paced-seq-reference-") as tmp:
            fixture = Path(tmp) / "paced.seq"
            fixture.write_bytes(data)
            rows = self.trace("paced", fixture, attempts)
        self.assertEqual(len(rows), attempts)
        produced = sum(int(row[2]) == 512 for row in rows)
        self.assertGreater(produced, 500)
        self.assertLess(produced, attempts)
        scheduled = schedule_seq_audio_blocks(
            parse_seq(data), repeat_count=0, max_frames=produced * 512,
        )
        self.assertTrue(scheduled["stopped_by_window"])
        by_block = {}
        for event in scheduled["events"]:
            if event["frame"] == produced * 512:
                self.assertTrue(event["truncated_by_window"])
                continue
            self.assertEqual(event["frame"] % 512, 0)
            by_block.setdefault(event["frame"] // 512, []).append(event)

        queued = 4096
        missing = 0
        blocks = on = off = cycles = dispatched = 0
        held = set()
        tempo = ((data[10] << 16) | (data[11] << 8) | data[12]) or 500000
        stalls = underruns = 0
        seen_tempos = {tempo}
        for attempt, row in enumerate(rows):
            self.assertEqual(row[0], "P")
            wrote = 512 if queued <= 4096 - 512 else 0
            if wrote:
                for event in by_block.get(blocks, ()):
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
                            held.remove(key)
                            off += 1
                    elif kind == "tempo":
                        tempo = event["tempo_us_per_quarter"]
                        seen_tempos.add(tempo)
                    elif kind == "loop_boundary":
                        cycles += 1
                    else:
                        self.fail(f"unexpected oracle event {kind}")
                blocks += 1
                queued += 512
            else:
                stalls += 1
            request = requests[attempt % len(requests)]
            taken = min(queued, request)
            queued -= taken
            missing += request - taken
            if taken < request:
                underruns += 1
            expected = (
                attempt, wrote, blocks, on, off, tempo, cycles, 1,
                dispatched, queued, taken, missing, 0,
            )
            actual = tuple(map(int, row[1:]))
            self.assertEqual(
                actual, expected,
                f"paced iteration {attempt}: {actual} != {expected}",
            )
        self.assertEqual(blocks, produced)
        self.assertEqual(cycles, scheduled["cycles_completed"])
        self.assertGreater(cycles, 20)
        self.assertGreater(stalls, 100)
        self.assertGreater(underruns, 10)
        self.assertGreater(on, 100)
        self.assertGreater(off, 100)
        self.assertEqual(seen_tempos, {250000, 300000, 400000, 500000})


    def test_paced_scene_switch_against_independent_fraction_epochs(self):
        """Scene changes must reset event time and voice ownership, but
        must NOT flush pending PCM or the STUDIO_C wet processor.
        Python independently reconstructs the full-ring consumer timeline,
        and generates a separate Fraction-based schedule for each epoch.
        """
        attempts = 1536
        switch_points = (241, 503, 761, 1019, 1277)
        bounds = (0, *switch_points, attempts)
        requests = (0, 0, 32, 256, 0, 0, 0, 4096, 1, 511, 0, 64)
        songs = (rapid_tempo_note_boundary_song(), changed_tempo_song())
        with tempfile.TemporaryDirectory(prefix="vh-paced-scenes-") as tmp:
            first = Path(tmp) / "rapid.seq"
            second = Path(tmp) / "tempo.seq"
            first.write_bytes(songs[0])
            second.write_bytes(songs[1])
            rows = self.trace("paced-switch", first, second, attempts)

        self.assertEqual(len(rows), attempts)
        by_epoch = []
        for epoch, (start, end) in enumerate(zip(bounds, bounds[1:])):
            segment = rows[start:end]
            self.assertEqual(len(segment), end - start)
            accepted = sum(int(row[3]) == 512 for row in segment)
            self.assertGreater(accepted, 0)
            schedule = schedule_seq_audio_blocks(
                parse_seq(songs[epoch % 2]), repeat_count=0,
                max_frames=accepted * 512,
            )
            self.assertTrue(schedule["stopped_by_window"])
            events = {}
            for item in schedule["events"]:
                if item["frame"] == accepted * 512:
                    self.assertTrue(item["truncated_by_window"])
                    continue
                events.setdefault(item["frame"] // 512, []).append(item)
            by_epoch.append((events, schedule["cycles_completed"]))

        queued, missing = 4096, 0
        blocks = on = off = cycles = dispatched = 0
        held = set()
        epoch = 0
        tempo = ((songs[0][10] << 16) |
                 (songs[0][11] << 8) | songs[0][12]) or 500000
        seen = {tempo}
        stalls = underruns = switched_while_queued = 0
        total_on = total_off = 0
        for attempt, row in enumerate(rows):
            self.assertEqual(row[0], "Q")
            if attempt in switch_points:
                if queued:
                    switched_while_queued += 1
                epoch += 1
                blocks = on = off = cycles = dispatched = 0
                held.clear()
                data = songs[epoch % 2]
                tempo = ((data[10] << 16) |
                         (data[11] << 8) | data[12]) or 500000
                seen.add(tempo)
            wrote = 512 if queued <= 4096 - 512 else 0
            if wrote:
                for event in by_epoch[epoch][0].get(blocks, ()):
                    dispatched += 1
                    kind = event["type"]
                    if kind == "note_on":
                        key = (event["channel"], event["note"])
                        if key in held:
                            off += 1
                        held.add(key)
                        on += 1
                        total_on += 1
                    elif kind == "note_off":
                        key = (event["channel"], event["note"])
                        if key in held:
                            held.remove(key)
                            off += 1
                            total_off += 1
                    elif kind == "tempo":
                        tempo = event["tempo_us_per_quarter"]
                        seen.add(tempo)
                    elif kind == "loop_boundary":
                        cycles += 1
                    else:
                        self.fail(f"unexpected event in epoch {epoch}: {kind}")
                blocks += 1
                queued += 512
            else:
                stalls += 1
            requested = requests[attempt % len(requests)]
            taken = min(queued, requested)
            queued -= taken
            missing += requested - taken
            if taken < requested:
                underruns += 1
            expected = (
                attempt, epoch, wrote, blocks, on, off, tempo, cycles, 1,
                dispatched, queued, taken, missing, 0,
            )
            observed = tuple(map(int, row[1:]))
            self.assertEqual(observed, expected,
                             f"scene epoch {epoch}, request {attempt}")
            if attempt + 1 in bounds[1:]:
                self.assertEqual(cycles, by_epoch[epoch][1])
        self.assertEqual(epoch, 5)
        self.assertEqual(switched_while_queued, len(switch_points))
        self.assertGreater(stalls, 100)
        self.assertGreater(underruns, 10)
        self.assertGreater(total_on, 100)
        self.assertGreater(total_off, 100)
        self.assertEqual(seen, {250000, 300000, 500000, 400000})


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
