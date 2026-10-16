#!/usr/bin/env python3
"""Host-only stage 222 handoff test matrix; never runs on real Switch."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import audit_switch_audio_handoff as handoff  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_assess_switch_audio_first_run import FirstRunOperatorEvidenceTests  # noqa: E402


class HardwareHandoffTests(unittest.TestCase):
    def setUp(self):
        fixture = FirstRunOperatorEvidenceTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.cards = fixture.base / "session-cards"
        self.cards.mkdir()
        self.records = []
        start = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc)
        for index, session in enumerate(fixture.record["sessions"]):
            began = start + timedelta(hours=index)
            card = {
                "schema": handoff.CARD_SCHEMA,
                "session_id": session["id"],
                "csv": session["csv"],
                "csv_sha256": bundle.digest_file(fixture.root / session["csv"])[1],
                "nro_sha256": fixture.record["nro_sha256"],
                "git_sha": fixture.record["build_git_sha"],
                "launch_id": "physical-run-" + str(index + 1),
                "start_utc": began.isoformat(),
                "end_utc": (began + timedelta(minutes=45)).isoformat(),
                "console_label": "switch-test-a",
                "launch_mode": session["launch_mode"],
                "audio_output": session["audio_output"],
                "music_audible": session["music_audible"],
                "audio_artifacts": session["audio_artifacts"],
                "normal_exit": session["normal_exit"],
                "observer_note": "SYNTHETIC fixture: never evidence of physical hardware",
            }
            self.records.append(card)
        self.save_cards()

    def save_cards(self):
        for card in self.records:
            (self.cards / (card["session_id"] + ".json")).write_text(
                json.dumps(card), encoding="utf-8")

    def audit(self, **options):
        self.fixture.write_record()
        return handoff.audit(self.fixture.root, self.fixture.observations,
                             self.cards, **options)

    def call_cli(self, *options):
        self.fixture.write_record()
        return subprocess.run([
            sys.executable, str(ROOT / "tools" / "audit_switch_audio_handoff.py"),
            str(self.fixture.root), "--observations",
            str(self.fixture.observations), "--cards-dir", str(self.cards),
            *options,
        ], capture_output=True, text=True, check=False)

    def test_matching_cards_remain_unattested_and_no_auto_pass(self):
        report = self.audit()
        self.assertEqual(report["result"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertTrue(report["repeated_session_claims"]["self_report_consistent"])
        self.assertEqual(report["repeated_session_claims"]["physical_independence"],
                         "NOT_ATTESTED")
        self.assertEqual(len(report["source_inventory"]), 7)
        self.assertEqual(len(report["acceptance_matrix"]), 7)
        self.assertEqual(report["retests"], [])

    def test_inventory_rehashes_source_operator_and_cards(self):
        report = self.audit()
        roles = [x["role"] for x in report["source_inventory"]]
        self.assertEqual(roles.count("raw_csv"), 2)
        self.assertEqual(roles.count("self_reported_session_card"), 2)
        self.assertIn("unsigned_bundle_manifest", roles)
        expected = bundle.digest_file(self.fixture.observations)[1]
        self.assertEqual(next(x for x in report["source_inventory"]
                              if x["role"] == "operator_claims")["sha256"], expected)

    def test_missing_one_card_yields_incomplete_and_action(self):
        (self.cards / "second.json").unlink()
        report = self.audit()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertEqual(report["repeated_session_claims"]["cards_present"], 1)
        self.assertEqual(report["session_cards"][1]["status"], "MISSING_MANUAL_CARD")
        self.assertTrue(any("second" in x.get("missing_sessions", [])
                            for x in report["handoff_followups"]))

    def test_missing_cards_dir_does_not_invent_sessions(self):
        for path in self.cards.iterdir():
            path.unlink()
        self.cards.rmdir()
        report = self.audit()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertEqual(report["repeated_session_claims"]["cards_present"], 0)

    def test_same_claimed_launch_id_is_flagged(self):
        self.records[1]["launch_id"] = self.records[0]["launch_id"]
        self.save_cards()
        report = self.audit()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("DUPLICATE_SELF_REPORTED_LAUNCH_ID",
                      {x["code"] for x in report["contradictions"]})

    def test_overlap_or_reverse_order_is_flagged(self):
        self.records[1]["start_utc"] = self.records[0]["start_utc"]
        self.save_cards()
        report = self.audit()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("OVERLAPPING_OR_OUT_OF_ORDER_LAUNCHES",
                      {x["code"] for x in report["contradictions"]})

    def test_reported_minutes_cannot_exceed_card_duration(self):
        self.records[0]["end_utc"] = (
            datetime.fromisoformat(self.records[0]["start_utc"]) +
            timedelta(minutes=15)).isoformat()
        self.save_cards()
        report = self.audit()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("REPORTED_CONTINUOUS_MINUTES_EXCEED_CARD_DURATION",
                      {x["code"] for x in report["contradictions"]})

    def test_wrong_csv_hash_or_nro_build_is_flagged(self):
        for key, value in (
            ("csv_sha256", "f" * 64), ("nro_sha256", "e" * 64),
            ("git_sha", "b" * 40),
        ):
            original = self.records[0][key]
            self.records[0][key] = value
            self.save_cards()
            with self.subTest(key=key):
                report = self.audit()
                self.assertEqual(report["result"], "INVESTIGATE")
                self.assertIn("CARD_BINARY_OR_CSV_IDENTITY_MISMATCH",
                              {x["code"] for x in report["contradictions"]})
            self.records[0][key] = original
        self.save_cards()

    def test_cards_must_match_operator_audio_and_launch_mode(self):
        for key, value in (
            ("music_audible", "NO"), ("launch_mode", "APPLET"),
            ("audio_output", "DOCK_HDMI"), ("normal_exit", "NO"),
        ):
            original = self.records[0][key]
            self.records[0][key] = value
            self.save_cards()
            with self.subTest(key=key):
                report = self.audit()
                self.assertEqual(report["result"], "INVESTIGATE")
                self.assertIn("CARD_OPERATOR_" + key.upper() + "_DISAGREEMENT",
                              {x["code"] for x in report["contradictions"]})
            self.records[0][key] = original
        self.save_cards()

    def test_different_console_labels_require_manual_investigation(self):
        self.records[1]["console_label"] = "switch-test-b"
        self.save_cards()
        report = self.audit()
        self.assertEqual(report["result"], "INVESTIGATE")
        self.assertIn("DIFFERENT_CONSOLE_LABELS",
                      {x["code"] for x in report["contradictions"]})

    def test_naive_timestamp_and_broken_card_are_invalid(self):
        self.records[0]["start_utc"] = "2026-10-17T08:00:00"
        self.save_cards()
        run = self.call_cli()
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["result"], "INVALID_EVIDENCE")

    def test_duplicate_json_keys_rejected(self):
        (self.cards / "first.json").write_text(
            '{"schema":"one","schema":"two"}', encoding="utf-8")
        with self.assertRaises(bundle.BundleError):
            self.audit()

    def test_extra_json_card_fails_closed(self):
        (self.cards / "third.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(handoff.HandoffError, "untracked extra"):
            self.audit()

    def test_card_symlink_does_not_appear_to_be_missing(self):
        (self.cards / "first.json").unlink()
        (self.cards / "first.json").symlink_to(self.cards / "second.json")
        with self.assertRaisesRegex(handoff.HandoffError, "symlink"):
            self.audit()

    def test_operator_file_within_bundle_rejected(self):
        self.fixture.write_record()
        inside = self.fixture.root / "operator.json"
        inside.write_bytes(self.fixture.observations.read_bytes())
        with self.assertRaisesRegex(handoff.HandoffError, "outside"):
            handoff.audit(self.fixture.root, inside, self.cards)

    def test_corrupt_csv_rejected_without_publishing_matrix(self):
        (self.fixture.root / self.fixture.files[0]).write_bytes(b"CORRUPT")
        result = self.call_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["result"], "INVALID_EVIDENCE")
        self.assertNotIn("acceptance_matrix", json.loads(result.stdout))

    def test_incomplete_operator_review_blocks_consistent_cards(self):
        self.fixture.record["sessions"][1]["home_returns"] = 0
        report = self.audit()
        self.assertEqual(report["result"], "INCONCLUSIVE")
        self.assertTrue(any(r["id"] == "H02" and r["status"] == "INCOMPLETE"
                            for r in report["acceptance_matrix"]))
        self.assertTrue(any(r["scenario"] == "H02" for r in report["retests"]))

    def test_required_h06_or_h07_never_auto_approved(self):
        review = self.audit(require_h06=True, compare_builds=True)
        self.assertEqual(review["result"], "INCONCLUSIVE")
        self.assertEqual({r["scenario"] for r in review["retests"]}, {"H06", "H07"})

    def test_cli_json_and_read_only_inputs(self):
        self.fixture.write_record()
        before = {str(p.relative_to(self.fixture.root)): p.read_bytes()
                  for p in self.fixture.root.rglob("*") if p.is_file()}
        obs_bytes = self.fixture.observations.read_bytes()
        card_bytes = {p.name: p.read_bytes() for p in self.cards.glob("*.json")}
        result = self.call_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        self.assertEqual(before, {str(p.relative_to(self.fixture.root)): p.read_bytes()
                                 for p in self.fixture.root.rglob("*") if p.is_file()})
        self.assertEqual(obs_bytes, self.fixture.observations.read_bytes())
        self.assertEqual(card_bytes,
                         {p.name: p.read_bytes() for p in self.cards.glob("*.json")})


if __name__ == "__main__":
    unittest.main()
