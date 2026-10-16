#!/usr/bin/env python3
"""Stage 219 regressions: all inputs synthetic; no physical Switch or SD."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import assess_switch_audio_first_run as assess  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_verify_switch_audio_bundle import (  # noqa: E402
    synthetic_structural_nro, write_session,
)


def operator_session(csv_path, ident, minutes=35, home=5, sleep=3):
    return {
        "id": ident,
        "csv": csv_path,
        "physical_switch": "YES",
        "launch_mode": "APPLICATION",
        "audio_output": "HANDHELD",
        "music_audible": "YES",
        "audio_artifacts": "NONE",
        "home_returns": home,
        "sleep_resumes": sleep,
        "continuous_minutes": minutes,
        "normal_exit": "YES",
        "notes": "SYNTHETIC fixture; not physical playback",
    }


class FirstRunOperatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.root = self.base / "evidence"
        (self.root / "nro").mkdir(parents=True)
        (self.root / "nro" / "vandal-hearts-prototype.nro").write_bytes(
            synthetic_structural_nro())
        self.files = [
            "session-01/audio-diagnostics-0000.csv",
            "session-02/audio-diagnostics-0001.csv",
        ]
        write_session(self.root / self.files[0], 1250)
        write_session(self.root / self.files[1], 1350)
        bundle.create(self.root, "nro/vandal-hearts-prototype.nro",
                      self.files, "d" * 40, "")
        self.record = {
            "schema": assess.SCHEMA,
            "build_git_sha": "d" * 40,
            "nro_sha256": bundle.digest_file(
                self.root / "nro" / "vandal-hearts-prototype.nro")[1],
            "sessions": [
                operator_session(self.files[0], "first", 35, 5, 3),
                operator_session(self.files[1], "second", 25, 5, 2),
            ],
            "prior_csv_path": self.files[0],
            "prior_csv_sha256_before": bundle.digest_file(self.root / self.files[0])[1],
            "prior_csv_sha256_after": bundle.digest_file(self.root / self.files[0])[1],
        }
        self.observations = self.base / "operator.json"

    def write_record(self):
        self.observations.write_text(json.dumps(self.record), encoding="utf-8")

    def review(self):
        self.write_record()
        return assess.assess(self.root, assess.read_observations(self.observations))

    def test_claimed_all_scenarios_still_not_hardware_pass(self):
        result = self.review()
        self.assertEqual(result["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["scenario_coverage"]["H02_home_operator_total"], 10)
        self.assertEqual(result["scenario_coverage"]["H03_sleep_operator_total"], 5)
        self.assertTrue(result["scenario_coverage"]["H01_two_different_csv_1000_pages_each"])
        self.assertEqual(result["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "FILE_BOUND_OPERATOR_HASHES_MATCH")
        self.assertEqual(result["scenario_coverage"]["H05_independent_SD_readback"],
                         "NOT_ATTESTED")
        self.assertIn("not authenticated", result["limitations"])

    def test_missing_observations_are_inconclusive(self):
        self.record["sessions"][0]["music_audible"] = "UNKNOWN"
        self.record["sessions"][1]["sleep_resumes"] = None
        self.assertEqual(self.review()["result"], "INCONCLUSIVE")
        self.assertEqual(self.review()["hardware_status"], "HARDWARE NOT TESTED")

    def test_audible_dropout_or_unsafe_exit_needs_investigation(self):
        for field, value in (
                ("music_audible", "NO"), ("audio_artifacts", "HEARD"),
                ("normal_exit", "NO"), ("physical_switch", "NO")):
            with self.subTest(field=field):
                original = self.record["sessions"][0][field]
                self.record["sessions"][0][field] = value
                self.assertEqual(self.review()["result"], "INVESTIGATE")
                self.record["sessions"][0][field] = original

    def test_observed_pcm_and_home_faults_require_investigation(self):
        # A malformed/changed CSV cannot be silently counted as clean.
        path = self.root / self.files[0]
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        fields = list(rows[0])
        rows[-1]["pcm_fail"] = "2"
        rows[-1]["home_fail"] = "1"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = self.root / bundle.MANIFEST_NAME
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        size, sha = bundle.digest_file(path)
        metadata["sessions"][0].update(size=size, sha256=sha)
        manifest_path.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.review()["result"], "INVESTIGATE")

    def test_insufficient_home_and_sleep_do_not_imply_success(self):
        self.record["sessions"][1]["home_returns"] = 3
        self.assertEqual(self.review()["result"], "INCONCLUSIVE")
        self.record["sessions"][1]["home_returns"] = 5
        self.record["sessions"][0]["sleep_resumes"] = 1
        self.assertEqual(self.review()["result"], "INCONCLUSIVE")

    def test_less_than_thirty_continuous_minutes_is_inconclusive(self):
        self.record["sessions"][0]["continuous_minutes"] = 29
        self.assertEqual(self.review()["result"], "INCONCLUSIVE")

    def test_prior_csv_retention_mismatch_is_a_problem(self):
        self.record["prior_csv_sha256_after"] = "b" * 64
        result = self.review()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertEqual(result["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "OPERATOR_HASHES_DIFFER")

    def test_no_prior_csv_hashes_is_inconclusive(self):
        self.record["prior_csv_sha256_before"] = None
        self.record["prior_csv_sha256_after"] = None
        self.assertEqual(self.review()["result"], "INCONCLUSIVE")

    def test_v1_equal_hashes_no_longer_suffice_for_h05(self):
        self.record["schema"] = assess.SCHEMA_V1
        del self.record["prior_csv_path"]
        result = self.review()
        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertEqual(result["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "UNBOUND_LEGACY_OPERATOR_HASHES")
        self.assertIn("H05_UNBOUND", {x["code"] for x in result["consistency_findings"]})

    def test_v2_matching_hash_without_path_is_inconclusive(self):
        self.record["prior_csv_path"] = None
        report = self.review()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertEqual(report["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "UNBOUND_LEGACY_OPERATOR_HASHES")

    def test_v2_unknown_h05_path_is_inconclusive(self):
        self.record["prior_csv_path"] = "missing/audio-diagnostics-9999.csv"
        report = self.review()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertEqual(report["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "PRIOR_CSV_NOT_IN_BUNDLE")

    def test_h05_cannot_use_newest_csv_as_prior_record(self):
        newer = self.files[1]
        digest = bundle.digest_file(self.root / newer)[1]
        self.record["prior_csv_path"] = newer
        self.record["prior_csv_sha256_before"] = digest
        self.record["prior_csv_sha256_after"] = digest
        review = self.review()
        self.assertEqual(review["result"], "INCONCLUSIVE")
        self.assertEqual(review["scenario_coverage"]["H05_prior_csv_operator_hashes"],
                         "H05_SEQUENCE_NOT_ESTABLISHED")
        self.assertIn("H05_ORDER_UNCONFIRMED",
                      {x["code"] for x in review["consistency_findings"]})

    def test_h05_pair_matching_each_other_but_not_file_requires_investigation(self):
        self.record["prior_csv_sha256_before"] = "e" * 64
        self.record["prior_csv_sha256_after"] = "e" * 64
        report = self.review()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("H05_VERIFIED_BYTES_MISMATCH",
                      {x["code"] for x in report["consistency_findings"]})

    def test_historical_fault_in_first_row_not_hidden_by_zero_increments(self):
        path = self.root / self.files[0]
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        for row in rows:
            row["pcm_fail"] = "3"
            row["home_fail"] = "2"
            row["lease_fail"] = "1"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest_file = self.root / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        size, sha = bundle.digest_file(path)
        manifest["sessions"][0].update(size=size, sha256=sha)
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        self.record["prior_csv_sha256_before"] = sha
        self.record["prior_csv_sha256_after"] = sha
        report = self.review()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertEqual(report["sessions"][0]["fault_counter_baseline"],
                         {"pcm_fail": 3, "home_fail": 2, "lease_fail": 1})
        self.assertIn("HISTORICAL_OR_RETAINED_ERROR",
                      {x["code"] for x in report["consistency_findings"]})

    def test_missing_csv_exit_vs_operator_normal_exit_is_conflict(self):
        path = self.root / self.files[0]
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        rows[-1]["event"] = "PERIODIC"
        rows[-1]["status"] = "1"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest_file = self.root / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        size, sha = bundle.digest_file(path)
        manifest["sessions"][0].update(size=size, sha256=sha)
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        self.record["prior_csv_sha256_before"] = sha
        self.record["prior_csv_sha256_after"] = sha
        report = self.review()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("CONTRADICTORY_EXIT",
                      {x["code"] for x in report["consistency_findings"]})

    def test_unknown_h05_path_type_is_rejected_at_schema_boundary(self):
        for value in ([], {}, True, "../other.txt", "fake.nro"):
            self.record["prior_csv_path"] = value
            self.write_record()
            with self.subTest(value=value), self.assertRaisesRegex(
                    assess.OperatorError, "prior_csv_path"):
                assess.read_observations(self.observations)

    def test_zero_home_claim_conflicting_with_retained_home_counter(self):
        # Counter increase is a resume, not unambiguous proof of a HOME press.
        path = self.root / self.files[0]
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, rows = reader.fieldnames, list(reader)
        rows[-1]["home_resumes"] = "1"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        manifest_file = self.root / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        size, sha = bundle.digest_file(path)
        manifest["sessions"][0].update(size=size, sha256=sha)
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        self.record["prior_csv_sha256_before"] = sha
        self.record["prior_csv_sha256_after"] = sha
        self.record["sessions"][0]["home_returns"] = 0
        self.record["sessions"][1]["home_returns"] = 10
        report = self.review()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertIn("UNEXPLAINED_HOME_COUNTER",
                      {x["code"] for x in report["consistency_findings"]})

    def test_wrong_binary_commit_is_rejected(self):
        self.record["build_git_sha"] = "e" * 40
        with self.assertRaisesRegex(assess.OperatorError, "another NRO/build"):
            self.review()

    def test_duplicate_csv_or_id_is_rejected(self):
        self.record["sessions"][1]["id"] = "first"
        self.write_record()
        with self.assertRaisesRegex(assess.OperatorError, "repeated"):
            assess.read_observations(self.observations)
        self.record["sessions"][1]["id"] = "second"
        self.record["sessions"][1]["csv"] = self.files[0]
        self.write_record()
        with self.assertRaisesRegex(assess.OperatorError, "repeated"):
            assess.read_observations(self.observations)

    def test_no_fabricated_unlisted_csv_is_accepted(self):
        self.record["sessions"][1]["csv"] = "session-03/audio-diagnostics-9999.csv"
        with self.assertRaisesRegex(assess.OperatorError, "CSV coverage"):
            self.review()

    def test_duplicate_json_keys_and_forged_status_are_rejected(self):
        self.observations.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(bundle.BundleError):
            assess.read_observations(self.observations)
        self.record["hardware_status"] = "PASS"
        self.write_record()
        with self.assertRaisesRegex(assess.OperatorError, "schema fields"):
            assess.read_observations(self.observations)

    def test_invalid_numbers_and_missing_fields_are_rejected(self):
        for value in (-1, True, "10", 10001):
            self.record["sessions"][0]["home_returns"] = value
            self.write_record()
            with self.subTest(value=value), self.assertRaisesRegex(
                    assess.OperatorError, "home_returns"):
                assess.read_observations(self.observations)
        self.record["sessions"][0]["home_returns"] = 5
        del self.record["sessions"][0]["normal_exit"]
        self.write_record()
        with self.assertRaisesRegex(assess.OperatorError, "session fields"):
            assess.read_observations(self.observations)

    def test_unhashable_enum_value_is_a_clean_validation_error(self):
        for field in ("music_audible", "audio_artifacts", "launch_mode",
                      "audio_output", "normal_exit"):
            original = self.record["sessions"][0][field]
            self.record["sessions"][0][field] = ["MALFORMED"]
            self.write_record()
            with self.subTest(field=field), self.assertRaisesRegex(
                    assess.OperatorError, "invalid " + field):
                assess.read_observations(self.observations)
            self.record["sessions"][0][field] = original

    def test_modified_immutable_csv_causes_failure(self):
        self.write_record()
        path = self.root / self.files[0]
        path.write_bytes(path.read_bytes() + b"TAMPER")
        with self.assertRaisesRegex(bundle.BundleError, "SHA-256 mismatch"):
            assess.assess(self.root, assess.read_observations(self.observations))

    def test_operator_file_is_outside_manifest_evidence(self):
        self.write_record()
        cli = [sys.executable, str(ROOT / "tools" /
                                   "assess_switch_audio_first_run.py"),
               str(self.root), "--observations", str(self.observations)]
        run = subprocess.run(cli, check=False, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        self.record["sessions"][0]["music_audible"] = "NO"
        self.write_record()
        run = subprocess.run(cli, check=False, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(json.loads(run.stdout)["result"], "INVESTIGATE")
        self.record["build_git_sha"] = "f" * 40
        self.write_record()
        run = subprocess.run(cli, check=False, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
