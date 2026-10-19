#!/usr/bin/env python3
"""MAP02 v187: native PS1 RAM snapshots must bind to true VBlank ordinals."""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.apply_map02_v187_native_ram_snapshots import (
    SNAPSHOT_MARKER, SNAPSHOT_SUCCESS, EVENT_SEQUENCE_EXIT, patch_frontend,
)
from tools.apply_map02_v186_late_vblank_ram_corruption import (
    patch_frontend as v186_patch, expected_failure,
)
from tools.apply_map02_v185_ram_vblank_persistence import patch_frontend as v185_patch
from tools.apply_map02_v183_native_ram_values import VALUE, TRANSFORMED
from tools.apply_map02_v185_ram_vblank_persistence import GUARD_VALUE

def snapshot(phase: int, mode: int = 0) -> str:
    """Expected output only: actual native logs are verified in CI."""
    if phase not in (1, 2, 3):
        raise ValueError("only post-phase-zero pre-execution snapshots exist")
    values = [VALUE, TRANSFORMED, GUARD_VALUE]
    if mode:
        tampered_phase = 1 if mode <= 3 else expected_failure(mode)[0]
        if phase == tampered_phase:
            lane = (mode - 1) if mode <= 3 else (mode - 4) % 3
            values[lane] ^= 1
    return (
        f"{SNAPSHOT_MARKER} phase={phase} vblanks={phase} "
        f"first={values[0]:08x} derived={values[1]:08x} guard={values[2]:08x}"
    )

class V187NativeSnapshots(unittest.TestCase):
    def test_clean_exact_numeric_receipts(self):
        self.assertEqual(EVENT_SEQUENCE_EXIT, 87)
        for phase in (1, 2, 3):
            self.assertEqual(
                snapshot(phase),
                f"VH187_NATIVE_RAM_SNAPSHOT phase={phase} vblanks={phase} "
                "first=51a7c3d9 derived=51a73c26 guard=a1b2c3d4",
            )
        self.assertIn("boundaries=3", SNAPSHOT_SUCCESS)

    def test_each_of_nine_fault_modes_changes_only_one_word(self):
        for mode in range(1, 10):
            boundary = 1 if mode <= 3 else expected_failure(mode)[0]
            good = snapshot(boundary)
            bad = snapshot(boundary, mode)
            self.assertNotEqual(good, bad)
            a = good.split(" ")
            b = bad.split(" ")
            self.assertEqual(sum(x != y for x, y in zip(a, b)), 1)
            self.assertEqual(len(a), len(b))
            with self.subTest(mode=mode):
                self.assertEqual(bad[:bad.index("first=")],
                                 f"{SNAPSHOT_MARKER} phase={boundary} vblanks={boundary} ")

    def test_native_insertion_precedes_guest_reexecution_and_ram_comparison(self):
        # Generate all v185 CLI flags first; the previous partial stub only
        # carried the v183 flag while incorrectly expecting v185 flags.
        stub = ('\tint vh183_guest_ram_values=0;\n'
                '\t\telse if (!strcmp(argv[i], "--vh183-guest-ram-values"))\n'
                '\tif (loadst_f) {\n')
        native = patch_frontend(v186_patch(v185_patch(stub)))
        self.assertIn(SNAPSHOT_SUCCESS, native)
        self.assertIn("vh78_vblank_observed_count!=phase", native)
        self.assertIn("VH187_NATIVE_VBLANK_SEQUENCE_REFUSED", native)
        self.assertIn("VH187_RAM_SNAPSHOT_COUNT_REFUSED", native)
        self.assertIn("return 87;", native)
        self.assertLess(native.index(SNAPSHOT_MARKER),
                        native.index("if(vh185_first!=0x51a7c3d9u ||"))
        self.assertLess(native.index(SNAPSHOT_MARKER),
                        native.index("unsigned int entry_count=vh78_vblank_observed_count;"))
        self.assertLess(native.index("vh187_snapshots!=3u"),
                        native.index('SysPrintf("VH185_NATIVE_RAM_PERSISTENCE_PASS'))
        for idx in range(10):
            old = "--vh185-ram-persist-" if idx < 4 else "--vh186-ram-persist-"
            self.assertIn(f"{old}{idx}", native)
        with self.assertRaises(ValueError):
            patch_frontend(native)

    def test_native_ci_checks_actual_receipts_and_fail_closed(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        audit = (ROOT / ".github/workflows/map02-v187-native-ram-snapshots.yml").read_text()
        for token in (
            "apply_map02_v187_native_ram_snapshots",
            "test_map02_v187_native_ram_snapshots.py",
            "VH187_NATIVE_RAM_SNAPSHOT",
            "VH187_NATIVE_RAM_SNAPSHOTS_PASS",
            "for mode in 4 5 6 7 8 9; do",
            "VH186_NATIVE_LATE_RAM_REFUSALS_PASS",
            "native_snapshot=",
            'grep -Fx "$native_snapshot"',
        ):
            self.assertIn(token, native)
        self.assertIn("test_map02_v186_late_vblank_ram_corruption.py", audit)
        self.assertIn("original_retail_executed=0", audit)

if __name__ == "__main__":
    unittest.main()
