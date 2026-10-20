"""Adversarial portable tests: no real NRO or copyrighted game data used."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import map02_candidate_receipt as proof

COMMIT = "a" * 40
TREE = "b" * 40
OTHER = "c" * 40
FAKE_NRO = b"public synthetic fixture, not an executable Switch NRO\x00" * 8


class CandidateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-nro-receipt-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.nro = self.root / proof.NRO_NAME
        self.receipt = self.root / "receipt.json"
        self.nro.write_bytes(FAKE_NRO)
        self.entry = proof.make_receipt(self.nro, COMMIT, TREE)
        self.write(self.entry)

    def write(self, entry):
        self.receipt.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    def test_valid_fixture_is_sha256_bound(self):
        r = proof.verify(self.nro, self.receipt, COMMIT, TREE)
        self.assertEqual(r, self.entry)
        self.assertEqual(r["size_bytes"], len(FAKE_NRO))
        self.assertEqual(len(r["sha256"]), 64)

    def test_change_one_byte_same_size_is_rejected(self):
        content = bytearray(FAKE_NRO)
        content[3] ^= 1
        self.nro.write_bytes(content)
        with self.assertRaisesRegex(proof.ReceiptError, "SHA-256 mismatch"):
            proof.verify(self.nro, self.receipt, COMMIT, TREE)

    def test_changed_size_is_rejected(self):
        self.nro.write_bytes(FAKE_NRO[:-1])
        with self.assertRaisesRegex(proof.ReceiptError, "byte count mismatch"):
            proof.verify(self.nro, self.receipt, COMMIT, TREE)

    def test_wrong_source_commit_is_rejected(self):
        with self.assertRaisesRegex(proof.ReceiptError, "source commit mismatch"):
            proof.verify(self.nro, self.receipt, OTHER, TREE)

    def test_wrong_source_tree_is_rejected(self):
        with self.assertRaisesRegex(proof.ReceiptError, "source tree mismatch"):
            proof.verify(self.nro, self.receipt, COMMIT, OTHER)

    def test_no_zero_byte_or_wrong_filename(self):
        self.nro.write_bytes(b"")
        with self.assertRaisesRegex(proof.ReceiptError, "zero-byte"):
            proof.make_receipt(self.nro, COMMIT, TREE)
        other = self.root / "other-name.nro"
        other.write_bytes(FAKE_NRO)
        with self.assertRaisesRegex(proof.ReceiptError, "filename"):
            proof.make_receipt(other, COMMIT, TREE)

    def test_symlink_nro_and_receipt_are_rejected(self):
        link = self.root / "nested"
        link.mkdir()
        (link / proof.NRO_NAME).symlink_to(self.nro)
        with self.assertRaisesRegex(proof.ReceiptError, "symlink"):
            proof.make_receipt(link / proof.NRO_NAME, COMMIT, TREE)
        symlink = self.root / "receipt-alias.json"
        symlink.symlink_to(self.receipt)
        with self.assertRaisesRegex(proof.ReceiptError, "symlink"):
            proof.parse_receipt(symlink)

    def test_duplicate_json_key_or_unexpected_field(self):
        self.receipt.write_text(
            '{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(proof.ReceiptError, "duplicate"):
            proof.parse_receipt(self.receipt)
        changed = dict(self.entry, original_ps1_disc="no")
        self.write(changed)
        with self.assertRaisesRegex(proof.ReceiptError, "unexpected"):
            proof.parse_receipt(self.receipt)

    def test_booleans_and_invalid_digests_rejected(self):
        self.write(dict(self.entry, size_bytes=True))
        with self.assertRaisesRegex(proof.ReceiptError, "byte count"):
            proof.parse_receipt(self.receipt)
        self.write(dict(self.entry, sha256="A" * 64))
        with self.assertRaisesRegex(proof.ReceiptError, "SHA-256 format"):
            proof.parse_receipt(self.receipt)

    def test_kind_and_commit_sha_format_rejected(self):
        self.write(dict(self.entry, kind="retail-game-image"))
        with self.assertRaisesRegex(proof.ReceiptError, "kind"):
            proof.parse_receipt(self.receipt)
        self.write(dict(self.entry, source_commit="invalid"))
        with self.assertRaisesRegex(proof.ReceiptError, "source_commit"):
            proof.parse_receipt(self.receipt)

    def test_oversized_and_malformed_receipts_rejected(self):
        self.receipt.write_text(" " * 8200, encoding="utf-8")
        with self.assertRaisesRegex(proof.ReceiptError, "large"):
            proof.parse_receipt(self.receipt)
        self.receipt.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(proof.ReceiptError, "malformed"):
            proof.parse_receipt(self.receipt)

    def test_cli_roundtrip_and_tamper_failure(self):
        script = Path(proof.__file__)
        def invoke(action):
            return subprocess.run([
                sys.executable, str(script), action,
                "--nro", str(self.nro),
                "--receipt", str(self.receipt),
                "--source-commit", COMMIT, "--source-tree", TREE,
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(invoke("create").returncode, 0)
        completed = invoke("verify")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("VH_MAP02_CANDIDATE_RECEIPT_PASS", completed.stdout)
        self.nro.write_bytes(FAKE_NRO + b"tampered")
        broken = invoke("verify")
        self.assertNotEqual(broken.returncode, 0)
        self.assertIn("VH_MAP02_CANDIDATE_RECEIPT_FAIL", broken.stderr)


if __name__ == "__main__":
    unittest.main()
