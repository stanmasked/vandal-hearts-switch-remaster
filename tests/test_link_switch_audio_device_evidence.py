#!/usr/bin/env python3
"""Stage 232: synthetic host-to-post-run CSV evidence link, no real Switch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import audit_switch_audio_handoff as handoff  # noqa: E402
import link_switch_audio_device_evidence as linker  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_sd_reinsert as reinsert  # noqa: E402
from test_audit_switch_audio_handoff import HardwareHandoffTests  # noqa: E402


class DeviceEvidenceLinkTests(unittest.TestCase):
    def setUp(self):
        fixture = HardwareHandoffTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fx = fixture
        self.post_run_bundle = fixture.fixture.root
        self.base = fixture.fixture.base
        self.baseline = self.base / "pre-run-readback.json"
        self.after = self.base / "post-reinsert-review.json"
        self.first_time = "2026-10-17T07:00:00+00:00"
        self.after_time = "2026-10-17T07:30:00+00:00"
        self.run_id = 123456
        self.artifact_id = 789012
        self.commit = fixture.fixture.record["build_git_sha"]
        self.nro_sha = fixture.fixture.record["nro_sha256"]
        self.nro_size = (self.post_run_bundle / "nro" /
                         "vandal-hearts-prototype.nro").stat().st_size
        self.manifest_file = self.post_run_bundle / bundle.MANIFEST_NAME
        manifest = json.loads(self.manifest_file.read_text())
        manifest["ci_run_url"] = (
            "https://github.com/stanmasked/vandal-hearts-switch-remaster/"
            f"actions/runs/{self.run_id}")
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        self.baseline_record = {
            "schema": reinsert.SCHEMA,
            "hardware_status": bundle.HARDWARE_STATUS,
            "phase": "BEFORE_MANUAL_REMOUNT",
            "provenance": "LIVE_GITHUB_AND_LOCAL_BYTE_MATCH_NOT_SIGNED",
            "build_git_sha": self.commit,
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "run_attempt": 1,
            "artifact_zip_sha256": "1" * 64,
            "installed_nro_sha256": self.nro_sha,
            "installed_nro_size": self.nro_size,
            "sd_destination_relative":
                "switch/vandal-hearts-remake/vandal-hearts-prototype.nro",
            "manifest_sha256": "2" * 64,
            "transfer_plan_sha256": "3" * 64,
            "checked_at_utc": self.first_time,
            "remount_performed": False,
            "physical_sd_attested": False,
        }
        self.report_record = {
            "schema": linker.RECHECK_SCHEMA,
            "result": "POST_REINSERT_LOCAL_NRO_BYTES_MATCH",
            "hardware_status": bundle.HARDWARE_STATUS,
            "baseline_sha256": "",
            "build_git_sha_confirmed_at_recheck": self.commit,
            "run_id": self.run_id,
            "artifact_id": self.artifact_id,
            "run_attempt": 1,
            "installed_nro_sha256": self.nro_sha,
            "installed_nro_size": self.nro_size,
            "checked_at_utc": self.after_time,
            "operator_reinsert_claim": "SELF_REPORTED_NOT_INDEPENDENTLY_ATTESTED",
            "physical_sd_medium": "NOT_ATTESTED",
            "physical_nro_execution": bundle.HARDWARE_STATUS,
            "audible_music": "NOT_TESTED",
            "sd_power_loss_durability": "NOT_TESTED",
            "limitations": "SYNTHETIC, not real Switch testing or physical SD.",
        }
        self.rewrite()

    def rewrite(self):
        self.fx.save_cards()
        self.fx.fixture.write_record()
        self.baseline.write_bytes(reinsert.baseline_bytes(self.baseline_record))
        self.baseline_sha = bundle.digest_file(self.baseline)[1]
        self.report_record["baseline_sha256"] = self.baseline_sha
        self.after.write_text(json.dumps(self.report_record, indent=2),
                              encoding="utf-8")
        self.after_sha = bundle.digest_file(self.after)[1]

    def link(self, **kwargs):
        options = dict(
            root=self.post_run_bundle,
            observations=self.fx.fixture.observations,
            cards=self.fx.cards, baseline=self.baseline,
            baseline_sha256=self.baseline_sha,
            recheck_report=self.after, recheck_sha256=self.after_sha,
        )
        options.update(kwargs)
        return linker.link(**options)

    def test_full_two_session_csv_link_is_only_ready_for_human_review(self):
        report = self.link()
        self.assertEqual(report["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(report["self_reported_session_independence"], "NOT_ATTESTED")
        self.assertEqual(report["physical_switch_execution"], "NOT_ATTESTED")
        self.assertEqual(report["audible_music"], "NOT_ATTESTED")
        self.assertEqual(report["build"]["git_sha_self_reported"], self.commit)
        self.assertEqual(len(report["device_session_claims"]), 2)
        self.assertEqual(len(report["scenarios"]), 7)
        self.assertEqual(report["chronology_findings"], [])

    def test_post_run_manifest_may_change_when_csv_sessions_added(self):
        self.assertNotEqual(
            self.baseline_record["manifest_sha256"],
            bundle.digest_file(self.manifest_file)[1])
        self.assertEqual(self.link()["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")

    def test_missing_one_card_keeps_result_inconclusive(self):
        (self.fx.cards / "second.json").unlink()
        result = self.link()
        self.assertEqual(result["result"], "INCONCLUSIVE")
        self.assertIn("MISSING_MANUAL_CARD",
                      {r["state"] for r in result["device_session_claims"]})

    def test_session_claim_predates_reinsert_check_needs_investigation(self):
        self.fx.records[0]["start_utc"] = "2026-10-17T06:00:00+00:00"
        self.fx.records[0]["end_utc"] = "2026-10-17T07:00:00+00:00"
        self.fx.save_cards()
        report = self.link()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("SESSION_CLAIM_BEFORE_VERIFIED_SD_RECHECK",
                      {r["code"] for r in report["chronology_findings"]})

    def test_observed_audio_fault_is_not_misreported_as_ready(self):
        self.fx.records[0]["audio_artifacts"] = "HEARD"
        self.fx.fixture.record["sessions"][0]["audio_artifacts"] = "HEARD"
        self.rewrite()
        self.assertEqual(self.link()["result"], "INVESTIGATE")

    def test_pinned_before_record_sha_mismatch_rejected(self):
        with self.assertRaisesRegex(reinsert.ReinsertError, "BASELINE_SHA256_MISMATCH"):
            self.link(baseline_sha256="0" * 64)

    def test_changed_after_report_sha_mismatch_rejected(self):
        self.after.write_bytes(self.after.read_bytes() + b"changed")
        with self.assertRaisesRegex(linker.LinkError, "RECHECK_SHA256_MISMATCH"):
            self.link()

    def test_mismatched_before_after_report_binding_rejected(self):
        self.report_record["baseline_sha256"] = "f" * 64
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError, "RECHECK_BASELINE_BINDING_MISMATCH"):
            self.link()

    def test_changed_run_attempt_is_strictly_rejected(self):
        self.report_record["run_attempt"] = 2
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError, "PRE_POST_BUILD_IDENTITY_MISMATCH"):
            self.link()

    def test_changed_nro_in_recheck_is_rejected(self):
        self.report_record["installed_nro_sha256"] = "f" * 64
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError, "PRE_POST_BUILD_IDENTITY_MISMATCH"):
            self.link()

    def test_post_run_manifest_commit_disagrees_with_record(self):
        manifest = json.loads(self.manifest_file.read_text())
        manifest["git_sha"] = "a" * 40
        self.manifest_file.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(linker.LinkError, "POST_RUN_BUNDLE_NRO_OR_BUILD_MISMATCH"):
            self.link()

    def test_post_run_manifest_run_url_mismatch_rejected(self):
        manifest = json.loads(self.manifest_file.read_text())
        manifest["ci_run_url"] = (
            "https://github.com/stanmasked/vandal-hearts-switch-remaster/"
            "actions/runs/234567")
        self.manifest_file.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(linker.LinkError,
                                    "POST_RUN_BUNDLE_GITHUB_RUN_URL_MISMATCH"):
            self.link()

    def test_post_run_nro_different_binary_rejected(self):
        path = self.post_run_bundle / "nro" / "vandal-hearts-prototype.nro"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaises(bundle.BundleError):
            self.link()

    def test_post_run_csv_mutation_fails_strict_bundle_hash(self):
        path = self.post_run_bundle / self.fx.fixture.files[0]
        path.write_bytes(path.read_bytes() + b"corrupted")
        with self.assertRaises(bundle.BundleError):
            self.link()

    def test_forged_hardware_pass_in_after_report_is_rejected(self):
        self.report_record["physical_nro_execution"] = "PASS"
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError,
                                    "falsely claims hardware acceptance"):
            self.link()

    def test_recheck_before_baseline_time_rejected(self):
        self.report_record["checked_at_utc"] = "2026-10-17T06:00:00+00:00"
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError, "REINSERT_REVIEW_PREDATES_BASELINE"):
            self.link()

    def test_recheck_timestamp_without_timezone_rejected(self):
        self.report_record["checked_at_utc"] = "2026-10-17T07:30:00"
        self.after.write_text(json.dumps(self.report_record))
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaisesRegex(linker.LinkError, "lacks timezone"):
            self.link()

    def test_duplicate_recheck_json_keys_rejected(self):
        self.after.write_text('{"schema":"a","schema":"b"}')
        self.after_sha = bundle.digest_file(self.after)[1]
        with self.assertRaises(bundle.BundleError):
            self.link()

    def test_missing_observer_measurement_remains_inconclusive(self):
        self.fx.fixture.record["sessions"][0]["music_audible"] = "UNKNOWN"
        self.fx.records[0]["music_audible"] = "UNKNOWN"
        self.rewrite()
        self.assertEqual(self.link()["result"], "INCONCLUSIVE")

    def test_optional_h06_remains_incomplete_not_auto_pass(self):
        self.assertEqual(self.link(require_h06=True)["result"], "INCONCLUSIVE")

    def test_read_only_link_does_not_write_primary_evidence(self):
        paths = [
            self.baseline, self.after, self.manifest_file,
            self.fx.fixture.observations,
            *(self.post_run_bundle / x for x in self.fx.fixture.files),
            *(self.fx.cards / x for x in ("first.json", "second.json")),
        ]
        before = {str(p): p.read_bytes() for p in paths}
        self.link()
        self.assertEqual(before, {str(p): p.read_bytes() for p in paths})

    def test_cli_json_success_and_hash_failure(self):
        args = [
            sys.executable,
            str(ROOT / "tools" / "link_switch_audio_device_evidence.py"),
            str(self.post_run_bundle),
            "--observations", str(self.fx.fixture.observations),
            "--cards-dir", str(self.fx.cards),
            "--baseline", str(self.baseline),
            "--baseline-sha256", self.baseline_sha,
            "--recheck-report", str(self.after),
            "--recheck-sha256", self.after_sha,
        ]
        ok = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        args[-1] = "0" * 64
        bad = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(json.loads(bad.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
