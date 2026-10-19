#!/usr/bin/env python3
"""MAP02 v189: real log replay must reject every adversarial transcript."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v188_native_ram_receipts import fixture
from tools.check_map02_v188_native_ram_receipts import (
    audit_log, POSITIVE_RAM,
)
from tools.check_map02_v189_adversarial_native_logs import (
    PASS_MARKER, audit_strict, replay_mutations, audit_replay,
)

class V189NativeLogReplay(unittest.TestCase):
    def test_exact_ten_good_baselines_and_159_strict_rejections(self):
        total = 0
        snapshots = []
        for mode in range(10):
            original = fixture(mode)
            snapshots.append(audit_strict(original, mode))
            recipes = list(replay_mutations(original, mode))
            self.assertEqual(len(recipes), 15 if mode == 0 else 16)
            self.assertEqual(len({label for label, _ in recipes}), len(recipes))
            for label, mutated in recipes:
                with self.subTest(mode=mode, recipe=label):
                    self.assertNotEqual(mutated, original)
                    with self.assertRaises(ValueError):
                        audit_strict(mutated, mode)
                total += 1
        self.assertEqual(sum(snapshots), 21)
        self.assertEqual(total, 159)

    def test_closes_v188_gap_refusal_preceding_its_native_ram_snapshot(self):
        for mode in range(1, 10):
            original = fixture(mode)
            modified = dict(replay_mutations(original, mode))["refusal-before-bad-readback"]
            # Presence/count-only v188 can miss this chronological false witness.
            self.assertGreater(audit_log(modified, mode), 0)
            with self.assertRaisesRegex(ValueError, "timeline"):
                audit_strict(modified, mode)

    def test_closes_v188_gap_for_reordered_positive_markers(self):
        good = fixture(0)
        modified = dict(replay_mutations(good, 0))["reorder-passes"]
        self.assertEqual(audit_log(modified, 0), 3)
        with self.assertRaisesRegex(ValueError, "timeline"):
            audit_strict(modified, 0)

    def test_real_directory_replay_and_no_file_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            originals = {}
            for mode in range(10):
                file = root / (f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log")
                file.write_text(fixture(mode), encoding="utf-8")
                originals[file.name] = file.read_bytes()
            self.assertEqual(audit_replay(root), (10, 21, 159))
            for name, content in originals.items():
                self.assertEqual((root / name).read_bytes(), content)
            (root / "v186-9.log").unlink()
            with self.assertRaises(ValueError):
                audit_replay(root)

    def test_native_ci_uses_actual_private_logs_after_original_v188_check(self):
        parent = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v189-adversarial-native-log-replay.yml").read_text()
        assert_marker = "VH189_NATIVE_LOG_REPLAY_PASS modes=10 snapshots=21 mutations=159 chronology=1 rejected=159 original_retail=0"
        self.assertEqual(PASS_MARKER, assert_marker)
        self.assertIn("check_map02_v189_adversarial_native_logs", parent)
        self.assertIn("test_map02_v189_adversarial_native_logs.py", parent)
        self.assertIn(assert_marker, parent)
        self.assertLess(parent.index("VH188_NATIVE_RAM_RECEIPT_SEQUENCE_PASS modes=10"),
                        parent.index("VH189_NATIVE_LOG_REPLAY_PASS modes=10"))
        self.assertIn("test_map02_v188_native_ram_receipts.py", independent)
        self.assertIn("original_retail_executed=0", independent)
        self.assertIn("VH186_NATIVE_LATE_RAM_REFUSALS_PASS", parent)

if __name__ == "__main__":
    unittest.main()
