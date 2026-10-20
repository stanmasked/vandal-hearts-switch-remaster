"""External MAP02 receipt Ed25519 custody: positive and refusal fixtures.

All signatures here use temporary throwaway test keys. No production
custodian key or real game asset is checked into GitHub.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import map02_external_custody as custody
from tools import run_map02_sealed_gpu_receipt_chain as chain


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL 3 with Ed25519 required")
class ExternalCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vh-map02-custodian-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report = self.root / "report.json"
        self.request = self.root / "request.json"
        self.pub = self.root / "public.pem"
        self.key = self.root / "private-test.pem"
        self.sig = self.root / "request.sig"
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
        inspection = {
            "schema": "vh.map02.sealed-linked-gpu-consumption.v1",
            "source_objects_sha256": copy.deepcopy(primary["objects_sha256"]),
            "linked_object_sha256": "3" * 64,
            "linked_hash_verified_against_receipt": True,
            "linked_bytes_sealed_before_binutils": True,
            "hd_replacement_authorized": False,
        }
        parts = {"primary": primary, "linked": linked, "inspection": inspection}
        self.bundle = {
            "schema": chain.SCHEMA, **parts,
            "receipt_sha256": {
                name: hashlib.sha256(chain._canonical(value)).hexdigest()
                for name, value in parts.items()},
            "sealed_receipt_snapshots": 3,
            "receipt_chain_consistent": True,
            "intermediate_receipt_files_written": False,
            "externally_authenticated": False,
            "hd_replacement_authorized": False,
        }
        self.sha = self.write_report()
        self.commit = "a" * 40
        self.id = 39125496281
        self.attempt = 1
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(self.key)], capture_output=True, check=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.key),
                        "-pubout", "-out", str(self.pub)],
                       capture_output=True, check=True)
        der = subprocess.run(["openssl", "pkey", "-pubin",
                              "-in", str(self.pub), "-pubout",
                              "-outform", "DER"], capture_output=True,
                             check=True).stdout
        self.fingerprint = hashlib.sha256(der).hexdigest()

    def write_report(self):
        data = json.dumps(self.bundle, sort_keys=True).encode("utf-8")
        self.report.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def prepare_request(self):
        raw = custody.prepare(self.report, self.sha, commit=self.commit,
                              run_id=self.id, run_attempt=self.attempt)
        self.request.write_bytes(raw)
        return raw

    def sign(self):
        subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey",
                        str(self.key), "-rawin", "-in", str(self.request),
                        "-out", str(self.sig)], capture_output=True,
                       check=True)

    def check(self, **overrides):
        params = dict(
            trusted_public_key_sha256=self.fingerprint,
            receipt_path=self.report,
            expected_receipt_sha256=self.sha,
            expected_commit=self.commit, expected_run_id=self.id,
            expected_run_attempt=self.attempt)
        params.update(overrides)
        return custody.verify(self.request, self.sig, self.pub, **params)

    def test_unsigned_request_advertises_no_custodian(self):
        item = custody._request(self.prepare_request())
        self.assertFalse(item["independent_custodian_signed"])
        self.assertFalse(item["real_map02_gameplay_authenticated"])
        self.assertFalse(item["hd_replacement_authorized"])
        self.assertEqual(item["subject"]["receipt_sha256"], self.sha)

    def test_valid_ed25519_custodian_signature_verified(self):
        self.prepare_request()
        self.sign()
        result = self.check()
        self.assertTrue(result["independent_custodian_signature_verified"])
        self.assertEqual(result["trusted_custodian_public_key_sha256"],
                         self.fingerprint)
        self.assertFalse(result["real_map02_gameplay_authenticated"])

    def test_no_signature_fails_closed(self):
        self.prepare_request()
        with self.assertRaises((OSError, ValueError)):
            self.check()

    def test_wrong_key_fingerprint_refused(self):
        self.prepare_request()
        self.sign()
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            self.check(trusted_public_key_sha256="0" * 64)

    def test_receipt_swapped_between_validation_and_request_read_rejected(self):
        from unittest.mock import patch
        original = custody.published.verify_published
        def swapped(receipt, expected):
            result = original(receipt, expected)
            self.report.write_bytes(self.report.read_bytes() + b"modified")
            return result
        with patch.object(custody.published, "verify_published", side_effect=swapped):
            with self.assertRaisesRegex(ValueError, "changed after initial verification"):
                self.prepare_request()

    def test_receipt_swapped_between_validation_and_signature_check_rejected(self):
        from unittest.mock import patch
        self.prepare_request()
        self.sign()
        original = custody.published.verify_published
        def swapped(receipt, expected):
            result = original(receipt, expected)
            self.report.write_bytes(self.report.read_bytes() + b"modified")
            return result
        with patch.object(custody.published, "verify_published", side_effect=swapped):
            with self.assertRaisesRegex(ValueError, "changed after initial verification"):
                self.check()

    def test_missing_trust_anchor_refused(self):
        self.prepare_request()
        self.sign()
        with self.assertRaisesRegex(ValueError, "fingerprint missing"):
            self.check(trusted_public_key_sha256=None)

    def test_modified_signature_refused(self):
        self.prepare_request()
        self.sign()
        data = bytearray(self.sig.read_bytes())
        data[0] ^= 1
        self.sig.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "signature invalid"):
            self.check()

    def test_modified_request_before_signature_check_refused(self):
        self.prepare_request()
        self.sign()
        obj = json.loads(self.request.read_text())
        obj["subject"]["linked_elf_sha256"] = "e" * 64
        self.request.write_bytes(custody._canonical(obj))
        with self.assertRaisesRegex(ValueError, "linked ELF hash mismatch"):
            self.check()

    def test_source_commit_replay_refused(self):
        self.prepare_request()
        self.sign()
        with self.assertRaisesRegex(ValueError, "trusted launch identity"):
            self.check(expected_commit="b" * 40)

    def test_run_id_replay_refused(self):
        self.prepare_request()
        self.sign()
        with self.assertRaisesRegex(ValueError, "trusted launch identity"):
            self.check(expected_run_id=self.id + 1)

    def test_run_attempt_replay_refused(self):
        self.prepare_request()
        self.sign()
        with self.assertRaisesRegex(ValueError, "trusted launch identity"):
            self.check(expected_run_attempt=2)

    def test_changed_report_denied_even_if_request_signed(self):
        self.prepare_request()
        self.sign()
        self.bundle["linked"]["linked_object_sha256"] = "4" * 64
        self.write_report()
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            self.check()

    def test_misleading_custodian_claim_refused(self):
        raw = self.prepare_request()
        item = json.loads(raw)
        item["independent_custodian_signed"] = True
        self.request.write_bytes(custody._canonical(item))
        self.sign()
        with self.assertRaisesRegex(ValueError, "falsely claims verification"):
            self.check()

    def test_symlink_request_refused(self):
        self.prepare_request()
        self.sign()
        displaced = self.root / "displaced.json"
        self.request.rename(displaced)
        self.request.symlink_to(displaced)
        with self.assertRaisesRegex(ValueError, "symlink forbidden"):
            self.check()

    def test_duplicate_json_fields_refused(self):
        self.request.write_bytes(b'{"schema":"x","schema":"y"}\n')
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            custody._request(self.request.read_bytes())

    def test_noncanonical_whitespace_refused(self):
        raw = self.prepare_request()
        with self.assertRaisesRegex(ValueError, "noncanonical encoding"):
            custody._request(b" " + raw)

    def test_bad_ed25519_signature_size_refused(self):
        self.prepare_request()
        self.sign()
        self.sig.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "must be 64 bytes"):
            self.check()


if __name__ == "__main__":
    unittest.main()
