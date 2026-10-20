#!/usr/bin/env python3
"""MAP02 v196: guest MIPS-I SW/LW dependency with real load-delay model."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v194_source_bound_exe import seed_source_witness
from tools.apply_map02_v183_native_ram_values import make_variants
from tools.check_map02_v195_independent_mips_opcodes import WORDS, verify_opcode_image
from tools.check_map02_v196_independent_mips_ram_semantics import (
    BASE, AUTHORED_WORD, COMPUTED_WORD, INITIAL_WORD, NEIGHBOR_GUARD,
    PASS_MARKER, audit_guest_ram, execute_words, signed_window,
)


class V196GuestMipsRamSemantics(unittest.TestCase):
    def test_real_source_input_executes_two_guest_stores_one_load_and_load_delay(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            seed_source_witness(root)
            native = (root / "V183_RAM_CORRECT.EXE").read_bytes()
            offset = verify_opcode_image(native)
            words = signed_window(native, offset)
            self.assertEqual(words, WORDS)
            ram, sw, lw, pending = execute_words(words)
            self.assertEqual((sw, lw, pending), (2, 1, (6,)))
            self.assertEqual(ram[BASE], AUTHORED_WORD)
            self.assertEqual(ram[BASE + 4], COMPUTED_WORD)
            self.assertEqual(ram[BASE + 8], NEIGHBOR_GUARD)
            self.assertEqual(audit_guest_ram(root), (10, 9, 2))

    def test_both_original_one_instruction_refusals_do_not_compute_true_ram(self):
        correct = make_variants()["CORRECT"]
        offset = verify_opcode_image(correct)
        for label in ("MISSING_SW", "MISSING_LW"):
            with self.subTest(label=label):
                corrupt = make_variants()[label]
                ram, sw, lw, commits = execute_words(signed_window(corrupt, offset))
                self.assertNotEqual(ram[BASE + 4], COMPUTED_WORD)
                self.assertEqual(ram[BASE + 8], NEIGHBOR_GUARD)
                if label == "MISSING_SW":
                    self.assertEqual((ram[BASE], sw, lw, commits), (INITIAL_WORD, 1, 1, (6,)))
                else:
                    self.assertEqual((ram[BASE], sw, lw, commits), (AUTHORED_WORD, 2, 0, ()))

    def test_delayed_load_must_not_be_visible_to_immediately_following_xori(self):
        # Move XORI into LW's one-instruction load-delay slot. A mistaken
        # zero-delay interpreter would falsely compute the correct value;
        # real PS1 MIPS-I registers still contain the prior 0xFF value.
        altered = list(WORDS)
        altered[6], altered[7] = altered[7], altered[6]
        ram, sw, lw, commits = execute_words(tuple(altered))
        self.assertEqual((sw, lw, commits), (2, 1, (6,)))
        self.assertEqual(ram[BASE + 4], AUTHORED_WORD)
        self.assertNotEqual(ram[BASE + 4], COMPUTED_WORD)

    def test_invalid_opcodes_memory_address_and_pending_load_refused(self):
        altered = list(WORDS)
        altered[3] = (altered[3] & 0xFFFF0000) | 8  # SW into protected neighbor
        with self.assertRaisesRegex(ValueError, "unexpected RAM address"):
            execute_words(tuple(altered))
        altered = list(WORDS)
        altered[2] = 0xFFFFFFFF  # unrecognized instruction family
        with self.assertRaisesRegex(ValueError, "unexpected synthetic MIPS"):
            execute_words(tuple(altered))
        altered = list(WORDS)
        altered[8] = altered[5]  # final LW with no delay slot
        with self.assertRaisesRegex(ValueError, "outside nine-word"):
            execute_words(tuple(altered))
        with self.assertRaises(ValueError):
            execute_words(WORDS[:-1])

    def test_canonical_native_chain_and_workflow_order_are_enforced(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v196-independent-mips-ram.yml").read_text()
        self.assertIn(PASS_MARKER, native)
        self.assertIn("test_map02_v196_independent_mips_ram_semantics.py", native)
        self.assertIn("check_map02_v196_independent_mips_ram_semantics --verify-dir proof/private", native)
        self.assertLess(
            native.index("VH195_INDEPENDENT_MIPS_OPCODES_PASS modes=10"),
            native.index("VH196_INDEPENDENT_GUEST_MIPS_RAM_PASS modes=10"),
        )
        self.assertIn("test_map02_v195_independent_mips_opcodes.py", independent)
        self.assertIn("original_retail_executed=0", independent)


if __name__ == "__main__":
    unittest.main()
