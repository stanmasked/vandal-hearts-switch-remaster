#!/usr/bin/env python3
"""Stage 225 dual-run repeatability, pinned receipts, and race detection."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import replay_switch_audio_evidence_report as replay  # noqa: E402
import compare_switch_audio_archive_reports as cross_host  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
from test_archive_switch_audio_handoff import PortableArchiveTests  # noqa: E402


class RepeatableHardwareReportTests(unittest.TestCase):
    def setUp(self):
        fixture = PortableArchiveTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.fixture.fixture.base
        self.zip = fixture.destination
        self.archive_sha = fixture.create()["archive_sha256"]
        self.receipt = self.root / "receipt-225.json"

    def record(self):
        return replay.record(self.zip, self.archive_sha, self.receipt)

    def replay(self, digest=None):
        return replay.replay(
            self.zip, self.archive_sha, self.receipt,
            digest or bundle.digest_file(self.receipt)[1])

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" /
                                 "replay_switch_audio_evidence_report.py"), *args],
            capture_output=True, text=True, check=False)

    def test_record_twice_and_replay_report_never_claim_hardware_pass(self):
        original = self.record()
        self.assertEqual(original["result"], "DETERMINISTIC_REPORT_RECEIPT_CREATED")
        self.assertEqual(original["verification_passes"], 2)
        self.assertEqual(original["hardware_status"], "HARDWARE NOT TESTED")
        completed = self.replay(original["receipt_sha256"])
        self.assertEqual(completed["result"], "PINNED_REPORT_REPRODUCED")
        self.assertTrue(completed["report_was_unchanged"])
        self.assertEqual(completed["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(completed["manual_signoff"], "REQUIRED_NOT_AUTOMATED")

    def test_receipt_is_byte_identical_across_repeated_creation(self):
        first = self.record()
        second_path = self.root / "other-computer.json"
        second = replay.record(self.zip, self.archive_sha, second_path)
        self.assertEqual(self.receipt.read_bytes(), second_path.read_bytes())
        self.assertEqual(first["receipt_sha256"], second["receipt_sha256"])
        self.assertEqual(first["canonical_snapshot_sha256"],
                         second["canonical_snapshot_sha256"])

    def test_canonical_digest_ignores_mapping_insertion_order(self):
        a = {"b": {"z": 1, "a": 2}, "a": [3, 2]}
        b = {"a": [3, 2], "b": {"a": 2, "z": 1}}
        self.assertEqual(replay.canonical_bytes(a), replay.canonical_bytes(b))
        self.assertEqual(replay.sha256(replay.canonical_bytes(a)),
                         replay.sha256(replay.canonical_bytes(b)))

    def test_receipt_integrity_check_catches_changed_bytes(self):
        first = self.record()
        self.receipt.write_bytes(self.receipt.read_bytes() + b"\n")
        with self.assertRaisesRegex(replay.ReplayError, "RECEIPT_SHA256_MISMATCH"):
            self.replay(first["receipt_sha256"])

    def test_receipt_sha_anchor_is_mandatory_and_strict(self):
        self.record()
        for bad in ("", "ABC" * 21, "a" * 65, None):
            with self.subTest(value=bad), self.assertRaisesRegex(
                    replay.ReplayError, "expected receipt SHA-256"):
                replay.read_receipt(self.receipt, bad)

    def test_duplicate_receipt_keys_rejected_even_with_updated_anchor(self):
        self.receipt.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaises(bundle.BundleError):
            replay.read_receipt(self.receipt, bundle.digest_file(self.receipt)[1])

    def test_receipt_forged_hardware_status_is_invalid_even_with_rehashed_receipt(self):
        self.record()
        obj = json.loads(self.receipt.read_text())
        obj["hardware_status"] = "PASS"
        self.receipt.write_bytes(replay.receipt_bytes(obj))
        anchor = bundle.digest_file(self.receipt)[1]
        with self.assertRaisesRegex(replay.ReplayError, "claimed hardware PASS"):
            replay.read_receipt(self.receipt, anchor)

    def test_receipt_forged_snapshot_is_detected_even_if_rehashed(self):
        self.record()
        obj = json.loads(self.receipt.read_text())
        obj["snapshot"]["handoff_review"] = "INVESTIGATE"
        self.receipt.write_bytes(replay.receipt_bytes(obj))
        with self.assertRaisesRegex(replay.ReplayError, "SNAPSHOT_SHA256_MISMATCH"):
            replay.read_receipt(self.receipt, bundle.digest_file(self.receipt)[1])

    def test_forged_snapshot_with_updated_internal_sha_still_detects_replay_drift(self):
        self.record()
        obj = json.loads(self.receipt.read_text())
        obj["snapshot"]["handoff_review"] = "INVESTIGATE"
        obj["snapshot_sha256"] = replay.sha256(replay.canonical_bytes(obj["snapshot"]))
        self.receipt.write_bytes(replay.receipt_bytes(obj))
        with self.assertRaisesRegex(replay.ReplayError, "REPORT_DRIFT"):
            self.replay(bundle.digest_file(self.receipt)[1])

    def test_noncanonical_json_encoding_rejected_even_with_matching_anchor(self):
        self.record()
        obj = json.loads(self.receipt.read_text())
        self.receipt.write_text(json.dumps(obj, indent=4), encoding="utf-8")
        with self.assertRaisesRegex(replay.ReplayError, "NONCANONICAL_RECEIPT"):
            replay.read_receipt(self.receipt, bundle.digest_file(self.receipt)[1])

    def test_zip_corruption_detected_before_replay_report(self):
        first = self.record()
        with self.zip.open("ab") as output:
            output.write(b"\x00altered")
        with self.assertRaisesRegex(replay.ReplayError, "ARCHIVE_CHANGED"):
            self.replay(first["receipt_sha256"])

    def test_wrong_zip_anchor_rejected_when_replaying_another_build(self):
        first = self.record()
        with self.assertRaisesRegex(replay.ReplayError, "RECEIPT_REFERENCES_DIFFERENT_ARCHIVE"):
            replay.replay(self.zip, "f" * 64, self.receipt, first["receipt_sha256"])

    def test_mid_verification_zip_mutation_is_detected(self):
        real = cross_host.verified_snapshot
        def mutate_after_first(*args):
            first = real(*args)
            with self.zip.open("ab") as output:
                output.write(b"late mutation")
            return first
        with patch.object(replay.cross_host, "verified_snapshot",
                          side_effect=mutate_after_first):
            with self.assertRaisesRegex(replay.ReplayError,
                                        "ARCHIVE_CHANGED_DURING_VERIFICATION"):
                replay.stable_snapshot(self.zip, self.archive_sha)

    def test_two_different_semantic_reports_fail_as_nondeterministic(self):
        first = cross_host.verified_snapshot(self.zip, self.archive_sha)
        second = copy.deepcopy(first)
        second["handoff_review"] = "INCONCLUSIVE"
        with patch.object(replay.cross_host, "verified_snapshot",
                          side_effect=[first, second]):
            with self.assertRaisesRegex(replay.ReplayError, "NONDETERMINISTIC"):
                replay.stable_snapshot(self.zip, self.archive_sha)

    def test_receipt_never_overwrites_an_existing_file(self):
        self.record()
        original = self.receipt.read_bytes()
        with self.assertRaisesRegex(replay.ReplayError, "already exists"):
            self.record()
        self.assertEqual(original, self.receipt.read_bytes())

    def test_record_and_replay_do_not_write_to_original_archive(self):
        before = self.zip.read_bytes()
        self.record()
        self.replay()
        self.assertEqual(before, self.zip.read_bytes())

    def test_cli_valid_record_and_replay_return_zero_without_hardware_pass(self):
        a = self.cli(
            "record", str(self.zip),
            "--expected-archive-sha256", self.archive_sha,
            "--output", str(self.receipt))
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        recorded = json.loads(a.stdout)
        b = self.cli(
            "replay", str(self.zip),
            "--expected-archive-sha256", self.archive_sha,
            "--receipt", str(self.receipt),
            "--expected-receipt-sha256", recorded["receipt_sha256"])
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        self.assertEqual(json.loads(b.stdout)["result"], "PINNED_REPORT_REPRODUCED")
        self.assertEqual(json.loads(b.stdout)["hardware_status"], "HARDWARE NOT TESTED")

    def test_cli_bad_receipt_and_changed_zip_fail_closed(self):
        self.record()
        a = self.cli(
            "replay", str(self.zip),
            "--expected-archive-sha256", self.archive_sha,
            "--receipt", str(self.receipt),
            "--expected-receipt-sha256", "0" * 64)
        self.assertEqual(a.returncode, 2)
        self.assertEqual(json.loads(a.stdout)["result"], "INVALID_EVIDENCE")
        self.zip.write_bytes(self.zip.read_bytes() + b"modified")
        b = self.cli(
            "replay", str(self.zip),
            "--expected-archive-sha256", self.archive_sha,
            "--receipt", str(self.receipt),
            "--expected-receipt-sha256", bundle.digest_file(self.receipt)[1])
        self.assertEqual(b.returncode, 2)
        self.assertEqual(json.loads(b.stdout)["result"], "INVALID_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
