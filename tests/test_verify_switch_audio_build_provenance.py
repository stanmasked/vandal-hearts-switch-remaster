#!/usr/bin/env python3
"""Stage 216: synthetic GitHub metadata and ZIP consistency regressions."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from test_verify_switch_audio_bundle import synthetic_structural_nro  # noqa: E402
import verify_switch_audio_bundle as bundle  # noqa: E402
import verify_switch_audio_build_provenance as check  # noqa: E402


class GitHubArchiveCrosscheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.folder = self.base / "evidence"
        (self.folder / "nro").mkdir(parents=True)
        self.nro = "nro/vandal-hearts-prototype.nro"
        (self.folder / self.nro).write_bytes(synthetic_structural_nro())
        self.sha = "a" * 40
        self.run_id = 13371
        self.artifact_id = 8948
        self.run_url = f"https://github.com/{check.REPOSITORY}/actions/runs/{self.run_id}"
        bundle.create(self.folder, self.nro, [], self.sha, self.run_url)
        self.archive = self.base / "downloaded.zip"
        self.rebuild_zip()
        self.run = {
            "id": self.run_id,
            "name": check.WORKFLOW_NAME,
            "path": check.WORKFLOW_PATH,
            "status": "completed",
            "conclusion": "success",
            "head_branch": check.BRANCH,
            "head_sha": self.sha,
            "repository": {"full_name": check.REPOSITORY},
            "html_url": self.run_url,
        }
        self.artifact = {
            "id": self.artifact_id,
            "name": check.ARTIFACT_NAME,
            "expired": False,
            "size_in_bytes": self.archive.stat().st_size,
            "digest": "sha256:" + self.sha256(self.archive),
            "url": f"https://api.github.com/repos/{check.REPOSITORY}/actions/artifacts/{self.artifact_id}",
            "workflow_run": {"id": self.run_id,
                             "head_branch": check.BRANCH,
                             "head_sha": self.sha},
        }
        self.run_path = self.base / "run.json"
        self.artifact_path = self.base / "artifact.json"
        self.write_snapshots()

    @staticmethod
    def sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def rebuild_zip(self, entries=None):
        if entries is None:
            entries = [(check.NRO_NAME, (self.folder / self.nro).read_bytes())]
        with zipfile.ZipFile(self.archive, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)

    def refresh_artifact_hash(self):
        self.artifact["size_in_bytes"] = self.archive.stat().st_size
        self.artifact["digest"] = "sha256:" + self.sha256(self.archive)
        self.write_snapshots()

    def write_snapshots(self):
        self.run_path.write_text(json.dumps(self.run), encoding="utf-8")
        self.artifact_path.write_text(json.dumps(self.artifact), encoding="utf-8")

    def verify(self):
        self.write_snapshots()
        return check.crosscheck(self.folder, self.archive,
                                self.run_path, self.artifact_path)

    def test_verified_archive_still_not_authenticity_or_hardware_pass(self):
        result = self.verify()
        self.assertEqual(result["comparison"], "CONSISTENT_WITH_PROVIDED_GITHUB_METADATA")
        self.assertEqual(result["build_provenance"], "LOCAL_METADATA_CROSSCHECK_NOT_SIGNED")
        self.assertEqual(result["hardware_status"], "HARDWARE NOT TESTED")
        self.assertEqual(result["git_sha"], self.sha)
        self.assertEqual(result["verified_archive"]["nro_sha256"],
                         self.sha256(self.folder / self.nro))
        self.assertIn("not a signed", result["limitations"])

    def test_rejects_different_commit(self):
        self.run["head_sha"] = "b" * 40
        with self.assertRaisesRegex(check.ProvenanceError, "commit"):
            self.verify()

    def test_rejects_wrong_workflow_branch_or_repository(self):
        for key, changed, message in (
                ("name", "Other workflow", "workflow identity"),
                ("head_branch", "main", "branch"),
                ("path", ".github/workflows/other.yml", "workflow identity")):
            prior = self.run[key]
            self.run[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(check.ProvenanceError, message):
                self.verify()
            self.run[key] = prior
        self.run["repository"]["full_name"] = "other/repo"
        with self.assertRaisesRegex(check.ProvenanceError, "repository"):
            self.verify()

    def test_rejects_failed_or_in_progress_run(self):
        self.run["conclusion"] = "failure"
        with self.assertRaisesRegex(check.ProvenanceError, "not completed"):
            self.verify()
        self.run["conclusion"] = "success"
        self.run["status"] = "in_progress"
        with self.assertRaisesRegex(check.ProvenanceError, "not completed"):
            self.verify()

    def test_rejects_wrong_run_and_artifact_correlation(self):
        self.artifact["workflow_run"]["id"] += 1
        with self.assertRaisesRegex(check.ProvenanceError, "another workflow run"):
            self.verify()
        self.artifact["workflow_run"]["id"] = self.run_id
        self.artifact["workflow_run"]["head_sha"] = "b" * 40
        with self.assertRaisesRegex(check.ProvenanceError, "another workflow run"):
            self.verify()

    def test_rejects_expired_wrong_name_or_different_url(self):
        self.artifact["expired"] = True
        with self.assertRaisesRegex(check.ProvenanceError, "expired"):
            self.verify()
        self.artifact["expired"] = False
        self.artifact["name"] = "audout-standalone-probe"
        with self.assertRaisesRegex(check.ProvenanceError, "artifact name"):
            self.verify()
        self.artifact["name"] = check.ARTIFACT_NAME
        self.artifact["url"] = "https://api.github.com/repos/other/repo/actions/artifacts/8948"
        with self.assertRaisesRegex(check.ProvenanceError, "URL"):
            self.verify()

    def test_rejects_changed_archive_without_mutating_metadata(self):
        with self.archive.open("ab") as file:
            file.write(b"changed")
        with self.assertRaisesRegex(check.ProvenanceError, "size mismatch"):
            self.verify()

    def test_rejects_rehashed_wrong_binary(self):
        self.rebuild_zip([(check.NRO_NAME, b"not the original NRO")])
        self.refresh_artifact_hash()
        with self.assertRaisesRegex(check.ProvenanceError, "NRO size disagrees"):
            self.verify()

    def test_rejects_zip_traversal_and_duplicates(self):
        for entries, expected in (
                ([("../unexpected", b"x"), (check.NRO_NAME, synthetic_structural_nro())],
                 "unsafe ZIP member"),
                ([(check.NRO_NAME, synthetic_structural_nro()),
                  (check.NRO_NAME, synthetic_structural_nro())],
                 "duplicate ZIP member")):
            self.rebuild_zip(entries)
            self.refresh_artifact_hash()
            with self.subTest(expected=expected), self.assertRaisesRegex(
                    check.ProvenanceError, expected):
                self.verify()

    def test_rejects_symlink_in_zip(self):
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr(info, "../../outside")
            archive.writestr(check.NRO_NAME, synthetic_structural_nro())
        self.refresh_artifact_hash()
        with self.assertRaisesRegex(check.ProvenanceError, "symbolic link"):
            self.verify()

    def test_rejects_missing_ci_run_url(self):
        manifest_path = self.folder / bundle.MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["ci_run_url"] = ""
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(check.ProvenanceError, "manifest CI URL"):
            self.verify()

    def test_rejects_modified_verified_bundle_nro(self):
        with (self.folder / self.nro).open("ab") as file:
            file.write(b"tampered")
        with self.assertRaisesRegex(bundle.BundleError, "SHA-256 mismatch"):
            self.verify()

    def test_cli_exit_codes_and_failure_status(self):
        args = [sys.executable, str(ROOT / "tools" / "verify_switch_audio_build_provenance.py"),
                str(self.folder), "--artifact-zip", str(self.archive),
                "--run-json", str(self.run_path),
                "--artifact-json", str(self.artifact_path)]
        okay = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(okay.returncode, 0, okay.stdout + okay.stderr)
        self.assertEqual(json.loads(okay.stdout)["hardware_status"], "HARDWARE NOT TESTED")
        self.artifact["digest"] = "sha256:" + ("0" * 64)
        self.write_snapshots()
        failure = subprocess.run(args, capture_output=True, text=True, check=False)
        self.assertEqual(failure.returncode, 2, failure.stdout + failure.stderr)
        self.assertEqual(json.loads(failure.stdout)["comparison"], "FAILED")
        self.assertEqual(json.loads(failure.stdout)["hardware_status"], "HARDWARE NOT TESTED")


if __name__ == "__main__":
    unittest.main()
