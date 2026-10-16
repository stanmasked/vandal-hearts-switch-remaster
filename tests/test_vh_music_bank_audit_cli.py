"""Asset-free CLI tests for the offline dual SEQ/VH/VB music audit.
Build the CLI via 'make build/vh_music_bank_audit' first.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "build" / "vh_music_bank_audit"

def seq(program: int, note: int) -> bytes:
    return (b"pQES" + bytes((0, 0, 0, 0, 1, 0xe0, 7, 0xa1, 0x20, 0, 0))
            + bytes((0, 0xc0, program, 0, 0x90, note, 105,
                     0x81, 0x70, 0x80, note, 0, 0, 0xff, 0x2f)))

def fixtures(root: Path, field_program: int = 7,
             selected_program: int = 7) -> None:
    for name, program, note, variant in [
        ("field", field_program, 60, 0),
        ("selected", selected_program, 67, 1),
    ]:
        dest = root / name
        dest.mkdir(parents=True, exist_ok=True)
        vh = bytearray(32 + 128 * 16 + 512 + 512)
        vh[:4] = b"pBAV"
        struct.pack_into("<HHH", vh, 18, 8, 1, 1)
        vh[24] = 127
        prog = 32 + 7 * 16
        vh[prog] = 1
        vh[prog + 1] = 127
        vh[prog + 4] = 64
        tone = 32 + 128 * 16
        vh[tone + 1] = 4
        vh[tone + 2] = 127
        vh[tone + 3] = 64
        vh[tone + 4] = 60
        vh[tone + 6] = 40
        vh[tone + 7] = 100
        struct.pack_into("<H", vh, tone + 16, 15)
        struct.pack_into("<HH", vh, tone + 20, 7, 1)
        struct.pack_into("<HH", vh, tone + 512, 2, 4)
        vb = bytearray(48)
        vb[16:18] = b"\x02\x04"
        vb[18:32] = bytes([0x22 if variant == 0 else 0x44]) * 14
        vb[32:34] = b"\x02\x03"
        vb[34:48] = bytes([0xee if variant == 0 else 0xdd]) * 14
        (dest / "music.seq").write_bytes(seq(program, note))
        (dest / "music.vh").write_bytes(vh)
        (dest / "music.vb").write_bytes(vb)

def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(CLI), *args], cwd=ROOT,
                          capture_output=True, text=True, check=False)

class MusicBankAuditCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CLI.is_file():
            raise RuntimeError("First build the CLI: make build/vh_music_bank_audit")

    def test_exact_and_strict_pass(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            result = run("--strict", path)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["schema"], 1)
            self.assertEqual(set(report) - {"schema"}, {"field", "selected"})
            for scene in ("field", "selected"):
                self.assertEqual(report[scene]["note_on"], 1)
                self.assertEqual(report[scene]["resolved"], 1)
                self.assertEqual(report[scene]["fallback"], 0)
                self.assertIsNone(report[scene]["first_missing"])
                self.assertIsNone(report[scene]["first_fallback"])
            self.assertNotIn("pQES", result.stdout)
            self.assertNotIn(path, result.stdout)

    def test_cross_program_fallback_is_actionable_and_strict_fails(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder, selected_program=9)
            normal = run(path)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            report = json.loads(normal.stdout)
            self.assertEqual(report["field"]["fallback"], 0)
            self.assertEqual(report["selected"]["fallback"], 1)
            self.assertEqual(
                report["selected"]["first_fallback"],
                {"program": 9, "note": 67, "selected_program": 0,
                 "selected_tone": 0, "selected_vag": 1})
            strict = run("--strict", path)
            self.assertEqual(strict.returncode, 4)
            self.assertEqual(json.loads(strict.stdout), report)

    def test_report_is_deterministic_and_does_not_expose_local_paths(self):
        with tempfile.TemporaryDirectory(prefix="music audit private ") as path:
            folder = Path(path)
            fixtures(folder, selected_program=9)
            first = run(path)
            second = run(path)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(first.stderr, second.stderr)
            report = json.loads(first.stdout)
            self.assertEqual(report["selected"]["fallback"], 1)
            self.assertNotIn(path, first.stdout)
            self.assertNotIn(path, first.stderr)
            self.assertNotIn("pBAV", first.stdout)
            self.assertEqual(run("--strict", path).returncode, 4)

    def test_bad_sequence_is_rejected_without_partial_json(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            seq_file = folder / "selected" / "music.seq"
            seq_file.write_bytes(seq(7, 60)[:15] + bytes((0, 0x90, 60)))
            result = run(path)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(path, result.stderr)

    def test_truncated_vb_is_rejected_without_partial_json(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            vb = folder / "field" / "music.vb"
            vb.write_bytes(vb.read_bytes()[:16])
            result = run("--strict", path)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(path, result.stderr)

    def test_interleaved_channels_keep_independent_programs(self):
        """A program change on channel 1 must not leak into channel 0."""
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            # Both channels request notes covered by program 7, but
            # channel 1 requests program 9 and must be reported as fallback.
            # Velocity-zero note_on is note_off, not another note to audit.
            events = bytes((
                0, 0xC0, 7,       # ch0 -> program 7
                0, 0xC1, 9,       # ch1 -> program 9
                0, 0x90, 60, 100, # ch0 -> exact
                0, 0x91, 67, 100, # ch1 -> fallback
                0, 0x91, 67, 0,   # ch1 -> note_off
                0x81, 0x70, 0xFF, 0x2F, # nonzero song duration
            ))
            (folder / "selected" / "music.seq").write_bytes(
                seq(7, 60)[:15] + events
            )
            normal = run(path)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            report = json.loads(normal.stdout)
            selected = report["selected"]
            self.assertEqual(selected["note_on"], 2)
            self.assertEqual(selected["resolved"], 2)
            self.assertEqual(selected["program_changes"], 2)
            self.assertEqual(selected["fallback"], 1)
            self.assertEqual(selected["missing"], 0)
            self.assertEqual(selected["first_fallback"], {
                "program": 9, "note": 67, "selected_program": 0,
                "selected_tone": 0, "selected_vag": 1,
            })
            strict = run("--strict", path)
            self.assertEqual(strict.returncode, 4, strict.stderr)
            self.assertEqual(json.loads(strict.stdout), report)

    def test_program_changes_and_running_status_within_one_song(self):
        """Count notes at the effective program, including running status."""
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            events = bytes((
                0, 0xC0, 7,         # program 7 -> direct
                0, 0x90, 60, 100,   # note 60
                0, 64, 100,         # running-status note_on 64
                0, 0xC0, 9,         # same channel -> fallback
                0, 0x90, 67, 100,   # fallback note
                0, 67, 0,           # running-status velocity-zero note_off
                0, 0xC0, 7,         # restore direct program
                0, 0x90, 72, 100,   # direct note
                0x81, 0x70, 0xFF, 0x2F,  # positive duration
            ))
            (folder / "selected" / "music.seq").write_bytes(
                seq(7, 60)[:15] + events
            )
            normal = run(path)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            report = json.loads(normal.stdout)
            selected = report["selected"]
            self.assertEqual(selected["note_on"], 4)
            self.assertEqual(selected["resolved"], 4)
            self.assertEqual(selected["missing"], 0)
            self.assertEqual(selected["program_changes"], 3)
            self.assertEqual(selected["fallback"], 1)
            self.assertEqual(selected["first_fallback"], {
                "program": 9, "note": 67, "selected_program": 0,
                "selected_tone": 0, "selected_vag": 1,
            })
            strict = run("--strict", path)
            self.assertEqual(strict.returncode, 4, strict.stderr)
            self.assertEqual(json.loads(strict.stdout), report)

    def test_multiple_fallbacks_retain_first_event_per_scene(self):
        """Counts include later mismatches, but diagnostics keep the first."""
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            field_events = bytes((
                0, 0xC0, 9,          # first fallback: program 9 / note 60
                0, 0x90, 60, 100,
                0, 0xC0, 7,          # exact note must not overwrite it
                0, 0x90, 62, 100,
                0, 0xC0, 12,
                0, 0x90, 65, 100,    # second fallback in field
                0, 0x90, 65, 0,      # note_off, not third fallback
                0x81, 0x70, 0xFF, 0x2F,
            ))
            selected_events = bytes((
                0, 0xC0, 7,
                0, 0x90, 67, 100,    # exact first note
                0, 0xC0, 10,
                0, 0x90, 69, 100,    # first fallback in selected
                0, 0xC0, 11,
                0, 0x90, 71, 100,    # second fallback in selected
                0, 0x80, 71, 0,      # explicit note_off is not counted
                0x81, 0x70, 0xFF, 0x2F,
            ))
            (folder / "field" / "music.seq").write_bytes(
                seq(7, 60)[:15] + field_events
            )
            (folder / "selected" / "music.seq").write_bytes(
                seq(7, 60)[:15] + selected_events
            )

            normal = run(path)
            self.assertEqual(normal.returncode, 0, normal.stderr)
            report = json.loads(normal.stdout)
            for scene in ("field", "selected"):
                data = report[scene]
                self.assertEqual(data["note_on"], 3)
                self.assertEqual(data["resolved"], 3)
                self.assertEqual(data["missing"], 0)
                self.assertEqual(data["fallback"], 2)
                self.assertEqual(data["program_changes"], 3)
                self.assertIsNone(data["first_missing"])
            self.assertEqual(report["field"]["first_fallback"], {
                "program": 9, "note": 60, "selected_program": 0,
                "selected_tone": 0, "selected_vag": 1,
            })
            self.assertEqual(report["selected"]["first_fallback"], {
                "program": 10, "note": 69, "selected_program": 0,
                "selected_tone": 0, "selected_vag": 1,
            })
            strict = run("--strict", path)
            self.assertEqual(strict.returncode, 4, strict.stderr)
            self.assertEqual(json.loads(strict.stdout), report)
            self.assertNotIn(path, normal.stdout)
            self.assertNotIn(path, strict.stderr)

    def test_truncated_running_status_and_tempo_are_rejected(self):
        """An invalid final SEQ must not emit a partial report for either bank."""
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            seq_file = folder / "selected" / "music.seq"
            header = seq(7, 60)[:15]
            invalid_events = (
                bytes((0, 0x90, 60, 105, 0, 0xFF, 0x51, 7, 0xA1, 0x20,
                       0, 67, 100, 0x81, 0x70, 0xFF, 0x2F)),
                bytes((0, 0xC0, 7, 0, 0x90, 60)),
                bytes((0, 0xFF, 0x51, 7, 0xA1)), # incomplete tempo bytes
            )
            for events in invalid_events:
                with self.subTest(events=events):
                    seq_file.write_bytes(header + events)
                    for args in ((path,), ("--strict", path)):
                        result = run(*args)
                        self.assertEqual(result.returncode, 3, result.stderr)
                        self.assertEqual(result.stdout, "")
                        self.assertNotIn(path, result.stderr)

    def test_sparse_program_out_of_range_uses_first_shadow_alias(self):
        """Out-of-range p7 notes select shadow p0 while strict still fails."""
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            fixtures(folder)
            vh = folder / "selected" / "music.vh"
            data = bytearray(vh.read_bytes())
            tone = 32 + 128 * 16
            data[tone + 6] = 60
            data[tone + 7] = 65
            vh.write_bytes(data)
            seq_file = folder / "selected" / "music.seq"
            for note, fallback in ((59, 1), (60, 0), (65, 0), (66, 1)):
                with self.subTest(note=note):
                    seq_file.write_bytes(seq(7, note))
                    normal = run(path)
                    self.assertEqual(normal.returncode, 0, normal.stderr)
                    report = json.loads(normal.stdout)
                    selected = report["selected"]
                    self.assertEqual(selected["note_on"], 1)
                    self.assertEqual(selected["resolved"], 1)
                    self.assertEqual(selected["missing"], 0)
                    self.assertEqual(selected["fallback"], fallback)
                    self.assertEqual(report["field"]["fallback"], 0)
                    expected = ({
                        "program": 7, "note": note, "selected_program": 0,
                        "selected_tone": 0, "selected_vag": 1,
                    } if fallback else None)
                    self.assertEqual(selected["first_fallback"], expected)
                    strict = run("--strict", path)
                    self.assertEqual(strict.returncode, 4 if fallback else 0,
                                     strict.stderr)
                    self.assertEqual(json.loads(strict.stdout), report)

    def test_missing_partial_corrupt_and_help(self):
        with tempfile.TemporaryDirectory() as path:
            folder = Path(path)
            self.assertEqual(run(path).returncode, 2)
            fixtures(folder)
            (folder / "selected" / "music.seq").unlink()
            self.assertEqual(run(path).returncode, 3)
            fixtures(folder)
            (folder / "selected" / "music.vh").write_bytes(b"corrupt")
            self.assertEqual(run(path).returncode, 3)
            self.assertEqual(run("--unexpected", path).returncode, 1)

if __name__ == "__main__":
    unittest.main()
