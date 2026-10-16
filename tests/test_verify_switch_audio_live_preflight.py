#!/usr/bin/env python3
"""Stage 217: offline synthetic API responses for the online preflight policy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from test_verify_switch_audio_build_provenance import GitHubArchiveCrosscheckTests  # noqa: E402
import verify_switch_audio_build_provenance as provenance  # noqa: E402
import verify_switch_audio_live_preflight as preflight  # noqa: E402

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


class LiveArtifactPreflightTests(unittest.TestCase):
    def setUp(self):
        fixture = GitHubArchiveCrosscheckTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        fixture.run["created_at"] = (NOW - timedelta(days=1)).isoformat()
        fixture.artifact["created_at"] = (NOW - timedelta(hours=23)).isoformat()
        fixture.artifact["expires_at"] = (NOW + timedelta(days=40)).isoformat()
        self.ref = {
            "ref": "refs/heads/" + provenance.BRANCH,
            "object": {"type": "commit", "sha": fixture.sha},
        }
        self.calls = []

    def fetch(self, path):
        self.calls.append(path)
        if path == f"/actions/runs/{self.fixture.run_id}":
            return self.fixture.run
        if path == f"/actions/artifacts/{self.fixture.artifact_id}":
            return self.fixture.artifact
        if path == preflight.REF_PATH:
            return self.ref
        raise AssertionError(f"unexpected API call: {path}")

    def verify(self, **kwargs):
        return preflight.evaluate(
            self.fixture.folder, self.fixture.archive,
            self.fixture.run_id, self.fixture.artifact_id,
            api_fetch=self.fetch, now=NOW, **kwargs)

    def test_current_commit_archive_exact_and_no_hardware_pass(self):
        result = self.verify()
        self.assertEqual(result["result"], "MATCHED_CURRENT_HEAD_AT_CHECK_TIME")
        self.assertEqual(result["head_sha_at_check_time"], self.fixture.sha)
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["build_provenance"],
                         "GITHUB_HTTPS_METADATA_AND_BYTE_MATCH_NOT_SIGNED")
        self.assertEqual(self.calls[-1], preflight.REF_PATH)
        self.assertEqual(result["verified_archive"]["nro_sha256"],
                         self.fixture.sha256(self.fixture.folder / self.fixture.nro))

    def test_rejects_old_nro_after_branch_advances(self):
        self.ref["object"]["sha"] = "e" * 40
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.verify()

    def test_rejects_run_or_artifact_response_with_another_id(self):
        self.fixture.run["id"] += 1
        with self.assertRaisesRegex(provenance.ProvenanceError, "run URL|manifest CI"):
            self.verify()
        self.fixture.run["id"] -= 1
        self.fixture.artifact["id"] += 1
        with self.assertRaisesRegex(provenance.ProvenanceError,
                                    "artifact metadata URL"):
            self.verify()

    def test_rejects_old_run_even_when_branch_same(self):
        self.fixture.run["created_at"] = (NOW - timedelta(days=32)).isoformat()
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.verify()

    def test_age_bound_is_configurable_and_validated(self):
        self.fixture.run["created_at"] = (NOW - timedelta(days=25)).isoformat()
        self.fixture.artifact["created_at"] = (NOW - timedelta(days=24)).isoformat()
        self.assertEqual(self.verify(max_age_days=30)["max_run_age_days"], 30)
        with self.assertRaisesRegex(provenance.ProvenanceError, "STALE_BUILD"):
            self.verify(max_age_days=14)
        with self.assertRaisesRegex(provenance.ProvenanceError, "max age"):
            self.verify(max_age_days=0)

    def test_rejects_expired_and_future_artifact(self):
        self.fixture.artifact["expires_at"] = (NOW - timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(provenance.ProvenanceError, "expired by timestamp"):
            self.verify()
        self.fixture.artifact["expires_at"] = (NOW + timedelta(days=10)).isoformat()
        self.fixture.artifact["created_at"] = (NOW + timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(provenance.ProvenanceError, "future GitHub timestamp"):
            self.verify()

    def test_rejects_wrong_branch_ref_or_tag(self):
        self.ref["ref"] = "refs/heads/main"
        with self.assertRaisesRegex(provenance.ProvenanceError, "branch reference"):
            self.verify()
        self.ref["ref"] = "refs/heads/" + provenance.BRANCH
        self.ref["object"]["type"] = "tag"
        with self.assertRaisesRegex(provenance.ProvenanceError, "reference a commit"):
            self.verify()

    def test_rejects_missing_or_naive_run_time(self):
        del self.fixture.run["created_at"]
        with self.assertRaisesRegex(provenance.ProvenanceError, "missing GitHub timestamp"):
            self.verify()
        self.fixture.run["created_at"] = "2026-10-16T12:00:00"
        with self.assertRaisesRegex(provenance.ProvenanceError, "timezone"):
            self.verify()

    def test_rejects_replaced_archive_even_if_branch_head_unchanged(self):
        self.fixture.archive.write_bytes(b"not the original ZIP")
        with self.assertRaisesRegex(provenance.ProvenanceError, "size mismatch"):
            self.verify()

    def test_rejects_modified_nro_without_online_requests(self):
        with (self.fixture.folder / self.fixture.nro).open("ab") as file:
            file.write(b"modified")
        from verify_switch_audio_bundle import BundleError
        with self.assertRaisesRegex(BundleError, "SHA-256 mismatch"):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_endpoint_allowlist_blocks_arbitrary_hosts_and_paths(self):
        for bad in (
            "//evil.example/path", "/user", "/actions/runs/0",
            "/actions/artifacts/-1", "/git/ref/heads/main",
        ):
            with self.subTest(url=bad), self.assertRaisesRegex(
                    provenance.ProvenanceError, "disallowed"):
                preflight.fetch_github_json(bad)

    def test_cli_rejects_invalid_ids_without_network(self):
        command = [sys.executable,
                   str(ROOT / "tools" / "verify_switch_audio_live_preflight.py"),
                   str(self.fixture.folder),
                   "--artifact-zip", str(self.fixture.archive),
                   "--run-id", "0", "--artifact-id", str(self.fixture.artifact_id)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["result"], "FAILED")
        self.assertEqual(json.loads(result.stdout)["hardware_status"],
                         "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
