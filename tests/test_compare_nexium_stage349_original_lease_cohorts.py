#!/usr/bin/env python3
"""Stage349 synthetic positive/negative controls; never original-run evidence."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_nexium_guest_lease_reconciliation_stage348 import KEYS, audit_source
from compare_nexium_stage349_original_lease_cohorts import (
    COUNTS, compare_originals, main, read_original,
)


class Stage349Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, stem="a", acquired=5, released=4, abandoned=1,
                submitted=4, busy=0, mismatched=0, failed=0):
        values = dict(
            software_lease_only=1,
            lease_pages_acquired=acquired,
            lease_pages_released=released,
            abandoned_sessions=abandoned,
            busy_begin_rejections=busy,
            mismatched_releases=mismatched,
            accepted_pages_submitted=submitted,
            submit_failures=failed,
        )
        raw = b"scope,value\n" + b"".join(
            f"{key},{values[key]}\n".encode("ascii") for key in KEYS
        )
        csv = self.root / f"{stem}.csv"
        receipt = self.root / f"{stem}.json"
        csv.write_bytes(raw)
        receipt.write_text(json.dumps(audit_source(raw)), encoding="utf-8")
        return csv, receipt, hashlib.sha256(raw).hexdigest()

    def read(self, f):
        return read_original(*f)

    def test_original_distinct_cohorts_are_balanced(self):
        a = self.read(self.fixture("a"))
        b = self.read(self.fixture("b", 7, 7, 0, 7, busy=2))
        doc = compare_originals(a, b, 39292707481, 39292997818)
        self.assertEqual(doc["second_minus_first"]["lease_pages_acquired"], 2)
        self.assertEqual(doc["second_minus_first"]["abandoned_sessions"], -1)
        self.assertTrue(doc["guest_software_ownership_balanced_in_both"])
        self.assertFalse(doc["DAC_or_speaker_playback_verified"])

    def test_reject_duplicate_source_bytes(self):
        a = self.read(self.fixture())
        with self.assertRaises(ValueError):
            compare_originals(a, a, 1, 2)

    def test_reject_duplicate_run_ids(self):
        a = self.read(self.fixture("a"))
        b = self.read(self.fixture("b", 7, 7, 0, 7))
        with self.assertRaises(ValueError):
            compare_originals(a, b, 1, 1)

    def test_reject_missing_run_ids(self):
        a = self.read(self.fixture("a"))
        b = self.read(self.fixture("b", 7, 7, 0, 7))
        with self.assertRaises(ValueError):
            compare_originals(a, b, 0, 2)

    def test_wrong_source_sha_pin_rejected(self):
        a = self.fixture()
        with self.assertRaises(ValueError):
            read_original(a[0], a[1], "0" * 64)

    def test_non_lowercase_sha_pin_rejected(self):
        a = self.fixture()
        with self.assertRaises(ValueError):
            read_original(a[0], a[1], "BADPIN")

    def test_source_csv_mutation_rejected(self):
        a = self.fixture()
        a[0].write_bytes(a[0].read_bytes() + b"extra\n")
        with self.assertRaises(ValueError):
            self.read(a)

    def test_receipt_wrong_sha_rejected(self):
        a = self.fixture()
        receipt = json.loads(a[1].read_text())
        receipt["original_guest_software_lease_csv_sha256"] = "0" * 64
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.read(a)

    def test_receipt_forged_count_rejected(self):
        a = self.fixture()
        receipt = json.loads(a[1].read_text())
        receipt["lease_pages_released"] += 1
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.read(a)

    def test_receipt_fake_hardware_proof_rejected(self):
        a = self.fixture()
        receipt = json.loads(a[1].read_text())
        receipt["physical_Nintendo_Switch_audio_tested"] = True
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.read(a)

    def test_receipt_forged_original_observation_rejected(self):
        a = self.fixture()
        receipt = json.loads(a[1].read_text())
        receipt["original_guest_software_lease_source_observed"] = False
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.read(a)

    def test_receipt_bool_substituted_for_count_rejected(self):
        a = self.fixture()
        receipt = json.loads(a[1].read_text())
        receipt["lease_pages_released"] = True
        a[1].write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            self.read(a)

    def test_symlinked_original_csv_rejected(self):
        a = self.fixture()
        linked = self.root / "linked.csv"
        linked.symlink_to(a[0])
        with self.assertRaises(ValueError):
            read_original(linked, a[1], a[2])

    def test_symlinked_parent_directory_rejected(self):
        a = self.fixture()
        linked = self.root / "linked_dir"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            read_original(linked / a[0].name, a[1], a[2])

    def test_source_unbalanced_rejected(self):
        a = self.fixture()
        a[0].write_bytes(a[0].read_bytes().replace(b"abandoned_sessions,1\n",
                                                   b"abandoned_sessions,2\n"))
        newpin = hashlib.sha256(a[0].read_bytes()).hexdigest()
        with self.assertRaises(Exception):
            read_original(a[0], a[1], newpin)

    def test_missing_receipt_rejected(self):
        a = self.fixture()
        a[1].unlink()
        with self.assertRaises(ValueError):
            self.read(a)

    def test_full_cli_creates_only_comparison_receipt(self):
        a = self.fixture("a")
        b = self.fixture("b", 7, 7, 0, 7)
        output = self.root / "comparison.json"
        args = [
            "--first-csv", str(a[0]), "--first-receipt", str(a[1]),
            "--first-sha256", a[2], "--first-run-id", "1",
            "--second-csv", str(b[0]), "--second-receipt", str(b[1]),
            "--second-sha256", b[2], "--second-run-id", "2",
            "--output", str(output),
        ]
        self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(output.read_text())["first_original"]["abandoned_sessions"], 1)
        self.assertEqual(main(args), 2)  # fail closed, do not overwrite receipt


if __name__ == "__main__":
    unittest.main()
