#!/usr/bin/env python3
"""Regression tests for integrated-NRO preflight (synthetic headers only)."""
from __future__ import annotations
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import verify_switch_integrated_nro_preflight as gate

SHA = "94d978da9cf52038bf5b8da3f2dec67c77d06700"

class TestIntegratedNroPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        data = bytearray(0x200)
        data[0x10:0x14] = b"NRO0"
        struct.pack_into("<I", data, 0x18, 0x200)
        for offset, start in ((0x20, 0x80), (0x28, 0xa0), (0x30, 0xc0)):
            struct.pack_into("<II", data, offset, start, 0x20)
        (self.root / gate.EXPECTED_NRO).write_bytes(data)
        self.digest = hashlib.sha256(data).hexdigest()
        self.hashfile = self.root / gate.EXPECTED_HASH_FILE
        self.hashfile.write_text(self.digest + "  build/vandal-hearts-prototype.nro\n")
        self.params = dict(git_sha=SHA, run_id=39022002964,
                           artifact_id=12097456224,
                           artifact_name=gate.EXPECTED_ARTIFACT,
                           expected_sha256=self.digest)

    def test_matching_bytes_only_allow_transfer_review(self):
        report = gate.check(self.root, **self.params)
        self.assertEqual(report["result"], "READY_FOR_SD_TRANSFER_REVIEW")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["physical_switch_execution"], "NOT_ATTESTED")

    def test_wrong_pinned_hash_rejected(self):
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **dict(self.params, expected_sha256="0"*64))

    def test_modified_nro_rejected(self):
        with (self.root / gate.EXPECTED_NRO).open("ab") as file:
            file.write(b"modified")
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **self.params)

    def test_hash_for_wrong_filename_rejected(self):
        self.hashfile.write_text(self.digest + "  another.nro\n")
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **self.params)

    def test_wrong_artifact_rejected(self):
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **dict(self.params, artifact_name="audout-audio"))

    def test_invalid_run_identity_rejected(self):
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **dict(self.params, git_sha="short"))
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **dict(self.params, run_id=0))

    def test_symlink_hash_rejected(self):
        self.hashfile.unlink()
        elsewhere = self.root / "other.txt"
        elsewhere.write_text(self.digest + "  build/vandal-hearts-prototype.nro\n")
        self.hashfile.symlink_to(elsewhere)
        with self.assertRaises(gate.PreflightError):
            gate.check(self.root, **self.params)

    def test_truncated_nro_rejected(self):
        data = bytearray((self.root / gate.EXPECTED_NRO).read_bytes()[:0x40])
        (self.root / gate.EXPECTED_NRO).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        self.hashfile.write_text(digest + "  build/vandal-hearts-prototype.nro\n")
        with self.assertRaises(Exception):
            gate.check(self.root, **dict(self.params, expected_sha256=digest))

if __name__ == "__main__":
    unittest.main()
