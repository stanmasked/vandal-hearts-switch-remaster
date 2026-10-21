"""Adversarial checks of the final read-only remote ref/CI seal."""
from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import test_map02_integration_candidate as fixture
import map02_final_ref_lock as lock
from map02_integration_candidate import make_candidate
from audit_map02_stack import AuditError


class FinalRefLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.IsolatedCandidateTests.setUpClass()
        cls.repo = fixture.IsolatedCandidateTests.repo
        cls.audit = copy.deepcopy(fixture.IsolatedCandidateTests.audit)
        cls.virtual = fixture.IsolatedCandidateTests.virtual
        cls.candidate = make_candidate(cls.repo, cls.audit, cls.virtual)
        cls.entries = [
            {"number": x["number"], "head_sha": x["source_sha"],
             "head_branch": f"synthetic/branch-{x['number']}",
             "base_branch": ("main" if i == 0
                             else f"synthetic/branch-{cls.virtual['steps'][i-1]['number']}")}
            for i, x in enumerate(cls.virtual["steps"])
        ]
        cls.entries[-1]["head_sha"] = "HEAD"
        cls.spec = {"repo": "stanmasked/vandal-hearts-switch-remaster"}
        cls.live = []
        for i, entry in enumerate(cls.entries):
            parent_sha = (cls.audit["main_sha"] if i == 0
                          else cls.virtual["steps"][i - 1]["source_sha"])
            cls.live.append({
                "number": entry["number"], "state": "open",
                "draft": True, "merged_at": None,
                "head": {
                    "ref": entry["head_branch"],
                    "sha": cls.virtual["steps"][i]["source_sha"],
                    "repo": {"full_name": cls.spec["repo"]},
                },
                "base": {
                    "ref": entry["base_branch"], "sha": parent_sha,
                    "repo": {"full_name": cls.spec["repo"]},
                },
            })
        cls.audit["live_pr_metadata"]["prs"] = [
            {"number": item["number"], "state": "open", "draft": True,
             "head_branch": item["head"]["ref"],
             "base_branch": item["base"]["ref"],
             "head_sha": item["head"]["sha"],
             "base_sha": item["base"]["sha"]}
            for item in cls.live
        ]
        cis = [
            {"number": entry["number"], "head_sha": cls.live[i]["head"]["sha"],
             "passed_runs": 1,
             "representative_id": 1111 + i,
             "representative_url": f"https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/{1111+i}",
             "conclusion": "success"}
            for i, entry in enumerate(cls.entries[:-1])
        ]
        cls.audit["upstream_ci_provenance"]["prs"] = cis
        cls.audit["upstream_ci_provenance"]["upstream_pr_count"] = 25
        cls.upstream = {
            "verified": True, "upstream_pr_count": 25,
            "successful_exact_commit_workflows": 25,
            "current_pr_self_run_excluded": True, "prs": copy.deepcopy(cis),
        }
        cls.candidate = make_candidate(cls.repo, cls.audit, cls.virtual)

    @classmethod
    def tearDownClass(cls):
        fixture.IsolatedCandidateTests.tearDownClass()

    def check(self, *, live=None, main=None, upstream=None, audit=None):
        with patch.object(lock, "validate_snapshot", return_value=self.entries):
            return lock.validate_last_snapshot(
                self.repo, self.spec, {}, self.audit if audit is None else audit,
                self.virtual, self.candidate,
                copy.deepcopy(self.live) if live is None else live,
                self.audit["main_sha"] if main is None else main,
                copy.deepcopy(self.upstream) if upstream is None else upstream,
            )

    def test_accept_26_unchanged_open_draft_prs_and_ci_receipts(self):
        x = self.check()
        self.assertEqual(x["fresh_live_prs"], 26)
        self.assertEqual(x["fresh_upstream_ci"], 25)
        self.assertTrue(x["time_of_check_only"])
        self.assertFalse(x["integration_authorized"])
        self.assertEqual(x["candidate_receipt_sha256"],
                         self.candidate["receipt_sha256"])
        self.assertEqual(len(x["root_sha256"]), 64)

    def test_refuse_main_moving_during_ci(self):
        with self.assertRaisesRegex(AuditError, "main advanced"):
            self.check(main="0" * 40)

    def test_refuse_last_pr_moving_during_ci(self):
        live = copy.deepcopy(self.live)
        live[-1]["head"]["sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "head SHA changed"):
            self.check(live=live)

    def test_refuse_modified_base_branch_even_when_sha_same(self):
        live = copy.deepcopy(self.live)
        live[3]["base"]["ref"] = "main"
        with self.assertRaisesRegex(AuditError, "retargeted"):
            self.check(live=live)

    def test_refuse_changed_draft_status(self):
        live = copy.deepcopy(self.live)
        live[13]["draft"] = False
        with self.assertRaisesRegex(AuditError, "no longer open"):
            self.check(live=live)

    def test_refuse_missing_current_run_in_upstream_chain(self):
        upstream = copy.deepcopy(self.upstream)
        upstream["prs"][0]["passed_runs"] = 0
        with self.assertRaisesRegex(AuditError, "pinned upstream CI"):
            self.check(upstream=upstream)

    def test_refuse_changed_upstream_ci_head(self):
        upstream = copy.deepcopy(self.upstream)
        upstream["prs"][7]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "pinned upstream CI"):
            self.check(upstream=upstream)

    def test_refuse_changed_candidate_receipt(self):
        old = copy.deepcopy(self.audit)
        old["head_sha"] = "0" * 40
        with self.assertRaises(AuditError):
            self.check(audit=old)

    def test_refuse_lost_original_pr_snapshot(self):
        old = copy.deepcopy(self.audit)
        del old["live_pr_metadata"]["prs"]
        with self.assertRaisesRegex(AuditError, "after original audit"):
            self.check(audit=old)

    def test_refuse_cross_repository_pr(self):
        live = copy.deepcopy(self.live)
        live[1]["head"]["repo"]["full_name"] = "other/repo"
        with self.assertRaisesRegex(AuditError, "another repository"):
            self.check(live=live)

    def test_refuse_absent_github_token(self):
        with self.assertRaisesRegex(AuditError, "missing GH_TOKEN"):
            lock.make_last_seal(self.repo, self.spec, {}, self.audit,
                                self.virtual, self.candidate, "")


if __name__ == "__main__":
    unittest.main()
