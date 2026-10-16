"""Synthetic-only tests for VAB aliases seen by the upstream PC-port loader."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_resolve_vab_note import make_sparse_bank
from tools.audit_pcport_vab_aliases import audit_aliases

CLI = ROOT / "tools" / "audit_pcport_vab_aliases.py"


class PcPortAliasAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vab alias private ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vh = self.root / "music.vh"
        self.vb = self.root / "music.vb"
        vh, vb = make_sparse_bank()
        self.vh.write_bytes(vh)
        self.vb.write_bytes(vb)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )

    def test_sparse_program_gaps_alias_next_packed_block(self):
        report = audit_aliases(self.vh, self.vb)
        self.assertEqual(report["schema"], 1)
        self.assertEqual(report["highest_populated_program"], 10)
        self.assertEqual(report["gap_alias_tones"], 8)
        self.assertEqual(report["inactive_slot_tones"], 0)
        self.assertTrue(report["requires_pcport_compatibility_review"])
        self.assertEqual(
            [(x["program"], x["source_program"], x["vag"])
             for x in report["aliases"]],
            [(p, 7, 3) for p in range(1, 7)]
            + [(p, 10, 4) for p in range(8, 10)],
        )
        self.assertTrue(all(x["valid_vag_and_range"] for x in report["aliases"]))

    def test_non_active_slot_with_vag_is_not_silently_skipped(self):
        vh = bytearray(self.vh.read_bytes())
        tone = 2080 + 2 * 32  # p0 slot 2, while p0 declares nTone = 2
        vh[tone + 6] = 115
        vh[tone + 7] = 120
        struct.pack_into("<H", vh, tone + 22, 2)
        self.vh.write_bytes(vh)
        report = audit_aliases(self.vh, self.vb)
        self.assertEqual(report["gap_alias_tones"], 8)
        self.assertEqual(report["inactive_slot_tones"], 1)
        self.assertEqual(report["aliases"][0], {
            "kind": "inactive_slot",
            "program": 0, "tone": 2, "source_program": 0,
            "vag": 2, "key_min": 115, "key_max": 120,
            "valid_vag_and_range": True,
        })

    def test_unused_slot_out_of_bounds_vag_is_diagnosed(self):
        vh = bytearray(self.vh.read_bytes())
        struct.pack_into("<H", vh, 2080 + 2 * 32 + 22, 250)
        self.vh.write_bytes(vh)
        report = audit_aliases(self.vh, self.vb)
        bad = [x for x in report["aliases"] if not x["valid_vag_and_range"]]
        self.assertEqual(len(bad), 1)
        self.assertEqual((bad[0]["program"], bad[0]["tone"], bad[0]["vag"]),
                         (0, 2, 250))

    def test_contiguous_single_program_has_no_aliases(self):
        header = bytearray(32)
        header[:4] = b"pBAV"
        struct.pack_into("<HHH", header, 18, 1, 1, 1)
        program_table = bytearray(128 * 16)
        program_table[0] = 1
        program_table[1] = 127
        program_table[4] = 64
        tone_table = bytearray(512)
        tone_table[2] = 127
        tone_table[3] = 64
        tone_table[4] = 60
        tone_table[6] = 40
        tone_table[7] = 100
        struct.pack_into("<HH", tone_table, 20, 0, 1)
        sizes = bytearray(512)
        struct.pack_into("<HH", sizes, 0, 2, 2)
        self.vh.write_bytes(header + program_table + tone_table + sizes)
        self.vb.write_bytes(bytes(32))
        report = audit_aliases(self.vh, self.vb)
        self.assertEqual(report["aliases"], [])
        self.assertFalse(report["requires_pcport_compatibility_review"])
        self.assertEqual(report["gap_alias_tones"], 0)
        self.assertEqual(report["inactive_slot_tones"], 0)
        cli = self.cli("--strict", str(self.vh), "--vb", str(self.vb))
        self.assertEqual(cli.returncode, 0, cli.stderr)

    def test_cli_strict_json_is_stable_and_private(self):
        normal = self.cli(str(self.vh), "--vb", str(self.vb))
        strict = self.cli("--strict", str(self.vh), "--vb", str(self.vb))
        repeat = self.cli(str(self.vh), "--vb", str(self.vb))
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(strict.returncode, 4, strict.stderr)
        self.assertEqual(normal.stdout, strict.stdout)
        self.assertEqual(normal.stdout, repeat.stdout)
        self.assertEqual(json.loads(normal.stdout)["gap_alias_tones"], 8)
        self.assertNotIn(str(self.root), normal.stdout)
        self.assertNotIn("pBAV", normal.stdout)

    def test_mismatched_header_count_fails_closed(self):
        vh = bytearray(self.vh.read_bytes())
        struct.pack_into("<H", vh, 18, 4)  # 3 populated records
        self.vh.write_bytes(vh)
        with self.assertRaisesRegex(ValueError, "header program count differs"):
            audit_aliases(self.vh, self.vb)


if __name__ == "__main__":
    unittest.main()
