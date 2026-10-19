#!/usr/bin/env python3
"""MAP02 v188: check strict source-independent log parser regression cases."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_map02_v188_native_ram_receipts import (
    audit_log, refusal_phase, corrupted_lane, expected_snapshot, POSITIVE_RAM,
)

def fixture(mode: int) -> str:
    failure = refusal_phase(mode)
    result = ["PCSX native synthetic guest invocation"]
    for phase in range(4):
        if phase:
            first, derived, guard = expected_snapshot(phase, mode)
            result.append(
                f"VH187_NATIVE_RAM_SNAPSHOT phase={phase} vblanks={phase} "
                f"first={first:08x} derived={derived:08x} guard={guard:08x}"
            )
        if phase == failure:
            flags = [1, 1, 1]
            flags[corrupted_lane(mode)] = 0
            result.append(
                f"VH185_NATIVE_RAM_PERSISTENCE_REFUSED phase={phase} "
                f"first_ok={flags[0]} derived_ok={flags[1]} guard_ok={flags[2]}"
            )
            break
        result.append(
            f"VH78_VBLANK_OBSERVED phase={phase} event={phase+1} "
            f"frame={phase+1} loops={572 if phase == 0 else 627}"
        )
    if not mode:
        result.extend(POSITIVE_RAM)
    return "\n".join(result) + "\n"

class V188NativeReceiptSequence(unittest.TestCase):
    def test_ten_valid_deterministic_logs_and_dimensions(self):
        counts = [audit_log(fixture(mode), mode) for mode in range(10)]
        self.assertEqual(counts, [3,1,1,1,2,2,2,3,3,3])
        self.assertEqual(sum(counts), 21)

    def test_wrong_mode_refused(self):
        for mode in (-1, 10, 999):
            with self.assertRaises(ValueError):
                audit_log("", mode)

    def test_clean_rejects_duplicate_missing_or_out_of_order_records(self):
        base = fixture(0)
        snap = "VH187_NATIVE_RAM_SNAPSHOT phase=2 vblanks=2 first=51a7c3d9 derived=51a73c26 guard=a1b2c3d4\n"
        evt = "VH78_VBLANK_OBSERVED phase=1 event=2 frame=2 loops=627\n"
        cases = [
            base.replace(snap, ""),        # missing boundary
            base.replace(snap, snap+snap), # duplicate
            base.replace(evt, evt+evt),
            base.replace(snap, snap.replace("phase=2", "phase=3")),
            base.replace(evt, evt.replace("event=2", "event=3")),
            base.replace(evt, evt.replace("loops=627", "loops=0")),
            base.replace(evt, evt.replace("frame=2", "frame=7")),
            base.replace(snap, snap.replace("derived=51a73c26", "derived=51a73c25")),
            base.replace(snap, snap.replace("vblanks=2", "vblanks=1")),
            base.replace(snap, "VH187_NATIVE_RAM_SNAPSHOT malformed\n"),
            base.replace(evt, "VH78_VBLANK_OBSERVED malformed\n"),
            base.replace(POSITIVE_RAM[0]+"\n", ""),
            base.replace(POSITIVE_RAM[0]+"\n", POSITIVE_RAM[0]+"\n"+POSITIVE_RAM[0]+"\n"),
            base.replace(POSITIVE_RAM[1]+"\n", ""),
        ]
        self.assertEqual(len(cases), 14)
        for case in cases:
            with self.subTest(case=cases.index(case)):
                with self.assertRaises(ValueError):
                    audit_log(case, 0)

    def test_all_corruptions_fail_closed_if_fields_or_order_are_forged(self):
        for mode in range(1, 10):
            base = fixture(mode)
            expected = audit_log(base, mode)
            self.assertEqual(expected, refusal_phase(mode))
            phase = refusal_phase(mode)
            first, second, guard = expected_snapshot(phase, mode)
            correct = (f"first={first:08x} derived={second:08x} guard={guard:08x}")
            for bad in (
                correct.replace(f"{first:08x}", "00000000", 1),
                correct.replace(f"{guard:08x}", "abcdef01", 1),
            ):
                with self.subTest(mode=mode, wrong=bad):
                    with self.assertRaises(ValueError):
                        audit_log(base.replace(correct, bad), mode)
            with self.assertRaises(ValueError):
                audit_log(base + POSITIVE_RAM[0] + "\n", mode)
            with self.assertRaises(ValueError):
                audit_log(base.replace("first_ok=", "first_ok=2"), mode)
            with self.assertRaises(ValueError):
                audit_log(base.replace("VH185_NATIVE_RAM_PERSISTENCE_REFUSED",
                                       "VH185_NATIVE_RAM_PERSISTENCE_IGNORED"), mode)
            with self.assertRaises(ValueError):
                audit_log(base.replace(f"phase={phase} vblanks={phase}",
                                       f"phase={phase} vblanks={2 if phase == 3 else 3}"), mode)
            with self.assertRaises(ValueError):
                audit_log(base + base, mode)

    def test_workflows_bind_real_private_native_logs_after_emulator_runs(self):
        parent = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        audit = (ROOT / ".github/workflows/map02-v188-native-receipt-sequence.yml").read_text()
        self.assertIn("check_map02_v188_native_ram_receipts", parent)
        self.assertIn("--verify-dir proof/private", parent)
        self.assertIn("VH188_NATIVE_RAM_RECEIPT_SEQUENCE_PASS", parent)
        self.assertIn("VH186_NATIVE_LATE_RAM_REFUSALS_PASS", parent)
        self.assertIn("test_map02_v188_native_ram_receipts.py", parent)
        self.assertIn("test_map02_v187_native_ram_snapshots.py", audit)
        self.assertIn("original_retail_executed=0", audit)

if __name__ == "__main__":
    unittest.main()
