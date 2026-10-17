#!/usr/bin/env python3
"""Stage 237: fully rerunnable final H05 handoff receipt, synthetic only."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import seal_switch_audio_h05_review as seal  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_verify_switch_audio_h05_operator_binding import H05OperatorCardsTests  # noqa: E402


class FinalReviewReceiptTests(unittest.TestCase):
    def setUp(self):
        fixture = H05OperatorCardsTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fx = fixture
        self.receipt = fixture.fx.host.base / "h05-final-review.json"
        self.params = {
            "source_bundle": fixture.fx.host.source_bundle,
            "plan": fixture.fx.host.plan,
            "captured": fixture.bundle,
            "baseline": fixture.fx.case.baseline,
            "baseline_sha256": fixture.fx.case.pinned,
            "review": fixture.fx.review,
            "review_sha256": fixture.fx.review_sha,
            "observations": fixture.observations,
            "cards_dir": fixture.cards,
            "require_h06": False,
            "compare_builds": False,
        }

    def issue(self, **overrides):
        p = {**self.params, **overrides}
        return seal.seal(self.receipt, **p)

    def replay(self, sha=None, **overrides):
        return seal.replay(
            self.receipt,
            sha if sha is not None else bundle.digest_file(self.receipt)[1],
            **{**self.params, **overrides})

    def cli(self, mode, *extras):
        base = [
            sys.executable,
            str(ROOT / "tools" / "seal_switch_audio_h05_review.py"),
            mode,
            "--source-bundle", str(self.params["source_bundle"]),
            "--transfer-plan", str(self.params["plan"]),
            "--captured", str(self.params["captured"]),
            "--h05-baseline", str(self.params["baseline"]),
            "--baseline-sha256", self.params["baseline_sha256"],
            "--h05-review", str(self.params["review"]),
            "--review-sha256", self.params["review_sha256"],
            "--observations", str(self.params["observations"]),
            "--cards-dir", str(self.params["cards_dir"]),
            *extras,
        ]
        return subprocess.run(base, text=True, capture_output=True)

    def test_every_original_file_and_all_operator_cards_are_in_receipt(self):
        sealed = self.issue()
        self.assertEqual(sealed["result"], "H05_FINAL_REVIEW_RECEIPT_SEALED")
        self.assertEqual(sealed["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(sealed["review_state"], "READY_FOR_INDEPENDENT_MANUAL_REVIEW")
        self.assertEqual(sealed["manual_signoff"], "REQUIRED_NOT_AUTOMATED")
        value = json.loads(self.receipt.read_text())
        roles = [item["role"] for item in value["entire_source_inventory"]]
        self.assertEqual(roles.count("raw_csv"), 3)
        self.assertEqual(roles.count("self_reported_session_card"), 3)
        self.assertEqual(roles.count("operator_claims"), 1)
        self.assertEqual(roles.count("nro"), 1)
        self.assertEqual(roles.count("unsigned_bundle_manifest"), 1)
        self.assertEqual(sealed["total_source_files"], 9)
        self.assertEqual(len(value["all_session_cards"]), 3)
        self.assertEqual(len(value["full_acceptance_matrix"]), 7)
        self.assertEqual(value["physical_switch_execution"], "NOT_ATTESTED")
        self.assertEqual(value["audible_music"], "NOT_ATTESTED")
        self.assertEqual(self.replay(sealed["receipt_sha256"])["result"],
                         "PINNED_H05_FINAL_REVIEW_REPLAYED")

    def test_receipt_is_reproducible_without_host_paths_or_wall_clock(self):
        first = self.issue()
        before = self.receipt.read_bytes()
        alternate = self.fx.fx.host.base / "h05-other-review.json"
        second = seal.seal(alternate, **self.params)
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(before, alternate.read_bytes())
        self.assertEqual(before, seal.stable(json.loads(before)))
        self.assertNotIn(str(self.fx.fx.host.base).encode(), before)

    def test_wrong_independent_digest_is_refused(self):
        self.issue()
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_SHA256_MISMATCH"):
            self.replay("f" * 64)
        with self.assertRaisesRegex(seal.SealError, "64 lowercase"):
            self.replay("INVALID")

    def test_receipt_byte_edit_is_refused(self):
        created = self.issue()
        self.receipt.write_bytes(self.receipt.read_bytes() + b"\n")
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_SHA256_MISMATCH"):
            self.replay(created["receipt_sha256"])

    def test_review_hardware_pass_cannot_be_accepted_even_if_repinned(self):
        self.issue()
        value = json.loads(self.receipt.read_text())
        value["hardware_status"] = "PASS"
        self.receipt.write_bytes(seal.stable(value))
        with self.assertRaisesRegex(seal.SealError, "hardware PASS"):
            self.replay(bundle.digest_file(self.receipt)[1])

    def test_review_claim_status_cannot_be_edited_and_repinned(self):
        self.issue()
        value = json.loads(self.receipt.read_text())
        value["result"] = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"
        value["operator_binding"]["old_csv"]["sha256"] = "f" * 64
        self.receipt.write_bytes(seal.stable(value))
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_REPLAY_MISMATCH"):
            self.replay(bundle.digest_file(self.receipt)[1])

    def test_changed_intermediate_card_is_detected_on_replay(self):
        signed = self.issue()
        card = self.fx.cards / "test2.json"
        obj = json.loads(card.read_text())
        obj["observer_note"] = "Changed original manual statement"
        card.write_text(json.dumps(obj))
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_REPLAY_MISMATCH"):
            self.replay(signed["receipt_sha256"])

    def test_mutated_original_raw_csv_rejected(self):
        signed = self.issue()
        member = self.fx.bundle / self.fx.sessions[1]["csv"]
        member.write_bytes(member.read_bytes() + b"changed")
        with self.assertRaises(bundle.BundleError):
            self.replay(signed["receipt_sha256"])

    def test_mutated_operator_observations_changes_verified_snapshot(self):
        signed = self.issue()
        self.fx.operator["sessions"][2]["music_audible"] = "NO"
        self.fx.entries[2]["music_audible"] = "NO"
        self.fx.save()
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_REPLAY_MISMATCH"):
            self.replay(signed["receipt_sha256"])

    def test_missing_h05_card_is_preserved_as_inconclusive_not_auto_pass(self):
        (self.fx.cards / "test3.json").unlink()
        made = self.issue()
        self.assertEqual(made["review_state"], "INCONCLUSIVE")
        value = json.loads(self.receipt.read_text())
        self.assertEqual(value["operator_binding"]["result"], "INCONCLUSIVE")
        self.assertEqual(value["operator_binding"]["missing_cards"][0]["session"],
                         "test3")
        self.assertTrue(value["full_handoff_followups"])
        self.assertEqual(self.replay(made["receipt_sha256"])["review_state"],
                         "INCONCLUSIVE")

    def test_heard_audio_artifact_is_preserved_as_investigate(self):
        self.fx.entries[2]["audio_artifacts"] = "HEARD"
        self.fx.sessions[2]["audio_artifacts"] = "HEARD"
        self.fx.save()
        made = self.issue()
        self.assertEqual(made["review_state"], "INVESTIGATE")
        value = json.loads(self.receipt.read_text())
        self.assertEqual(value["operator_binding"]["result"], "INVESTIGATE")
        self.assertEqual(value["full_acceptance_matrix"][0]["status"], "INVESTIGATE")
        self.assertEqual(self.replay(made["receipt_sha256"])["review_state"],
                         "INVESTIGATE")

    def test_requested_optional_h06_remains_inconclusive(self):
        made = self.issue(require_h06=True)
        self.assertEqual(made["review_state"], "INCONCLUSIVE")
        value = json.loads(self.receipt.read_text())
        self.assertTrue(value["audit_options"]["require_h06"])
        with self.assertRaisesRegex(seal.SealError, "FINAL_REVIEW_REPLAY_MISMATCH"):
            self.replay(made["receipt_sha256"], require_h06=False)
        self.assertEqual(self.replay(made["receipt_sha256"], require_h06=True)
                         ["review_state"], "INCONCLUSIVE")

    def test_reject_output_inside_original_or_cards_folders(self):
        for dest in (
            self.fx.bundle / "receipt.json",
            self.fx.fx.host.source_bundle / "receipt.json",
            self.fx.cards / "receipt.json",
        ):
            with self.subTest(dest=dest), self.assertRaisesRegex(
                    seal.SealError, "outside"):
                seal.seal(dest, **self.params)
            self.assertFalse(dest.exists())

    def test_existing_receipt_cannot_be_overwritten(self):
        self.issue()
        previous = self.receipt.read_bytes()
        with self.assertRaisesRegex(seal.SealError, "refusing overwrite"):
            self.issue()
        self.assertEqual(self.receipt.read_bytes(), previous)

    def test_replay_does_not_change_sources_cards_receipt_or_csv(self):
        made = self.issue()
        watched = [
            self.receipt, self.params["baseline"], self.params["review"],
            self.params["plan"], self.params["observations"],
            self.fx.bundle / bundle.MANIFEST_NAME,
            *(self.fx.cards / (entry["session_id"] + ".json")
              for entry in self.fx.entries),
            *(self.fx.bundle / entry["csv"] for entry in self.fx.sessions),
        ]
        before = [path.read_bytes() for path in watched]
        self.replay(made["receipt_sha256"])
        self.assertEqual(before, [path.read_bytes() for path in watched])

    def test_cli_seal_replay_and_missing_pin_fails_closed(self):
        created = self.cli("seal", "--output", str(self.receipt))
        self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
        parsed = json.loads(created.stdout)
        self.assertEqual(parsed["hardware_status"], "HARDWARE NOT TESTED")
        pinned = parsed["receipt_sha256"]
        check = self.cli("replay", "--receipt", str(self.receipt),
                         "--expected-receipt-sha256", pinned)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(json.loads(check.stdout)["result"],
                         "PINNED_H05_FINAL_REVIEW_REPLAYED")
        invalid = self.cli("replay", "--receipt", str(self.receipt),
                           "--expected-receipt-sha256", "0" * 64)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(json.loads(invalid.stdout)["result"], "INVALID_EVIDENCE")
        self.assertEqual(json.loads(invalid.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
