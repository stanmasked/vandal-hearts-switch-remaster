#!/usr/bin/env python3
"""Stage 236 synthetic H05 -> raw CSV -> operator card integration tests."""
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

import assess_switch_audio_first_run as first_run  # noqa: E402
import audit_switch_audio_handoff as handoff  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_h05_operator_binding as binding  # noqa: E402
from test_verify_switch_audio_h05_capture_binding import H05CapturedEvidenceTests  # noqa: E402
from test_assess_switch_audio_first_run import operator_session  # noqa: E402


class H05OperatorCardsTests(unittest.TestCase):
    def setUp(self):
        fixture = H05CapturedEvidenceTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fx = fixture
        self.bundle = fixture.output
        self.cards = fixture.host.base / "original-operator-cards"
        self.cards.mkdir()
        self.observations = fixture.host.base / "original-operator-observations.json"
        manifest = bundle.read_manifest(self.bundle)
        self.nro_sha = manifest["nro"]["sha256"]
        self.git_sha = manifest["git_sha"]
        self.sessions = []
        self.entries = []
        for n, item in enumerate(manifest["sessions"], 1):
            ident = "test" + str(n)
            session = operator_session(item["path"], ident, 25, 5, 3)
            self.sessions.append(session)
            start = datetime(2026, 10, 17, n + 7, 0, tzinfo=timezone.utc)
            card = {
                "schema": handoff.CARD_SCHEMA,
                "session_id": ident,
                "csv": item["path"],
                "csv_sha256": item["sha256"],
                "nro_sha256": self.nro_sha,
                "git_sha": self.git_sha,
                "launch_id": "simulated-run-" + str(n),
                "start_utc": start.isoformat(),
                "end_utc": (start + timedelta(minutes=35)).isoformat(),
                "console_label": "synthetic-switch",
                "launch_mode": session["launch_mode"],
                "audio_output": session["audio_output"],
                "music_audible": session["music_audible"],
                "audio_artifacts": session["audio_artifacts"],
                "normal_exit": session["normal_exit"],
                "observer_note": "SYNTHETIC, never hardware evidence",
            }
            self.entries.append(card)
        self.operator = {
            "schema": first_run.SCHEMA,
            "build_git_sha": self.git_sha,
            "nro_sha256": self.nro_sha,
            "sessions": self.sessions,
            "prior_csv_path": manifest["sessions"][0]["path"],
            "prior_csv_sha256_before": manifest["sessions"][0]["sha256"],
            "prior_csv_sha256_after": manifest["sessions"][0]["sha256"],
        }
        self.save()

    def save(self):
        self.observations.write_text(json.dumps(self.operator), encoding="utf-8")
        for item in self.entries:
            (self.cards / (item["session_id"] + ".json")).write_text(
                json.dumps(item), encoding="utf-8")

    def verify(self, **overrides):
        options = dict(
            source_bundle=self.fx.host.source_bundle,
            plan=self.fx.host.plan,
            captured=self.bundle,
            baseline=self.fx.case.baseline,
            baseline_sha256=self.fx.case.pinned,
            review=self.fx.review,
            review_sha256=self.fx.review_sha,
            observations=self.observations,
            cards_dir=self.cards,
        )
        options.update(overrides)
        return binding.verify(**options)

    def test_old_and_new_are_bound_to_distinct_ordered_operator_claims(self):
        result = self.verify()
        self.assertEqual(result["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["handoff_result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(result["old_csv"]["session_id"], "test1")
        self.assertEqual(result["new_csv"]["session_id"], "test3")
        self.assertNotEqual(result["old_csv"]["sha256"], result["new_csv"]["sha256"])
        self.assertEqual(len(result["operator_card_sha256"]), 2)
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["physical_session_independence"], "NOT_ATTESTED")
        self.assertEqual(result["actual_audio_playback"], "NOT_ATTESTED")
        self.assertEqual(result["manual_signoff"], "REQUIRED_NOT_AUTOMATED")

    def test_prior_csv_path_mismatch_is_investigation_not_hardware_pass(self):
        self.operator["prior_csv_path"] = self.sessions[1]["csv"]
        self.save()
        result = self.verify()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertIn("H05_OPERATOR_PRIOR_CSV_PATH_MISMATCH",
                      {x["code"] for x in result["contradictions"]})

    def test_prior_csv_hash_claim_mismatch_is_investigation(self):
        self.operator["prior_csv_sha256_before"] = "f" * 64
        self.operator["prior_csv_sha256_after"] = "f" * 64
        self.save()
        result = self.verify()
        self.assertEqual(result["result"], "INVESTIGATE")
        self.assertIn("H05_OPERATOR_PRIOR_CSV_HASHES_MISMATCH",
                      {x["code"] for x in result["contradictions"]})

    def test_missing_new_session_card_is_inconclusive(self):
        (self.cards / "test3.json").unlink()
        x = self.verify()
        self.assertEqual(x["result"], "INCONCLUSIVE")
        self.assertEqual(x["missing_cards"][0]["session"], "test3")

    def test_missing_old_session_card_is_inconclusive(self):
        (self.cards / "test1.json").unlink()
        x = self.verify()
        self.assertEqual(x["result"], "INCONCLUSIVE")
        self.assertEqual(x["missing_cards"][0]["session"], "test1")

    def test_wrong_new_card_csv_is_never_accepted(self):
        self.entries[2]["csv"] = self.sessions[1]["csv"]
        self.save()
        x = self.verify()
        self.assertEqual(x["result"], "INVESTIGATE")
        self.assertIn("H05_OPERATOR_CARD_CSV_BUILD_IDENTITY_MISMATCH",
                      {q["code"] for q in x["contradictions"]})

    def test_mismatched_old_card_nro_is_investigation(self):
        self.entries[0]["nro_sha256"] = "f" * 64
        self.save()
        self.assertEqual(self.verify()["result"], "INVESTIGATE")

    def test_mismatched_new_card_csv_hash_is_investigation(self):
        self.entries[2]["csv_sha256"] = "f" * 64
        self.save()
        self.assertEqual(self.verify()["result"], "INVESTIGATE")

    def test_same_operator_launch_label_is_investigation(self):
        self.entries[2]["launch_id"] = self.entries[0]["launch_id"]
        self.save()
        x = self.verify()
        self.assertEqual(x["result"], "INVESTIGATE")
        self.assertIn("H05_REUSED_SELF_REPORTED_LAUNCH_ID",
                      {q["code"] for q in x["contradictions"]})

    def test_overlapping_operator_card_times_are_investigation(self):
        self.entries[2]["start_utc"] = self.entries[0]["start_utc"]
        self.entries[2]["end_utc"] = self.entries[0]["end_utc"]
        self.save()
        x = self.verify()
        self.assertEqual(x["result"], "INVESTIGATE")
        self.assertIn("H05_OVERLAPPING_OPERATOR_SESSION_TIMES",
                      {q["code"] for q in x["contradictions"]})

    def test_mismatched_console_label_requires_investigation(self):
        self.entries[2]["console_label"] = "synthetic-other-switch"
        self.save()
        x = self.verify()
        self.assertEqual(x["result"], "INVESTIGATE")
        self.assertIn("H05_CONSOLE_LABEL_CHANGED",
                      {q["code"] for q in x["contradictions"]})

    def test_operator_sessions_order_swapped_refuses_old_after_new(self):
        self.operator["sessions"] = list(reversed(self.sessions))
        self.save()
        with self.assertRaisesRegex(binding.OperatorBindingError, "SESSION_ORDER_WRONG"):
            self.verify()

    def test_operator_csv_coverage_missing_is_invalid(self):
        self.operator["sessions"].pop()
        self.save()
        with self.assertRaises(first_run.OperatorError):
            self.verify()

    def test_duplicate_operator_csv_claim_is_rejected(self):
        self.operator["sessions"][2]["csv"] = self.operator["sessions"][0]["csv"]
        self.save()
        with self.assertRaises(first_run.OperatorError):
            self.verify()

    def test_operator_build_id_disagrees_with_pinned_nro(self):
        self.operator["build_git_sha"] = "f" * 40
        self.save()
        with self.assertRaises(first_run.OperatorError):
            self.verify()

    def test_audio_dropout_never_returns_ready(self):
        self.entries[2]["audio_artifacts"] = "HEARD"
        self.sessions[2]["audio_artifacts"] = "HEARD"
        self.save()
        self.assertEqual(self.verify()["result"], "INVESTIGATE")

    def test_not_recorded_music_is_inconclusive_or_investigate(self):
        self.entries[2]["music_audible"] = "UNKNOWN"
        self.sessions[2]["music_audible"] = "UNKNOWN"
        self.save()
        self.assertNotEqual(self.verify()["result"],
                            "READY_FOR_INDEPENDENT_MANUAL_REVIEW")

    def test_unknown_h06_stays_incomplete(self):
        self.assertEqual(self.verify(require_h06=True)["result"], "INCONCLUSIVE")

    def test_changed_captured_csv_detected_by_stage235(self):
        file = self.bundle / self.sessions[0]["csv"]
        file.write_bytes(file.read_bytes() + b"changed")
        with self.assertRaises(bundle.BundleError):
            self.verify()

    def test_changed_h05_review_digest_detected(self):
        with self.assertRaisesRegex(Exception, "REVIEW_SHA256_MISMATCH"):
            self.verify(review_sha256="f" * 64)

    def test_missing_observations_is_invalid(self):
        self.observations.unlink()
        with self.assertRaisesRegex(binding.OperatorBindingError, "operator observations"):
            self.verify()

    def test_read_only_for_all_evidence_and_operator_cards(self):
        watched = [
            self.observations, self.fx.case.baseline, self.fx.review,
            self.fx.host.plan, self.bundle / bundle.MANIFEST_NAME,
            *(self.cards / (item["session_id"] + ".json") for item in self.entries),
            *(self.bundle / item["csv"] for item in self.sessions),
        ]
        before = [p.read_bytes() for p in watched]
        self.verify()
        self.assertEqual(before, [p.read_bytes() for p in watched])

    def test_cli_returns_json_and_fails_bad_hash(self):
        command = [
            sys.executable, str(ROOT / "tools" / "verify_switch_audio_h05_operator_binding.py"),
            "--source-bundle", str(self.fx.host.source_bundle),
            "--transfer-plan", str(self.fx.host.plan),
            "--captured", str(self.bundle),
            "--h05-baseline", str(self.fx.case.baseline),
            "--baseline-sha256", self.fx.case.pinned,
            "--h05-review", str(self.fx.review),
            "--review-sha256", self.fx.review_sha,
            "--observations", str(self.observations),
            "--cards-dir", str(self.cards),
        ]
        ok = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["result"],
                         "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        command[command.index("--review-sha256")+1] = "f" * 64
        failed = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(json.loads(failed.stdout)["result"], "INVALID_EVIDENCE")
        self.assertEqual(json.loads(failed.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
