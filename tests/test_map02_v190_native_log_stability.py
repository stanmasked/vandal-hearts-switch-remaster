#!/usr/bin/env python3
"""MAP02 v190: native evidence stability and same-byte inode-swap refusal."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_map02_v188_native_ram_receipts import fixture
from tools.check_map02_v190_native_log_stability import (
    PASS_MARKER, audit_stability, sample_file, snapshot_directory,
)

def make_private_native_logs(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for mode in range(10):
        name = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
        data = fixture(mode).encode("utf-8")
        (root / name).write_bytes(data)
        files[name] = data
    return files

class V190NativeEvidenceStability(unittest.TestCase):
    def test_all_ten_originals_unchanged_by_159_hostile_in_memory_replays(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            originals = make_private_native_logs(root)
            before = snapshot_directory(root)
            self.assertEqual(len(before), 10)
            self.assertEqual(audit_stability(root), (10, 21, 159))
            self.assertEqual(snapshot_directory(root), before)
            for name, raw in originals.items():
                self.assertEqual((root / name).read_bytes(), raw)

    def test_detects_in_place_evidence_corruption_during_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_private_native_logs(root)
            target = root / "v186-9.log"

            def malicious_replay(directory):
                with target.open("ab") as f:
                    f.write(b"\nTAMPERED AFTER ORIGINAL READ\n")
                return (10, 21, 159)

            with patch(
                "tools.check_map02_v190_native_log_stability.audit_replay",
                side_effect=malicious_replay,
            ):
                with self.assertRaisesRegex(ValueError, "changed during replay"):
                    audit_stability(root)

    def test_detects_same_byte_content_replacement_with_new_inode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_private_native_logs(root)
            target = root / "v185-1.log"

            def malicious_swap(directory):
                same_bytes = target.read_bytes()
                replacement = root / "temporary-witness"
                replacement.write_bytes(same_bytes)
                old_inode = target.stat().st_ino
                os.replace(replacement, target)
                self.assertNotEqual(old_inode, target.stat().st_ino)
                return (10, 21, 159)

            with patch(
                "tools.check_map02_v190_native_log_stability.audit_replay",
                side_effect=malicious_swap,
            ):
                with self.assertRaisesRegex(ValueError, "changed during replay"):
                    audit_stability(root)

    def test_rejects_symlink_missing_and_oversized_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_private_native_logs(root)
            entry = root / "v186-4.log"
            real = root / "saved-original"
            entry.rename(real)
            entry.symlink_to(real)
            with self.assertRaises(ValueError):
                snapshot_directory(root)
            entry.unlink()
            entry.write_bytes(b"x" * 2_000_001)
            with self.assertRaises(ValueError):
                sample_file(entry)
            entry.unlink()
            with self.assertRaises(FileNotFoundError):
                snapshot_directory(root)

    def test_rejects_two_mode_labels_hardlinked_to_the_same_inode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_private_native_logs(root)
            target = root / "v186-8.log"
            target.unlink()
            os.link(root / "v186-7.log", target)
            with self.assertRaisesRegex(ValueError, "share an inode"):
                snapshot_directory(root)

    def test_real_pcsx_job_runs_provenance_after_v189_against_private_logs(self):
        parent = (ROOT / ".github/workflows/map02-v104-content-guard.yml").read_text()
        independent = (ROOT / ".github/workflows/map02-v190-native-log-stability.yml").read_text()
        self.assertIn(
            "python3 -m remaster.tools.check_map02_v190_native_log_stability "
            "--verify-dir proof/private", parent
        )
        self.assertLess(
            parent.index("VH189_NATIVE_LOG_REPLAY_PASS modes=10"),
            parent.index("VH190_NATIVE_LOG_STABILITY_PASS modes=10"),
        )
        self.assertIn(PASS_MARKER, parent)
        self.assertIn("test_map02_v190_native_log_stability.py", parent)
        self.assertIn("test_map02_v189_adversarial_native_logs.py", independent)
        self.assertIn("original_retail_executed=0", independent)

if __name__ == "__main__":
    unittest.main()
