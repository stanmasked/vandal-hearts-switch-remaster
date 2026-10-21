"""Strict offline tests for upstream MAP02 GitHub Actions evidence."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_map02_stack import AuditError
import audit_map02_upstream_ci as audit


class UpstreamCiProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.repo = "stanmasked/vandal-hearts-switch-remaster"
        self.entries = json.loads(
            (ROOT / "data/map02_full_stack_snapshot.json").read_text(
                encoding="utf-8"))["pull_requests"]
        self.sha = self.entries[0]["head_sha"]
        self.good = {
            "id": 12345, "head_sha": self.sha,
            "event": "pull_request",
            "status": "completed", "conclusion": "success",
            "html_url": f"https://github.com/{self.repo}/actions/runs/12345",
        }

    def check(self, runs):
        return audit.validate_commit_runs(self.repo, 241, self.sha, runs)

    def test_accept_exact_commit_success(self):
        x = self.check([self.good])
        self.assertEqual(x["head_sha"], self.sha)
        self.assertEqual(x["representative_id"], 12345)

    def test_reject_success_on_unrelated_commit(self):
        unrelated = dict(self.good, head_sha="0" * 40)
        with self.assertRaisesRegex(AuditError, "no successful"):
            self.check([unrelated])

    def test_reject_success_on_non_pr_event(self):
        non_pr = dict(self.good, event="workflow_dispatch")
        with self.assertRaisesRegex(AuditError, "no successful"):
            self.check([non_pr])

    def test_reject_only_queued_run(self):
        queued = dict(self.good, status="in_progress", conclusion=None)
        with self.assertRaisesRegex(AuditError, "no successful"):
            self.check([queued])

    def test_reject_completed_failure_even_with_another_success(self):
        failed = dict(self.good, id=456, conclusion="failure",
                      html_url=f"https://github.com/{self.repo}/actions/runs/456")
        with self.assertRaisesRegex(AuditError, "failed completed"):
            self.check([self.good, failed])

    def test_reject_timed_out_run(self):
        failed = dict(self.good, conclusion="timed_out")
        with self.assertRaisesRegex(AuditError, "failed completed"):
            self.check([failed])

    def test_reject_foreign_or_missing_provenance(self):
        wrong = dict(self.good, html_url="https://example.invalid/actions/runs/12345")
        with self.assertRaisesRegex(AuditError, "provenance"):
            self.check([wrong])
        wrong = dict(self.good, id=None)
        with self.assertRaisesRegex(AuditError, "provenance"):
            self.check([wrong])

    def test_reject_no_workflow_results(self):
        with self.assertRaisesRegex(AuditError, "no successful"):
            self.check([])

    def test_all_25_upstream_shas_must_have_a_matching_success(self):
        def one_success(repo, sha, token):
            self.assertEqual(repo, self.repo)
            self.assertEqual(token, "test-token")
            return [{
                "id": 101, "head_sha": sha, "event": "pull_request",
                "status": "completed", "conclusion": "success",
                "html_url": f"https://github.com/{repo}/actions/runs/101",
            }]
        with patch.object(audit, "fetch_commit_runs", side_effect=one_success):
            x = audit.audit_upstream_ci(self.repo, self.entries, "test-token")
        self.assertEqual(x["upstream_pr_count"], 25)
        self.assertEqual(x["successful_exact_commit_workflows"], 25)
        self.assertEqual(x["prs"][-1]["number"], 347)
        self.assertTrue(x["current_pr_self_run_excluded"])

    def test_no_success_for_one_upstream_blocks_complete_audit(self):
        def one_missing(repo, sha, token):
            if sha == self.entries[9]["head_sha"]:
                return []
            return [{
                "id": 101, "head_sha": sha, "event": "pull_request",
                "status": "completed", "conclusion": "success",
                "html_url": f"https://github.com/{repo}/actions/runs/101",
            }]
        with patch.object(audit, "fetch_commit_runs", side_effect=one_missing):
            with self.assertRaisesRegex(AuditError, "PR #262"):
                audit.audit_upstream_ci(self.repo, self.entries, "test-token")

    def test_current_pr_must_be_terminal_head_not_fake_sha(self):
        corrupt = [dict(x) for x in self.entries]
        corrupt[-1]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "terminal HEAD"):
            audit.audit_upstream_ci(self.repo, corrupt, "test-token")


if __name__ == "__main__":
    unittest.main()
