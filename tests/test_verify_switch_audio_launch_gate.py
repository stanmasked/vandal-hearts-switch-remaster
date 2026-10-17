#!/usr/bin/env python3
"""Stage 230 host-only CI/archive/source/SD identity chain regressions."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_launch_gate as gate  # noqa: E402
import verify_switch_audio_live_preflight as preflight  # noqa: E402
import verify_switch_audio_build_provenance as provenance  # noqa: E402
import verify_switch_audio_sd_transfer as transfer  # noqa: E402
from test_switch_audio_ci_build_receipt import CIBuildReceiptTests  # noqa: E402
from test_verify_switch_audio_live_preflight import NOW  # noqa: E402


class LaunchGateTests(unittest.TestCase):
    def setUp(self):
        fixture = CIBuildReceiptTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        gh = fixture.fx
        gh.run["created_at"] = (NOW - timedelta(days=1)).isoformat()
        gh.artifact["created_at"] = (NOW - timedelta(hours=23)).isoformat()
        gh.artifact["expires_at"] = (NOW + timedelta(days=40)).isoformat()
        fixture.pack()
        self.gh = gh
        self.sd_root = gh.base / "mock-sd-root"
        self.sd_root.mkdir()
        self.sd_file = self.sd_root / transfer.DEFAULT_DESTINATION
        self.plan = gh.base / "operator-transfer-plan.json"
        transfer.create_plan(gh.folder, self.sd_root, self.plan)
        self.api_calls = []
        self.ref = {
            "ref": "refs/heads/" + provenance.BRANCH,
            "object": {"type": "commit", "sha": gh.sha},
        }

    def fetch(self, path):
        self.api_calls.append(path)
        if path == "/actions/runs/" + str(self.gh.run_id):
            return self.gh.run
        if path == "/actions/artifacts/" + str(self.gh.artifact_id):
            return self.gh.artifact
        if path == preflight.REF_PATH:
            return self.ref
        raise AssertionError("unexpected GitHub API path: " + path)

    def copy_sd(self):
        self.sd_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.gh.folder / self.gh.nro, self.sd_file)

    def check(self, **overrides):
        opts = {
            "api_fetch": self.fetch,
            "now": NOW,
        }
        opts.update(overrides)
        return gate.evaluate(
            self.gh.folder, self.gh.archive, self.sd_root,
            self.plan, self.gh.run_id, self.gh.artifact_id, **opts)

    def test_exact_gh_receipt_source_plan_sd_chain_gates_only_host_readiness(self):
        self.copy_sd()
        report = self.check()
        self.assertEqual(report["result"], "READY_FOR_MANUAL_DEVICE_LAUNCH")
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(report["git_sha_confirmed_by_github_at_check_time"],
                         self.gh.sha)
        self.assertEqual(report["run_id"], self.gh.run_id)
        self.assertEqual(report["artifact_id"], self.gh.artifact_id)
        self.assertEqual(report["run_attempt"], 1)
        self.assertEqual(report["installed_nro_sha256"],
                         self.gh.sha256(self.sd_file))
        self.assertEqual(len(report["verified_layers"]), 4)
        self.assertFalse(report["physical_sd_medium_attested"])
        self.assertFalse(report["physical_launch_attested"])
        self.assertFalse(report["audible_music_attested"])
        self.assertFalse(report["csv_diagnostics_attested"])
        self.assertEqual(self.api_calls[-1], preflight.REF_PATH)

    def test_missing_sd_file_is_not_ready(self):
        with self.assertRaisesRegex(transfer.TransferError, "missing"):
            self.check()

    def test_sd_same_length_corruption_is_rejected(self):
        self.copy_sd()
        data = bytearray(self.sd_file.read_bytes())
        data[-1] ^= 1
        self.sd_file.write_bytes(data)
        with self.assertRaisesRegex(transfer.TransferError, "SHA-256/size"):
            self.check()

    def test_shortened_sd_copy_cannot_be_declared_ready(self):
        self.copy_sd()
        self.sd_file.write_bytes(self.sd_file.read_bytes()[:-1])
        with self.assertRaisesRegex(transfer.TransferError, "SHA-256/size"):
            self.check()

    def test_sd_symlink_rejected_even_when_points_to_correct_source(self):
        self.sd_file.parent.mkdir(parents=True, exist_ok=True)
        self.sd_file.symlink_to(self.gh.folder / self.gh.nro)
        with self.assertRaisesRegex(transfer.TransferError, "symbolic link"):
            self.check()

    def test_old_sha_after_branch_moved_is_rejected(self):
        self.copy_sd()
        self.ref["object"]["sha"] = "b" * 40
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.check()

    def test_artifact_zip_bytes_tampered_even_when_sd_still_matches(self):
        self.copy_sd()
        with self.gh.archive.open("ab") as file:
            file.write(b"tampered")
        with self.assertRaisesRegex(provenance.ProvenanceError,
                                    "size mismatch"):
            self.check()

    def test_git_run_attempt_disagrees_with_receipt(self):
        self.copy_sd()
        self.gh.run["run_attempt"] = 2
        with self.assertRaisesRegex(provenance.ProvenanceError, "attempt"):
            self.check()

    def test_no_stage229_ci_sidecar_is_explicitly_rejected(self):
        self.copy_sd()
        self.gh.rebuild_zip([(provenance.NRO_NAME,
                              (self.gh.folder / self.gh.nro).read_bytes())])
        self.gh.artifact["size_in_bytes"] = self.gh.archive.stat().st_size
        self.gh.artifact["digest"] = "sha256:" + self.gh.sha256(self.gh.archive)
        with self.assertRaisesRegex(gate.GateError, "CI_BUILD_RECEIPT_REQUIRED"):
            self.check()

    def test_bad_run_or_artifact_requested_ids_rejected(self):
        self.copy_sd()
        for rid, aid in ((0, self.gh.artifact_id),
                         (self.gh.run_id, 0),
                         (True, self.gh.artifact_id)):
            with self.subTest(run=rid, artifact=aid), self.assertRaises(gate.GateError):
                gate.evaluate(self.gh.folder, self.gh.archive, self.sd_root,
                              self.plan, rid, aid,
                              api_fetch=self.fetch, now=NOW)

    def test_stale_run_and_expired_artifact_rejected(self):
        self.copy_sd()
        self.gh.run["created_at"] = (NOW - timedelta(days=32)).isoformat()
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.check()
        self.gh.run["created_at"] = (NOW - timedelta(days=1)).isoformat()
        self.gh.artifact["expires_at"] = (NOW - timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(provenance.ProvenanceError, "expired"):
            self.check()

    def test_evidence_nro_modified_after_planning_fails_closed(self):
        self.copy_sd()
        src = self.gh.folder / self.gh.nro
        src.write_bytes(src.read_bytes() + b"modified")
        with self.assertRaises(bundle.BundleError):
            self.check()

    def test_transfer_plan_source_commit_cannot_be_changed_after_creation(self):
        self.copy_sd()
        data = json.loads(self.plan.read_text())
        data["git_sha"] = "b" * 40
        self.plan.write_text(json.dumps(data))
        with self.assertRaisesRegex(transfer.TransferError, "source identity"):
            self.check()

    def test_sd_file_already_matching_before_plan_does_not_prove_manual_copy(self):
        self.copy_sd()
        self.plan.unlink()
        transfer.create_plan(self.gh.folder, self.sd_root, self.plan)
        report = self.check()
        self.assertEqual(report["result"], "READY_FOR_MANUAL_DEVICE_LAUNCH")
        self.assertFalse(report["manual_copy_witnessed"])
        self.assertFalse(report["physical_launch_attested"])

    def test_no_csv_sessions_not_mistaken_for_hardware_readiness(self):
        self.copy_sd()
        self.assertEqual(len(bundle.read_manifest(self.gh.folder)["sessions"]), 0)
        report = self.check()
        self.assertFalse(report["csv_diagnostics_attested"])
        self.assertEqual(report["hardware_status"], "HARDWARE NOT TESTED")

    def test_host_gate_does_not_modify_original_archive_sd_bundle_or_plan(self):
        self.copy_sd()
        watched = [
            self.gh.archive, self.sd_file,
            self.gh.folder / self.gh.nro,
            self.gh.folder / bundle.MANIFEST_NAME,
            self.plan,
        ]
        before = [x.read_bytes() for x in watched]
        self.check()
        self.assertEqual(before, [x.read_bytes() for x in watched])

    def test_invalid_cli_arguments_return_two_without_accessing_github(self):
        cmd = [sys.executable,
               str(ROOT / "tools" / "verify_switch_audio_launch_gate.py"),
               str(self.gh.folder), "--artifact-zip", str(self.gh.archive),
               "--run-id", "0", "--artifact-id", str(self.gh.artifact_id),
               "--sd-root", str(self.sd_root),
               "--transfer-plan", str(self.plan)]
        run = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["result"], "INVALID_EVIDENCE")
        self.assertEqual(json.loads(run.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
