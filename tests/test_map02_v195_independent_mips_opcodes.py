#!/usr/bin/env python3
"""MAP02 v195: independently verify guest SW/LW opcode chain in PS-X EXE."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v194_source_bound_exe import seed_source_witness
from tools.apply_map02_v183_native_ram_values import make_variants
from tools.check_map02_v194_source_bound_exe import audit_canonical_source
from tools.check_map02_v195_independent_mips_opcodes import (
    WORDS, PASS_MARKER, verify_opcode_image, audit_opcode_lineage,
)


def find_signed_offset(blob: bytes) -> int:
    seq = b"".join(w.to_bytes(4, "little") for w in WORDS)
    loc = blob.find(seq, 2048)
    if loc < 2048 or blob.find(seq, loc + 1) != -1:
        raise ValueError("synthetic guest chain not unique in canonical test image")
    return loc


class V195IndependentMipsOpcodeSequence(unittest.TestCase):
    def test_source_generated_native_exe_has_exact_nine_signed_words(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed_source_witness(root)
            before = (root / "V183_RAM_CORRECT.EXE").read_bytes()
            self.assertEqual(verify_opcode_image(before), find_signed_offset(before))
            self.assertEqual(audit_opcode_lineage(root), (10, 9, 2))
            self.assertEqual((root / "V183_RAM_CORRECT.EXE").read_bytes(), before)

    def test_mips_word_and_load_delay_mutations_all_fail(self):
        original = make_variants()["CORRECT"]
        offset = find_signed_offset(original)
        for j in range(9):
            modified = bytearray(original)
            modified[offset + 4*j] ^= 1
            with self.subTest(word=j), self.assertRaisesRegex(ValueError, "hardcoded"):
                verify_opcode_image(bytes(modified))

    def test_rejects_duplicate_signed_opcode_window(self):
        original = bytearray(make_variants()["CORRECT"])
        offset = find_signed_offset(original)
        other = offset + 64
        original[other:other + 36] = original[offset:offset + 36]
        with self.assertRaisesRegex(ValueError, "exactly one"):
            verify_opcode_image(bytes(original))

    def test_rejects_psx_exe_header_or_signature_forgery(self):
        original = make_variants()["CORRECT"]
        for at in (0, 0x4C):
            mutant = bytearray(original)
            mutant[at] ^= 0x01
            with self.subTest(offset=at), self.assertRaises(ValueError):
                verify_opcode_image(bytes(mutant))

    def test_catches_compromised_builder_that_would_pass_v194(self):
        # Malicious source builder AND all twenty native EXE receipts agree
        # on the same invalid input. The v194 source-rebuild hash check alone
        # would accept; the independent literal opcodes must still refuse it.
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            seed_source_witness(directory)
            canonical = make_variants()
            bad = bytearray(canonical["CORRECT"])
            off = find_signed_offset(bad)
            bad[off + 4*3:off + 4*4] = b"\x00\x00\x00\x00"
            fake = bytes(bad)
            (directory / "V183_RAM_CORRECT.EXE").write_bytes(fake)
            sha = hashlib.sha256(fake).hexdigest()
            (directory / "v193-native-exe-receipts.txt").write_text(
                "".join(f"mode={mode} before={sha} after={sha}\n" for mode in range(10)),
                encoding="ascii",
            )
            forged = dict(canonical, CORRECT=fake)
            with patch(
                "tools.check_map02_v194_source_bound_exe.make_variants",
                return_value=forged,
            ):
                self.assertEqual(audit_canonical_source(directory), (10, 3, 20))
                with self.assertRaisesRegex(ValueError, "hardcoded"):
                    audit_opcode_lineage(directory)

    def test_native_ci_enforces_literals_after_source_rebuild(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v195-independent-mips-opcodes.yml").read_text()
        self.assertIn(PASS_MARKER, native)
        self.assertIn("test_map02_v195_independent_mips_opcodes.py", native)
        self.assertIn("check_map02_v195_independent_mips_opcodes --verify-dir proof/private", native)
        self.assertLess(
            native.index("VH194_NATIVE_SOURCE_EXE_REBUILD_PASS modes=10"),
            native.index("VH195_INDEPENDENT_MIPS_OPCODES_PASS modes=10"),
        )
        self.assertIn("test_map02_v194_source_bound_exe.py", independent)
        self.assertIn("original_retail_executed=0", independent)


if __name__ == "__main__":
    unittest.main()
