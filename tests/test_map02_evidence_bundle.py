"""Adversarial *synthetic-only* integrity tests for a self-contained NeXium ZIP.

These fixtures are NOT real screenshots and never count as runtime evidence.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import map02_evidence_bundle as bundle
from map02_candidate_receipt import make_receipt
from test_map02_cold_restart_oracle import fixtures


SOURCE = "a" * 40
TREE = "b" * 40


def prepare(folder: Path) -> None:
    fixtures(folder)
    (folder / bundle.NRO_NAME).write_bytes(b"NRO0 synthetic no retail game bytes")
    receipt = make_receipt(folder / bundle.NRO_NAME, SOURCE, TREE)
    (folder / "build-receipt.json").write_text(
        json.dumps(receipt), encoding="utf-8")
    from run_map02_nexium_cold_restart import evidence_manifest
    (folder / "capture-sha256-manifest.json").write_text(
        json.dumps(evidence_manifest(folder)), encoding="utf-8")
    for log in ("boot1_nexium.log", "boot2_nexium.log"):
        (folder / log).write_text("synthetic-only test log\n",
                                  encoding="utf-8")
    (folder / "result.log").write_text(
        bundle.PASS_GAME + "\nsynthetic fixture, not real NeXium\n",
        encoding="utf-8")
    (folder / "offline-audit.log").write_text(
        bundle.PASS_OFFLINE + "\nsynthetic fixture, not real NeXium\n",
        encoding="utf-8")
    (folder / "nexium-archive.sha256").write_text(
        "0" * 64 + "  nexium-linux-x86_64.tar.gz\n", encoding="utf-8")
    (folder / "nexium-executable.sha256").write_text(
        "0" * 64 + "  /tmp/nexium/nexium\n", encoding="utf-8")
    (folder / "nexium-release.json").write_text(
        '{"tag_name":"synthetic-test-only"}\n', encoding="utf-8")


class EvidenceBundleTests(unittest.TestCase):
    def test_complete_synthetic_bundle_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            value = bundle.create(folder, SOURCE, TREE)
            self.assertEqual(value["png_count"], 24)
            self.assertEqual(value["file_count"], 35)
            self.assertEqual(len(value["root_sha256"]), 64)
            self.assertEqual(bundle.verify(folder, SOURCE, TREE), value)

    def test_mutated_nro_is_rejected_even_if_pngs_still_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            (folder / bundle.NRO_NAME).write_bytes(b"NRO0 substituted bytes")
            with self.assertRaisesRegex(ValueError, "NRO SHA-256 mismatch"):
                bundle.verify(folder, SOURCE, TREE)

    def test_mutated_log_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            (folder / "boot1_nexium.log").write_text("tampered\n",
                                                       encoding="utf-8")
            with self.assertRaisesRegex(bundle.EvidenceError,
                                        "SHA-256 / file provenance mismatch"):
                bundle.verify(folder, SOURCE, TREE)

    def test_mutated_png_after_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            (folder / "boot2_bow_hit.png").write_bytes(b"not a PNG")
            with self.assertRaises((ValueError, OSError)):
                bundle.verify(folder, SOURCE, TREE)

    def test_source_identity_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            with self.assertRaisesRegex(ValueError, "source commit mismatch"):
                bundle.verify(folder, "c" * 40, TREE)

    def test_symlinked_nro_or_extraneous_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            real = folder / bundle.NRO_NAME
            renamed = folder / "real-original-nro"
            real.rename(renamed)
            real.symlink_to(renamed)
            with self.assertRaisesRegex(bundle.EvidenceError, "unexpected evidence|not regular"):
                bundle.create(folder, SOURCE, TREE)

    def test_extra_file_rejected_even_after_good_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            (folder / "untracked.iso").write_bytes(b"synthetic test only")
            with self.assertRaisesRegex(bundle.EvidenceError, "unexpected evidence"):
                bundle.verify(folder, SOURCE, TREE)

    def test_missing_capture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            (folder / "boot1_legacy.png").unlink()
            with self.assertRaisesRegex(bundle.EvidenceError, "incomplete"):
                bundle.create(folder, SOURCE, TREE)

    def test_duplicate_receipt_fields_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            path = folder / bundle.RECEIPT
            value = path.read_text(encoding="utf-8")
            value = value.replace('"schema_version": 1,',
                                  '"schema_version": 1, "schema_version": 1,')
            path.write_text(value, encoding="utf-8")
            with self.assertRaisesRegex(bundle.EvidenceError,
                                        "invalid or duplicate-field"):
                bundle.verify(folder, SOURCE, TREE)

    def test_tampered_root_digest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prepare(folder)
            bundle.create(folder, SOURCE, TREE)
            path = folder / bundle.RECEIPT
            value = json.loads(path.read_text(encoding="utf-8"))
            value["root_sha256"] = "0" * 64
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(bundle.EvidenceError,
                                        "SHA-256 / file provenance mismatch"):
                bundle.verify(folder, SOURCE, TREE)


if __name__ == "__main__":
    unittest.main()
