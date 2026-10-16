#!/usr/bin/env python3
"""Stage 221: synthetic, offline-only H01-H07 final review regression tests."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import report_switch_audio_acceptance_matrix as matrix  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_assess_switch_audio_first_run import FirstRunOperatorEvidenceTests  # noqa: E402


class AcceptanceMatrixTests(unittest.TestCase):
    def setUp(self):
        fixture = FirstRunOperatorEvidenceTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    @property
    def obs(self):
        return self.fixture.record

    def review(self, **opts):
        return matrix.build_matrix(self.fixture.root, self.obs, **opts)

    def scenarios(self, **opts):
        return {row["id"]: row for row in self.review(**opts)["scenarios"]}

    def cli(self, *flags):
        self.fixture.write_record()
        cmd = [
            sys.executable,
            str(ROOT / "tools" / "report_switch_audio_acceptance_matrix.py"),
            str(self.fixture.root), "--observations", str(self.fixture.observations),
            *flags,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, check=False)

    def rewrite_session(self, index, **fields):
        path = self.fixture.root / self.fixture.files[index]
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headings, rows = reader.fieldnames, list(reader)
        rows[-1].update({key: str(value) for key, value in fields.items()})
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headings)
            writer.writeheader()
            writer.writerows(rows)
        manifest_path = self.fixture.root / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        size, digest = bundle.digest_file(path)
        manifest["sessions"][index].update(size=size, sha256=digest)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        if index == 0:
            self.obs["prior_csv_sha256_before"] = digest
            self.obs["prior_csv_sha256_after"] = digest

    def test_complete_operator_claims_still_require_physical_signoff(self):
        result = self.review()
        self.assertEqual(result["schema"], matrix.SCHEMA)
        self.assertEqual(result["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual([r["id"] for r in result["scenarios"]],
                         ["H01", "H02", "H03", "H04", "H05", "H06", "H07"])
        self.assertEqual([r["status"] for r in result["scenarios"][:5]],
                         [matrix.READY] * 5)
        self.assertEqual([r["status"] for r in result["scenarios"][5:]],
                         [matrix.NOT_REQUIRED] * 2)
        self.assertEqual(result["retests"], [])
        self.assertEqual(result["manual_gate"]["decision"], "NEVER_AUTO_APPROVE")
        self.assertTrue(result["manual_gate"]["human_signoff_required"])

    def test_empty_or_unknown_operator_input_never_passes(self):
        first = self.obs["sessions"][0]
        first["physical_switch"] = "UNKNOWN"
        first["music_audible"] = "UNKNOWN"
        first["home_returns"] = None
        first["sleep_resumes"] = None
        first["continuous_minutes"] = None
        result = self.review()
        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertEqual(self.scenarios()["H01"]["status"], matrix.INCOMPLETE)
        self.assertEqual(self.scenarios()["H02"]["status"], matrix.INCOMPLETE)
        self.assertTrue(result["retests"])
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")

    def test_home_below_ten_gets_targeted_retest(self):
        self.obs["sessions"][1]["home_returns"] = 2
        result = self.review()
        self.assertEqual(self.scenarios()["H02"]["status"], matrix.INCOMPLETE)
        self.assertIn("HOME", next(a["action"] for a in result["retests"]
                                   if a["scenario"] == "H02"))

    def test_sleep_below_five_and_no_automatic_observation(self):
        self.obs["sessions"][1]["sleep_resumes"] = 1
        h03 = self.scenarios()["H03"]
        self.assertEqual(h03["status"], matrix.INCOMPLETE)
        self.assertEqual(h03["observed"]["csv_sleep_cycles"], "NOT_OBSERVABLE")

    def test_long_run_below_thirty_gets_retest(self):
        for row in self.obs["sessions"]:
            row["continuous_minutes"] = 29
        self.assertEqual(self.scenarios()["H04"]["status"], matrix.INCOMPLETE)

    def test_h05_unbound_legacy_operator_hashes_get_retest(self):
        self.obs["schema"] = "vh-switch-audio-first-run-operator/v1"
        del self.obs["prior_csv_path"]
        h05 = self.scenarios()["H05"]
        self.assertEqual(h05["status"], matrix.INCOMPLETE)
        self.assertEqual(h05["observed"]["retention"], "UNBOUND_LEGACY_OPERATOR_HASHES")

    def test_h05_wrong_prior_hash_gets_investigation(self):
        self.obs["prior_csv_sha256_after"] = "0" * 64
        result = self.review()
        self.assertEqual(self.scenarios()["H05"]["status"], matrix.INVESTIGATE)
        self.assertEqual(result["retests"][0]["scenario"], "H05")
        self.assertEqual(result["result"], "INVESTIGATE")

    def test_operator_reports_audio_artifact_investigation_first(self):
        self.obs["sessions"][0]["audio_artifacts"] = "HEARD"
        result = self.review()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertEqual(self.scenarios()["H01"]["status"], matrix.INVESTIGATE)
        self.assertEqual(self.scenarios()["H04"]["status"], matrix.INVESTIGATE)
        self.assertTrue(result["retests"])
        self.assertTrue(all(r["priority"] == matrix.INVESTIGATE for r in result["retests"]))

    def test_pcm_submit_failure_from_csv_requires_retest(self):
        self.rewrite_session(0, pcm_fail=2)
        result = self.review()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertEqual(self.scenarios()["H01"]["status"], matrix.INVESTIGATE)
        self.assertEqual(self.scenarios()["H04"]["status"], matrix.INVESTIGATE)
        self.assertIn("OBSERVED_PCM_HOME_FAULT",
                      {f["code"] for f in result["unresolved_operator_findings"]})

    def test_retained_home_failure_blocks_home_case(self):
        self.rewrite_session(0, home_fail=1)
        self.assertEqual(self.scenarios()["H02"]["status"], matrix.INVESTIGATE)

    def test_absent_exit_claimed_present_needs_investigation(self):
        self.rewrite_session(1, event="PERIODIC")
        result = self.review()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertEqual(self.scenarios()["H01"]["status"], matrix.INVESTIGATE)
        self.assertIn("CONTRADICTORY_EXIT",
                      {f["code"] for f in result["unresolved_operator_findings"]})

    def test_h06_is_optional_unless_explicitly_requested(self):
        self.assertEqual(self.scenarios()["H06"]["status"], matrix.NOT_REQUIRED)
        optional = self.review(require_h06=True)
        h06 = self.scenarios(require_h06=True)["H06"]
        self.assertEqual(h06["status"], matrix.INCOMPLETE)
        self.assertEqual(optional["result"], "INCONCLUSIVE")
        self.assertIn("NO_POWER_CUT", str(h06["observed"]))
        self.assertIn("non-destructive", h06["next_action"])

    def test_h07_requires_an_independent_second_build(self):
        self.assertEqual(self.scenarios()["H07"]["status"], matrix.NOT_REQUIRED)
        report = self.review(compare_builds=True)
        h07 = self.scenarios(compare_builds=True)["H07"]
        self.assertEqual(h07["status"], matrix.INCOMPLETE)
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertIn("2 independent", h07["next_action"])
        self.assertEqual(h07["observed"]["between_build_comparison"], "NOT_PROVIDED")

    def test_corrupt_csv_never_produces_review_matrix(self):
        (self.fixture.root / self.fixture.files[0]).write_bytes(b"broken")
        run = self.cli()
        self.assertEqual(run.returncode, 2)
        payload = json.loads(run.stdout)
        self.assertEqual(payload["result"], "INVALID_EVIDENCE")
        self.assertNotIn("scenarios", payload)
        self.assertEqual(payload["hardware_status"], "HARDWARE NOT TESTED")

    def test_wrong_build_id_fails_closed(self):
        self.obs["build_git_sha"] = "e" * 40
        run = self.cli()
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["result"], "INVALID_EVIDENCE")

    def test_cli_json_markdown_and_exit_zero_only_mean_generation(self):
        result = self.cli("--format", "json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        markdown = self.cli("--format", "markdown")
        self.assertEqual(markdown.returncode, 0, markdown.stderr)
        self.assertIn("HARDWARE NOT TESTED", markdown.stdout)
        self.assertIn("| H01 |", markdown.stdout)
        self.assertIn("| H07 |", markdown.stdout)
        self.assertIn("automatic PASS prohibited", markdown.stdout)

    def test_only_missing_retests_are_in_checklist_in_priority_order(self):
        self.obs["sessions"][1]["home_returns"] = 1
        self.obs["prior_csv_sha256_after"] = "0" * 64
        report = self.review()
        self.assertEqual(report["retests"][0]["scenario"], "H05")
        self.assertEqual(report["retests"][0]["priority"], matrix.INVESTIGATE)
        self.assertTrue(any(a["scenario"] == "H02" and a["priority"] == matrix.INCOMPLETE
                            for a in report["retests"]))

    def test_report_never_mutates_input_bundle_or_operator_file(self):
        self.fixture.write_record()
        before = {
            str(p.relative_to(self.fixture.root)): p.read_bytes()
            for p in self.fixture.root.rglob("*") if p.is_file()
        }
        operator_before = self.fixture.observations.read_bytes()
        self.review(require_h06=True, compare_builds=True)
        after = {
            str(p.relative_to(self.fixture.root)): p.read_bytes()
            for p in self.fixture.root.rglob("*") if p.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual(operator_before, self.fixture.observations.read_bytes())


if __name__ == "__main__":
    unittest.main()
