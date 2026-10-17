#!/usr/bin/env python3
"""Stage 229: synthetic CI build receipt and artifact provenance regressions."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import switch_audio_ci_build_receipt as receipt  # noqa: E402
import verify_switch_audio_build_provenance as provenance  # noqa: E402
import verify_switch_audio_live_preflight as live  # noqa: E402
from test_verify_switch_audio_build_provenance import GitHubArchiveCrosscheckTests  # noqa: E402
from test_verify_switch_audio_live_preflight import NOW  # noqa: E402
from datetime import timedelta  # noqa: E402


class CIBuildReceiptTests(unittest.TestCase):
    def setUp(self):
        fx = GitHubArchiveCrosscheckTests("runTest")
        fx.setUp()
        self.addCleanup(fx.doCleanups)
        self.fx = fx
        self.build_dir = fx.base / "build"
        self.build_dir.mkdir()
        self.nro = self.build_dir / receipt.NRO_NAME
        shutil.copyfile(fx.folder / fx.nro, self.nro)
        self.sidecar = self.build_dir / receipt.RECEIPT_NAME
        self.record = receipt.issue(
            self.nro, fx.sha, provenance.BRANCH,
            fx.run_id, 1, self.sidecar)
        fx.run["run_attempt"] = 1

    def pack(self, other=()):
        entries = [
            (receipt.NRO_NAME, self.nro.read_bytes()),
            (receipt.RECEIPT_NAME, self.sidecar.read_bytes()),
        ] + list(other)
        self.fx.rebuild_zip(entries)
        self.fx.refresh_artifact_hash()

    def check(self):
        self.pack()
        return self.fx.verify()

    def test_generated_receipt_bytes_match_NRO_and_not_hardware_pass(self):
        checked = receipt.verify(
            self.nro, self.sidecar, expected_git_sha=self.fx.sha,
            expected_run_id=self.fx.run_id, expected_branch=provenance.BRANCH)
        self.assertEqual(checked["result"], "CI_RECEIPT_AND_NRO_BYTES_MATCH")
        self.assertEqual(checked["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(checked["provenance"], "UNSIGNED_LOCAL_RECORD")
        self.assertEqual(checked["nro_size"], self.nro.stat().st_size)
        self.assertEqual(checked["nro_sha256"], self.fx.sha256(self.nro))

    def test_receipt_is_reproducible_for_same_inputs(self):
        other = self.build_dir / "other" / receipt.RECEIPT_NAME
        other.parent.mkdir()
        copy = other.parent / receipt.NRO_NAME
        shutil.copyfile(self.nro, copy)
        receipt.issue(copy, self.fx.sha, provenance.BRANCH,
                      self.fx.run_id, 1, other)
        self.assertEqual(self.sidecar.read_bytes(), other.read_bytes())

    def test_refuse_overwrite_existing_ci_receipt(self):
        before = self.sidecar.read_bytes()
        with self.assertRaisesRegex(receipt.ReceiptError, "unused"):
            receipt.issue(self.nro, self.fx.sha, provenance.BRANCH,
                          self.fx.run_id, 1, self.sidecar)
        self.assertEqual(self.sidecar.read_bytes(), before)

    def test_invalid_git_sha_branch_and_noninteger_run_ids_fail_closed(self):
        for field, replacement in (
            ("git_sha", "a" * 39),
            ("head_branch", "../evil"),
            ("run_id", True),
            ("run_attempt", 0),
            ("hardware_status", "PASS"),
            ("workflow_path", ".github/workflows/not-the-build.yml"),
        ):
            altered = dict(self.record)
            altered[field] = replacement
            with self.subTest(field=field), self.assertRaises(receipt.ReceiptError):
                receipt.check_record(altered)

    def test_tampered_ci_receipt_file_or_nro_is_rejected(self):
        original = self.sidecar.read_bytes()
        self.sidecar.write_bytes(original + b"\n")
        with self.assertRaisesRegex(receipt.ReceiptError, "noncanonical"):
            receipt.verify(self.nro, self.sidecar)
        self.sidecar.write_bytes(original)
        self.nro.write_bytes(self.nro.read_bytes() + b"x")
        with self.assertRaisesRegex(receipt.ReceiptError, "BUILD_RECEIPT_NRO_MISMATCH"):
            receipt.verify(self.nro, self.sidecar)

    def test_untrusted_git_run_metadata_can_be_checked_against_expected_identity(self):
        with self.assertRaisesRegex(receipt.ReceiptError, "COMMIT_MISMATCH"):
            receipt.verify(self.nro, self.sidecar, expected_git_sha="f" * 40)
        with self.assertRaisesRegex(receipt.ReceiptError, "RUN_MISMATCH"):
            receipt.verify(self.nro, self.sidecar, expected_run_id=999)
        with self.assertRaisesRegex(receipt.ReceiptError, "BRANCH_MISMATCH"):
            receipt.verify(self.nro, self.sidecar, expected_branch="main")

    def test_canonical_sidecar_is_verified_inside_official_artifact(self):
        report = self.check()
        self.assertEqual(report["comparison"],
                         "CONSISTENT_WITH_PROVIDED_GITHUB_METADATA")
        packed = report["verified_archive"]
        self.assertEqual(packed["ci_receipt_state"], "VERIFIED_UNTRUSTED")
        self.assertEqual(packed["ci_receipt"]["git_sha"], self.fx.sha)
        self.assertEqual(packed["ci_receipt"]["run_attempt"], 1)
        self.assertEqual(packed["nro_sha256"], self.fx.sha256(self.nro))

    def test_wrong_run_id_is_rejected_even_when_zip_hash_is_valid(self):
        value = dict(self.record)
        value["run_id"] += 1
        self.sidecar.write_bytes(receipt.json_bytes(value))
        with self.assertRaisesRegex(provenance.ProvenanceError, "run ID"):
            self.check()

    def test_wrong_run_attempt_is_rejected_even_with_same_commit(self):
        self.fx.run["run_attempt"] = 2
        with self.assertRaisesRegex(provenance.ProvenanceError, "attempt"):
            self.check()

    def test_wrong_commit_in_receipt_is_rejected_against_run_metadata(self):
        value = dict(self.record)
        value["git_sha"] = "f" * 40
        self.sidecar.write_bytes(receipt.json_bytes(value))
        with self.assertRaisesRegex(provenance.ProvenanceError, "commit"):
            self.check()

    def test_wrong_branch_in_receipt_rejected_against_run_metadata(self):
        value = dict(self.record)
        value["head_branch"] = "main"
        self.sidecar.write_bytes(receipt.json_bytes(value))
        with self.assertRaisesRegex(provenance.ProvenanceError, "branch"):
            self.check()

    def test_receipt_claiming_different_NRO_hash_rejected_inside_zip(self):
        value = dict(self.record)
        value["nro"] = {**self.record["nro"], "sha256": "f" * 64}
        self.sidecar.write_bytes(receipt.json_bytes(value))
        with self.assertRaisesRegex(provenance.ProvenanceError, "fingerprint"):
            self.check()

    def test_extra_file_in_zip_rejected_not_silently_ignored(self):
        self.pack([("unexpected.txt", b"extra data")])
        with self.assertRaisesRegex(provenance.ProvenanceError, "unexpected non-NRO"):
            self.fx.verify()

    def test_sidecar_in_different_directory_from_NRO_rejected(self):
        self.fx.rebuild_zip([
            ("build/" + receipt.NRO_NAME, self.nro.read_bytes()),
            (receipt.RECEIPT_NAME, self.sidecar.read_bytes()),
        ])
        self.fx.refresh_artifact_hash()
        with self.assertRaisesRegex(provenance.ProvenanceError, "beside the NRO"):
            self.fx.verify()

    def test_duplicate_sidecar_rejected(self):
        self.fx.rebuild_zip([
            (receipt.NRO_NAME, self.nro.read_bytes()),
            (receipt.RECEIPT_NAME, self.sidecar.read_bytes()),
            ("build/" + receipt.RECEIPT_NAME, self.sidecar.read_bytes()),
        ])
        self.fx.refresh_artifact_hash()
        with self.assertRaisesRegex(provenance.ProvenanceError, "multiple build receipts"):
            self.fx.verify()

    def test_bad_or_duplicate_json_keys_rejected_in_zip(self):
        self.fx.rebuild_zip([
            (receipt.NRO_NAME, self.nro.read_bytes()),
            (receipt.RECEIPT_NAME, b'{"schema":"v1","schema":"v2"}'),
        ])
        self.fx.refresh_artifact_hash()
        with self.assertRaisesRegex(provenance.ProvenanceError, "invalid CI build receipt"):
            self.fx.verify()

    def test_legacy_artifact_without_sidecar_stays_explicitly_unattested(self):
        self.fx.rebuild_zip([(receipt.NRO_NAME, self.nro.read_bytes())])
        self.fx.refresh_artifact_hash()
        report = self.fx.verify()
        self.assertEqual(report["verified_archive"]["ci_receipt_state"],
                         "ABSENT_LEGACY_ARTIFACT")
        self.assertIsNone(report["verified_archive"]["ci_receipt"])

    def test_live_preflight_binds_sidecar_to_real_run_record(self):
        self.fx.run["created_at"] = (NOW - timedelta(days=1)).isoformat()
        self.fx.artifact["created_at"] = (NOW - timedelta(hours=23)).isoformat()
        self.fx.artifact["expires_at"] = (NOW + timedelta(days=40)).isoformat()
        ref = {"ref": "refs/heads/" + provenance.BRANCH,
               "object": {"type": "commit", "sha": self.fx.sha}}
        self.pack()
        def mock_fetch(path):
            if path == f"/actions/runs/{self.fx.run_id}":
                return self.fx.run
            if path == f"/actions/artifacts/{self.fx.artifact_id}":
                return self.fx.artifact
            if path == live.REF_PATH:
                return ref
            raise AssertionError(path)
        checked = live.evaluate(self.fx.folder, self.fx.archive,
                                self.fx.run_id, self.fx.artifact_id,
                                api_fetch=mock_fetch, now=NOW)
        self.assertEqual(checked["result"], "MATCHED_CURRENT_HEAD_AT_CHECK_TIME")
        self.assertEqual(checked["verified_archive"]["ci_receipt_state"],
                         "VERIFIED_UNTRUSTED")
        self.fx.run["run_attempt"] = 2
        with self.assertRaisesRegex(provenance.ProvenanceError, "attempt"):
            live.evaluate(self.fx.folder, self.fx.archive,
                          self.fx.run_id, self.fx.artifact_id,
                          api_fetch=mock_fetch, now=NOW)

    def test_cli_generates_and_verifies_without_changing_NRO(self):
        self.sidecar.unlink()
        args = [sys.executable, str(ROOT / "tools" /
                                    "switch_audio_ci_build_receipt.py")]
        nro_before = self.nro.read_bytes()
        output = subprocess.run([
            *args, "create", str(self.nro),
            "--git-sha", self.fx.sha,
            "--branch", provenance.BRANCH,
            "--run-id", str(self.fx.run_id), "--run-attempt", "1",
            "--output", str(self.sidecar)], capture_output=True,
            text=True, check=False)
        self.assertEqual(output.returncode, 0, output.stdout + output.stderr)
        check = subprocess.run([
            *args, "verify", str(self.nro), "--receipt", str(self.sidecar),
            "--expected-git-sha", self.fx.sha,
            "--expected-run-id", str(self.fx.run_id),
            "--expected-branch", provenance.BRANCH], capture_output=True,
            text=True, check=False)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertEqual(json.loads(check.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")
        self.assertEqual(self.nro.read_bytes(), nro_before)

    def test_cli_wrong_run_hash_does_not_claim_ci_or_hardware_pass(self):
        args = [sys.executable, str(ROOT / "tools" /
                                    "switch_audio_ci_build_receipt.py"),
                "verify", str(self.nro), "--receipt", str(self.sidecar),
                "--expected-run-id", "999"]
        failed = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(json.loads(failed.stdout)["result"], "INVALID_EVIDENCE")
        self.assertEqual(json.loads(failed.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
