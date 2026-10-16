#!/usr/bin/env python3
"""Host-only regression tests for the stage 215 physical-audio evidence report."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(ROOT / "tools"))

import report_switch_audio_hardware as report  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_verify_switch_audio_bundle import (  # noqa: E402
    synthetic_structural_nro,
    write_session,
)


def adjust_csv(path: Path, **changes: int | str) -> None:
    with path.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.DictReader(input_file)
        fields = reader.fieldnames
        rows = list(reader)
    assert fields is not None
    rows[-1].update({name: str(value) for name, value in changes.items()})
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class HardwareReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "nro").mkdir()
        (self.root / "nro" / "game.nro").write_bytes(synthetic_structural_nro())
        self.files = [
            "session-01/audio-diagnostics-0000.csv",
            "session-02/audio-diagnostics-0001.csv",
        ]
        write_session(self.root / self.files[0], 1250)
        write_session(self.root / self.files[1], 1420)

    def manifest(self, sessions=None):
        return bundle.create(
            self.root, "nro/game.nro", self.files if sessions is None else sessions,
            "c" * 40, "https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/1234",
        )

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "report_switch_audio_hardware.py"),
             str(self.root), *args],
            text=True, capture_output=True, check=False,
        )

    def test_clean_sessions_are_manual_review_not_hardware_pass(self):
        self.manifest()
        data = report.review(self.root)
        self.assertEqual(data["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(data["telemetry_readiness"], "ENOUGH_DATA_FOR_MANUAL_REVIEW")
        self.assertEqual(data["report_triage"], "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(data["session_count"], 2)
        self.assertEqual(data["sessions"][0]["pcm"]["observed_pages"], 1250)
        self.assertEqual(data["file_integrity"]["prior_sd_file_preservation"],
                         "NOT_OBSERVABLE")
        self.assertEqual(data["sessions"][1]["resume"]["sleep_cycles"],
                         "NOT_SEPARATELY_OBSERVABLE")
        self.assertTrue(all(value == report.MANUAL_ONLY for value
                            in data["manual_acceptance"].values()))
        self.assertEqual(data["build"]["git_sha_self_reported"], "c" * 40)
        self.assertEqual(data["file_integrity"]["build_provenance"],
                         "SELF_REPORTED_UNVERIFIED")
        self.assertNotIn('"hardware_status": "PASS"', json.dumps(data))

    def test_faulted_pcm_home_and_lease_are_separated(self):
        adjust_csv(self.root / self.files[0], pcm_fail=3, lease_fail=2,
                   home_fail=4, home_resumes=12, pcm_restart=2, home_reopen=3,
                   home_recover=1)
        self.manifest()
        data = report.review(self.root)
        s = data["sessions"][0]
        self.assertEqual(s["pcm"]["submit_failures"], 3)
        self.assertEqual(s["pcm"]["lease_failures"], 2)
        self.assertEqual(s["pcm"]["restarts"], 2)
        self.assertEqual(s["resume"]["home_failures"], 4)
        self.assertEqual(s["resume"]["observed_home_resumes"], 12)
        self.assertEqual(s["resume"]["reopen_attempts"], 3)
        self.assertEqual(s["resume"]["recoveries"], 1)
        self.assertEqual(s["triage"], "INVESTIGATE")
        self.assertEqual(data["report_triage"], "INVESTIGATE")
        self.assertEqual(data["hardware_status"], "HARDWARE NOT TESTED")

    def test_short_or_unfinished_file_is_inconclusive(self):
        adjust_csv(self.root / self.files[1], output_pages=100,
                   event="PERIODIC", status=1)
        self.manifest()
        data = report.review(self.root)
        self.assertEqual(data["sessions"][1]["pcm"]["observed_pages"], 100)
        self.assertFalse(data["sessions"][1]["end_exit"])
        self.assertEqual(data["report_triage"], "INCONCLUSIVE")
        self.assertEqual(data["telemetry_readiness"], "INCOMPLETE")

    def test_identical_copies_are_not_independent(self):
        (self.root / self.files[1]).write_bytes(
            (self.root / self.files[0]).read_bytes())
        self.manifest()
        data = report.review(self.root)
        self.assertEqual(data["session_count"], 2)
        self.assertEqual(data["report_triage"], "INCONCLUSIVE")
        self.assertIn("Identical CSV bytes", data["duplicate_evidence_warnings"][0])

    def test_empty_bundle_is_a_preflight_not_hardware_report(self):
        (self.root / self.files[0]).unlink()
        (self.root / self.files[1]).unlink()
        self.manifest(sessions=[])
        data = report.review(self.root)
        self.assertEqual(data["sessions"], [])
        self.assertEqual(data["report_triage"], "INCONCLUSIVE")
        self.assertEqual(data["hardware_status"], "HARDWARE NOT TESTED")

    def test_changed_csv_or_nro_fails_closed(self):
        self.manifest()
        path = self.root / self.files[0]
        path.write_bytes(path.read_bytes() + b"MISMATCH")
        with self.assertRaisesRegex(bundle.BundleError, "SHA-256 mismatch"):
            report.review(self.root)
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID EVIDENCE", result.stderr)

    def test_untracked_csv_causes_failure_not_automatic_success(self):
        self.manifest()
        write_session(self.root / "session-03" / "audio-diagnostics-0002.csv")
        with self.assertRaisesRegex(bundle.BundleError, "untracked"):
            report.review(self.root)

    def test_cli_json_and_markdown_are_consistent(self):
        self.manifest()
        json_result = self.run_cli("--format", "json")
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["hardware_status"], "HARDWARE NOT TESTED")
        markdown_result = self.run_cli("--format", "markdown")
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn("Hardware status: HARDWARE NOT TESTED", markdown_result.stdout)
        self.assertIn("HOME failures", markdown_result.stdout)
        self.assertIn("physical hardware PASS", markdown_result.stdout)

    def test_report_exposes_retained_only_not_full_session(self):
        # Non-START retained window is not an intact history; no fabricated events.
        adjust_csv(self.root / self.files[0], home_resumes=5)
        self.manifest()
        data = report.review(self.root)
        self.assertEqual(data["sessions"][0]["resume"]["observed_home_resumes"], 5)
        self.assertEqual(data["sessions"][0]["recording"]["historical_gaps"], 0)
        self.assertIn("128-row", data["limitations"])


if __name__ == "__main__":
    unittest.main()
