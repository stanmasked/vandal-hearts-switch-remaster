#!/usr/bin/env python3
"""MAP02 v192: refuse fabricated or mismatched native process exits."""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_map02_v191_native_phase_markers import phase_fixture
from tools.check_map02_v192_native_process_exits import (
    MANIFEST, MARKER, verified_manifest, verify_exits,
)

def build_fixtures(directory: Path):
    receipts = []
    for mode in range(10):
        filename = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
        data = phase_fixture(mode).encode("utf-8")
        (directory / filename).write_bytes(data)
        receipts.append(f"mode={mode} exit={0 if mode == 0 else 86} sha256={hashlib.sha256(data).hexdigest()}")
    (directory / MANIFEST).write_text("\n".join(receipts)+"\n", encoding="ascii")
    return receipts

class V192NativeExitReceipts(unittest.TestCase):
    def test_ten_native_codes_and_hashes_survive_159_mutations(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            original = build_fixtures(directory)
            before = (directory / MANIFEST).read_bytes()
            self.assertEqual(verified_manifest(directory), original)
            self.assertEqual(verify_exits(directory), (10, 9, 10))
            self.assertEqual((directory / MANIFEST).read_bytes(), before)

    def test_refuse_wrong_exit_status_and_forged_or_reordered_receipts(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            lines = build_fixtures(directory)
            bad_cases = [
                lines[:1]+lines[2:],
                lines+lines[-1:],
                lines[1:2]+lines[0:1]+lines[2:],
                [lines[0].replace("exit=0", "exit=86")]+lines[1:],
                lines[:4]+[lines[4].replace("exit=86", "exit=0")]+lines[5:],
                lines[:3]+[lines[3].replace("sha256=", "sha256=f")]+lines[4:],
                lines[:5]+[" PREFIX "+lines[5]]+lines[6:],
                lines[:6]+[lines[6].replace("mode=6", "mode=9")]+lines[7:],
            ]
            self.assertEqual(len(bad_cases), 8)
            for ix, mutated in enumerate(bad_cases):
                with self.subTest(case=ix):
                    (directory / MANIFEST).write_text("\n".join(mutated)+"\n")
                    with self.assertRaises(ValueError):
                        verify_exits(directory)

    def test_refuse_log_replacement_even_if_exit_status_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            build_fixtures(directory)
            target = directory / "v186-7.log"
            target.write_bytes(target.read_bytes()+b"\nWRONG NATIVE LOG CONTENT\n")
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                verify_exits(directory)

    def test_refuse_private_manifest_symlink_and_oversize(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            build_fixtures(directory)
            manifest = directory / MANIFEST
            original = directory / "original-private-manifest"
            manifest.rename(original)
            manifest.symlink_to(original)
            with self.assertRaises(ValueError):
                verified_manifest(directory)
            manifest.unlink()
            manifest.write_bytes(b"x"*2049)
            with self.assertRaises(ValueError):
                verified_manifest(directory)

    def test_fail_closed_entrypoint_even_with_python_optimized_mode(self):
        source = (ROOT / "tools/check_map02_v192_native_process_exits.py").read_text()
        self.assertNotIn("assert verify_exits(", source)
        self.assertIn("if verify_exits(args.verify_dir) != (10, 9, 10):", source)
        self.assertIn('raise ValueError("native process-exit receipt verification failed")', source)

    def test_native_ci_records_each_process_exit_before_v192_parser(self):
        native = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v192-native-exit-log-receipts.yml").read_text()
        self.assertEqual(native.count("printf 'mode=%s exit=%s sha256=%s\\n'"), 2)
        self.assertEqual(native.count('>> proof/private/v192-native-exits.txt'), 2)
        self.assertIn('sha256sum "proof/private/v185-$mode.log"', native)
        self.assertIn('sha256sum "proof/private/v186-$mode.log"', native)
        self.assertIn('v192-native-exits.txt', native)
        self.assertIn("check_map02_v192_native_process_exits --verify-dir proof/private", native)
        self.assertIn(MARKER, native)
        self.assertLess(native.index("VH191_NATIVE_PHASE_MARKER_CHAIN_PASS modes=10"),
                        native.index("VH192_NATIVE_PROCESS_EXIT_RECEIPTS_PASS modes=10"))
        self.assertIn("test_map02_v191_native_phase_markers.py", independent)
        self.assertIn("original_retail_executed=0", independent)

if __name__ == "__main__":
    unittest.main()
