"""Synthetic independent-job verification of uploaded MAP02 receipts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import run_map02_sealed_gpu_receipt_chain as chain
from tools import verify_map02_published_receipt as audit


class PublishedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="map02-published-")
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "receipt.json"
        primary = {
            "schema": "vh.map02.sealed-gpu-make-objects.v1",
            "objects_sha256": {"libgpu.o": "1" * 64, "pc_raster.o": "2" * 64},
            "actual_make_children_kernel_attested": True,
            "hd_replacement_authorized": False,
        }
        linked = {
            "schema": "vh.map02.sealed-linked-gpu-object.v1",
            "source_objects_sha256": copy.deepcopy(primary["objects_sha256"]),
            "linked_object_sha256": "3" * 64,
            "binutils_consumed_sealed_objects": True,
            "hd_replacement_authorized": False,
        }
        inspected = {
            "schema": "vh.map02.sealed-linked-gpu-consumption.v1",
            "source_objects_sha256": copy.deepcopy(primary["objects_sha256"]),
            "linked_object_sha256": "3" * 64,
            "linked_hash_verified_against_receipt": True,
            "linked_bytes_sealed_before_binutils": True,
            "hd_replacement_authorized": False,
        }
        self.bundle = {
            "schema": chain.SCHEMA,
            "primary": primary, "linked": linked, "inspection": inspected,
            "receipt_sha256": {
                role: hashlib.sha256(chain._canonical(item)).hexdigest()
                for role, item in (("primary", primary), ("linked", linked),
                                   ("inspection", inspected))},
            "sealed_receipt_snapshots": 3,
            "receipt_chain_consistent": True,
            "intermediate_receipt_files_written": False,
            "externally_authenticated": False,
            "hd_replacement_authorized": False,
        }

    def write(self):
        raw = json.dumps(self.bundle, sort_keys=True).encode("utf-8")
        self.file.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_published_report_matches_external_commitment(self):
        digest = self.write()
        result = audit.verify_published(self.file, digest)
        self.assertTrue(result["caller_supplied_sha256_matched"])
        self.assertTrue(result["receipt_chain_consistent"])
        self.assertEqual(result["three_embedded_receipts_checked"], 3)
        self.assertFalse(result["independent_digital_signature_verified"])

    def test_whole_bundle_forgery_cannot_match_original_job_digest(self):
        trusted = self.write()
        self.bundle["primary"]["objects_sha256"]["libgpu.o"] = "f" * 64
        for stage in ("linked", "inspection"):
            self.bundle[stage]["source_objects_sha256"]["libgpu.o"] = "f" * 64
        for role in ("primary", "linked", "inspection"):
            self.bundle["receipt_sha256"][role] = hashlib.sha256(
                chain._canonical(self.bundle[role])).hexdigest()
        self.write()
        with self.assertRaisesRegex(ValueError, "SHA-256 differs from job commitment"):
            audit.verify_published(self.file, trusted)

    def test_embedded_receipt_digest_mutation_refused(self):
        expected = self.write()
        self.bundle["receipt_sha256"]["primary"] = "0" * 64
        changed = self.write()
        self.assertNotEqual(expected, changed)
        with self.assertRaisesRegex(ValueError, "embedded receipt digest differs"):
            audit.verify_published(self.file, changed)

    def test_inconsistent_receipt_link_refused_even_with_new_root_hash(self):
        self.bundle["linked"]["source_objects_sha256"]["libgpu.o"] = "f" * 64
        self.bundle["receipt_sha256"]["linked"] = hashlib.sha256(
            chain._canonical(self.bundle["linked"])).hexdigest()
        digest = self.write()
        with self.assertRaisesRegex(ValueError, "chain receipt hashes inconsistent"):
            audit.verify_published(self.file, digest)

    def test_false_security_flag_rejected(self):
        self.bundle["externally_authenticated"] = True
        digest = self.write()
        with self.assertRaisesRegex(ValueError, "security flags invalid"):
            audit.verify_published(self.file, digest)

    def test_symlinked_report_refused(self):
        digest = self.write()
        link = Path(self.tmp.name) / "alias.json"
        link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, "cannot be a symlink"):
            audit.verify_published(link, digest)

    def test_missing_expected_digest_refused(self):
        self.write()
        with self.assertRaisesRegex(ValueError, "expected external SHA-256"):
            audit.verify_published(self.file, None)

    def test_duplicate_json_fields_rejected(self):
        raw = b'{"schema":"x","schema":"y"}'
        self.file.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
            audit.verify_published(self.file, hashlib.sha256(raw).hexdigest())

    def test_nonfinite_json_refused(self):
        raw = b'{"schema":NaN}'
        self.file.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            audit.verify_published(self.file, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
