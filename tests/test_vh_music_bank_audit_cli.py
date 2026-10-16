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
                {"program": 9, "note": 67, "selected_program": 7,
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
            seq_file.write_bytes(b"pQES" + b"\\x00" * 11)
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
