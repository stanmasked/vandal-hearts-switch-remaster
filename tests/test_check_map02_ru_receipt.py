"""Synthetic mutation tests: no protected game bytes or playable data."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.check_map02_ru_receipt import check_receipt, EXPECTED_HASHES


def fixture():
    return {
        "schema": 1,
        "kind": "LOCAL_MAP02_RU_SOURCE_RECONCILIATION",
        "source_project": "Vandal Hearts PS1 RU v1.6",
        "verified_source_sha256": True,
        "volume_id": "SLUS_00447",
        "existing_decoder_source_sha256": "a" * 64,
        "existing_comparison_source_sha256": "b" * 64,
        "prs": {
            "lba": 7116, "size_bytes": 22783,
            "declared_compressed_bytes": 22779, "unpacked_bytes": 187264,
        },
        "dat": {"lba": 6999, "size_bytes": 238336},
        "hashes": dict(EXPECTED_HASHES),
        "comparison": {
            "compared_bytes": 187264, "difference_count": 2,
            "first_differences": [
                {"offset": 74048, "record": 243, "within_record": 176,
                 "prs_value": 241, "dat_value": 98},
                {"offset": 97152, "record": 319, "within_record": 176,
                 "prs_value": 243, "dat_value": 150},
            ],
            "matches_prior_two_differences": True,
            "target_faces": [
                {"record": 243, "x": 19, "z": 8,
                 "prs_local_gfx": 241, "dat_local_gfx": 98},
                {"record": 319, "x": 11, "z": 11,
                 "prs_local_gfx": 243, "dat_local_gfx": 150},
            ],
        },
        "prior_source_comparison": {
            "prs_logical_matches": True, "prs_unpacked_matches": True,
            "dat_matches": True, "all_match": True,
        },
        "interpretation": "MATCHES_PRIOR_SOURCE_BYTES",
        "original_payload_exported": False,
    }


class RuMap02ReceiptTests(unittest.TestCase):
    def test_good_receipt_is_consistent_but_not_runtime_proof(self):
        report = check_receipt(fixture())
        self.assertTrue(report["source_receipt_consistent"])
        self.assertFalse(report["runtime_gfx_selection_verified"])
        self.assertFalse(report["disc_independently_rehashed_by_this_gate"])
        self.assertFalse(report["original_gameplay_authenticated"])

    def test_rejects_prs_digest_substitution(self):
        receipt = fixture()
        receipt["hashes"]["prs_file"] = receipt["hashes"]["dat_file"]
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_integer_in_place_of_true(self):
        receipt = fixture()
        receipt["verified_source_sha256"] = 1
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_short_difference_list(self):
        receipt = fixture()
        receipt["comparison"]["first_differences"].pop()
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_wrong_lba(self):
        receipt = fixture()
        receipt["prs"]["lba"] += 1
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_wrong_face(self):
        receipt = fixture()
        receipt["comparison"]["target_faces"][1]["x"] += 1
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_false_prior_digest_match(self):
        receipt = fixture()
        receipt["prior_source_comparison"]["all_match"] = False
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_rejects_nonobject_hashes(self):
        receipt = fixture()
        receipt["hashes"] = []
        with self.assertRaises(ValueError):
            check_receipt(receipt)

    def test_cli_accepts_and_prints_metadata_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "-m", "tools.check_map02_ru_receipt", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)["source_receipt_consistent"])
            self.assertNotIn("74048", run.stdout)

    def test_cli_rejects_false_success(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipt.json"
            receipt = fixture()
            receipt["comparison"]["difference_count"] = 0
            path.write_text(json.dumps(receipt), encoding="utf-8")
            run = subprocess.run(
                [sys.executable, "-m", "tools.check_map02_ru_receipt", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
