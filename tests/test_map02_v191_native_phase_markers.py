#!/usr/bin/env python3
"""MAP02 v191: prevent false positive pixel phase passes in native logs."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v188_native_ram_receipts import fixture
from tools.check_map02_v188_native_ram_receipts import refusal_phase
from tools.check_map02_v191_native_phase_markers import (
    FINAL_VRAM, PASS_MARKER, verify_phase_log, audit_directory,
)

def phase_fixture(mode: int) -> str:
    lines = fixture(mode).splitlines()
    expanded = []
    for line in lines:
        expanded.append(line)
        if line.startswith("VH78_VBLANK_OBSERVED phase="):
            phase = int(line.split("phase=", 1)[1].split(" ", 1)[0])
            expanded.append(f"VH78_PHASE_PASS phase={phase} checked=595 guard=499")
    if mode == 0:
        expanded.append(FINAL_VRAM)
    return "\n".join(expanded) + "\n"

class V191NativePhaseMarkerChain(unittest.TestCase):
    def test_all_ten_correct_native_pixel_phase_chains(self):
        expected = [4, 1, 1, 1, 2, 2, 2, 3, 3, 3]
        actual = [verify_phase_log(phase_fixture(m), m) for m in range(10)]
        self.assertEqual(actual, expected)
        self.assertEqual(sum(actual), 22)

    def test_rejects_missing_duplicate_misordered_phase_and_wrong_pixel_count(self):
        for mode in range(10):
            good = phase_fixture(mode)
            marker = "VH78_PHASE_PASS phase=0 checked=595 guard=499"
            for name, bad in {
                "missing": good.replace(marker + "\n", "", 1),
                "duplicate": good.replace(marker, marker+"\n"+marker, 1),
                "wrong-pixels": good.replace(marker, marker.replace("595", "594"), 1),
                "wrong-guard": good.replace(marker, marker.replace("499", "498"), 1),
                "wrong-phase": good.replace(marker, marker.replace("phase=0", "phase=2"), 1),
                "hidden-prefix": good.replace(marker, "PREFIX "+marker, 1),
                "snapshot-too-early": good.replace(
                    marker, "", 1).replace(
                    "VH78_VBLANK_OBSERVED phase=0",
                    marker+"\nVH78_VBLANK_OBSERVED phase=0", 1
                ),
            }.items():
                with self.subTest(mode=mode, case=name):
                    with self.assertRaises(ValueError):
                        verify_phase_log(bad, mode)

    def test_refuses_false_final_pixel_success_in_every_bad_ram_run(self):
        for mode in range(1, 10):
            content = phase_fixture(mode)
            self.assertEqual(verify_phase_log(content, mode), refusal_phase(mode))
            for marker in (FINAL_VRAM, " PREFIX "+FINAL_VRAM):
                with self.subTest(mode=mode, marker=marker[:10]):
                    with self.assertRaises(ValueError):
                        verify_phase_log(content + marker + "\n", mode)

    def test_clean_requires_exact_one_final_2380_pixel_success_after_last_phase(self):
        clean = phase_fixture(0)
        self.assertEqual(verify_phase_log(clean, 0), 4)
        for bad in (
            clean.replace(FINAL_VRAM+"\n", ""),
            clean + FINAL_VRAM + "\n",
            clean.replace(FINAL_VRAM, FINAL_VRAM.replace("2380", "2379")),
            FINAL_VRAM+"\n"+clean.replace(FINAL_VRAM+"\n", ""),
        ):
            with self.assertRaises(ValueError):
                verify_phase_log(bad, 0)

    def test_ten_original_process_logs_and_full_native_audit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for mode in range(10):
                name = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
                (root/name).write_text(phase_fixture(mode), encoding="utf-8")
            self.assertEqual(audit_directory(root), (10, 21, 159, 22))
            (root/"v186-9.log").write_text(
                phase_fixture(9) + FINAL_VRAM + "\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                audit_directory(root)

    def test_pinned_native_ci_requires_v190_before_v191(self):
        native = (ROOT/".github/workflows/map02-v104-content-guard.yml").read_text()
        standalone = (ROOT/".github/workflows/map02-v191-native-phase-markers.yml").read_text()
        self.assertIn(PASS_MARKER, native)
        self.assertIn("test_map02_v191_native_phase_markers.py", native)
        self.assertIn("check_map02_v191_native_phase_markers --verify-dir proof/private", native)
        self.assertLess(
            native.index("VH190_NATIVE_LOG_STABILITY_PASS modes=10"),
            native.index("VH191_NATIVE_PHASE_MARKER_CHAIN_PASS modes=10")
        )
        self.assertIn("test_map02_v190_native_log_stability.py", standalone)
        self.assertIn("original_retail_executed=0", standalone)

if __name__ == "__main__":
    unittest.main()
