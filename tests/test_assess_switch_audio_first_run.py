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
            "prior_csv_sha256_before": "a" * 64,
            "prior_csv_sha256_after": "a" * 64,
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
                         "OPERATOR_HASHES_MATCH")
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
