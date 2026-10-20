"""Adversarial, offline-only tests for current GitHub metadata on all MAP02 PRs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_map02_pr_metadata import (
    validate_branch_contract, validate_live_prs, fetch_live_prs,
)
from audit_map02_stack import AuditError


class LivePullRequestMetadataTests(unittest.TestCase):
    def setUp(self):
        self.entries = json.loads(
            (ROOT / "data/map02_full_stack_snapshot.json").read_text(
                encoding="utf-8"))["pull_requests"]
        self.repo = "stanmasked/vandal-hearts-switch-remaster"
        self.head = "a" * 40
        self.main = "b" * 40
        self.merge_base = "c" * 40
        self.live = []
        for idx, row in enumerate(self.entries):
            expected_base = (
                self.main if idx == 0
                else self.merge_base if row["number"] == 265
                else self.entries[idx - 1]["head_sha"]
            )
            self.live.append({
                "number": row["number"],
                "state": "open", "draft": True, "merged_at": None,
                "head": {
                    "ref": row["head_branch"],
                    "sha": (self.head if row["head_sha"] == "HEAD"
                            else row["head_sha"]),
                    "repo": {"full_name": self.repo},
                },
                "base": {
                    "ref": row["base_branch"],
                    "sha": expected_base,
                    "repo": {"full_name": self.repo},
                },
            })

    def check(self, records=None):
        return validate_live_prs(
            self.repo, self.entries, self.live if records is None else records,
            self.head, self.main, self.merge_base)

    def test_accepts_all_26_live_draft_branches_and_pinned_shas(self):
        self.assertEqual(len(self.entries), 26)
        self.assertEqual(self.check()["open_draft_unmerged"], 26)
        self.assertEqual(self.check()["head_and_base_sha_pinned"], 26)

    def test_rejects_draft_switched_to_ready(self):
        actual = copy.deepcopy(self.live)
        actual[1]["draft"] = False
        with self.assertRaisesRegex(AuditError, "no longer open"):
            self.check(actual)

    def test_rejects_closed_or_merged_pr(self):
        for key, value in (("state", "closed"), ("merged_at", "2026-10-21T00:00:00Z")):
            actual = copy.deepcopy(self.live)
            actual[10][key] = value
            with self.assertRaisesRegex(AuditError, "no longer open"):
                self.check(actual)

    def test_rejects_base_retarget_even_if_commit_is_unchanged(self):
        actual = copy.deepcopy(self.live)
        actual[24]["base"]["ref"] = "main"
        with self.assertRaisesRegex(AuditError, "retargeted"):
            self.check(actual)

    def test_rejects_live_upstream_head_movement(self):
        actual = copy.deepcopy(self.live)
        actual[9]["head"]["sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "head SHA changed"):
            self.check(actual)

    def test_rejects_wrong_upstream_base_sha(self):
        actual = copy.deepcopy(self.live)
        actual[9]["base"]["sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "base SHA changed"):
            self.check(actual)

    def test_rejects_divergent_265_base_retarget(self):
        actual = copy.deepcopy(self.live)
        actual[10]["base"]["sha"] = self.entries[9]["head_sha"]
        with self.assertRaisesRegex(AuditError, "base SHA changed"):
            self.check(actual)

    def test_rejects_cross_repository_pr_head(self):
        actual = copy.deepcopy(self.live)
        actual[12]["head"]["repo"]["full_name"] = "foreign/fork"
        with self.assertRaisesRegex(AuditError, "another repository"):
            self.check(actual)

    def test_rejects_missing_metadata_or_wrong_response_number(self):
        for key, value in (("head", None), ("number", 999)):
            actual = copy.deepcopy(self.live)
            actual[6][key] = value
            with self.assertRaises(AuditError):
                self.check(actual)

    def test_manifest_base_chain_is_explicit_and_closed(self):
        validate_branch_contract(self.entries)
        incorrect = copy.deepcopy(self.entries)
        incorrect[18]["base_branch"] = "main"
        with self.assertRaisesRegex(AuditError, "base contract changed"):
            validate_branch_contract(incorrect)

    def test_missing_token_cannot_bypass_live_gate(self):
        with self.assertRaisesRegex(AuditError, "token required"):
            fetch_live_prs(self.repo, self.entries, "")


if __name__ == "__main__":
    unittest.main()
