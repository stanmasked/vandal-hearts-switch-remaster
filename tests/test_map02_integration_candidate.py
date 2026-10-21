"""Synthetic-only tests for the MAP02 object-only integration candidate.

Creates 26 tiny disposable Git commits (no retail assets) and checks that
the integration candidate is a verifiable *unreferenced* Git object chain.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_map02_stack import AuditError
from audit_map02_full_stack import NUMBERS
from rehearse_map02_full_stack import rehearse
from map02_integration_candidate import (
    inspect_commit, make_candidate, validate_candidate,
    match_runtime_receipt,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        text=True).stdout.strip()


class IsolatedCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="map02-candidate-")
        cls.repo = Path(cls.temp.name)
        root = cls.repo
        git(root, "init", "-q")
        git(root, "config", "user.name", "MAP02 Fixture")
        git(root, "config", "user.email", "fixture@example.invalid")
        (root / "original.txt").write_text("fixture only\n", encoding="utf-8")
        git(root, "add", "original.txt")
        git(root, "commit", "-qm", "base")
        main = git(root, "rev-parse", "HEAD")
        commits = []
        for n in NUMBERS:
            (root / f"scene_{n}.txt").write_text(f"sample {n}\n",
                                                  encoding="utf-8")
            git(root, "add", f"scene_{n}.txt")
            git(root, "commit", "-qm", f"source PR #{n}")
            commits.append({"number": n, "sha": git(root, "rev-parse", "HEAD")})
        head = commits[-1]["sha"]
        cls.virtual = rehearse(root, main, commits, head)
        cls.audit = {
            "result": "PASS",
            "pr_count": 26,
            "pinned_upstream_prs": 25,
            "checked_edges": 25,
            "integration_merge_performed": False,
            "head_sha": head,
            "main_sha": main,
            "live_pr_metadata": {
                "verified": True, "open_draft_unmerged": 26,
                "head_and_base_sha_pinned": 26,
                "prs": [{"number": row["number"],
                         "head_sha": row["sha"]} for row in commits],
            },
            "upstream_ci_provenance": {
                "verified": True, "successful_exact_commit_workflows": 25,
            },
        }

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_valid_complete_26_stage_candidate(self):
        receipt = make_candidate(self.repo, self.audit, self.virtual)
        self.assertEqual(receipt["pr_count"], 26)
        self.assertEqual(receipt["changed_paths"], 26)
        self.assertEqual(receipt["source_head_sha"], self.audit["head_sha"])
        self.assertEqual(receipt["source_tree_sha"],
                         receipt["isolated_candidate_tree_sha"])
        self.assertEqual(receipt["isolated_candidate_commit_sha"],
                         self.virtual["steps"][-1]["virtual_commit"])
        self.assertFalse(receipt["merged_into_main"])
        self.assertTrue(receipt["separate_nro_and_nexium_evidence_required"])
        self.assertEqual(validate_candidate(self.repo, self.audit, self.virtual,
                                            receipt), receipt)

    def test_virtual_commit_has_exact_two_reviewed_parents(self):
        receipt = make_candidate(self.repo, self.audit, self.virtual)
        tree, parents = inspect_commit(
            self.repo, receipt["isolated_candidate_commit_sha"])
        self.assertEqual(tree, receipt["source_tree_sha"])
        self.assertEqual(parents[1], receipt["source_head_sha"])
        self.assertEqual(parents[0],
                         self.virtual["steps"][-2]["virtual_commit"])

    def test_reject_silent_change_to_source_tree(self):
        altered = copy.deepcopy(self.virtual)
        altered["steps"][9]["source_tree"] = "0" * 40
        with self.assertRaises(AuditError):
            make_candidate(self.repo, self.audit, altered)

    def test_reject_missing_virtual_commit(self):
        altered = copy.deepcopy(self.virtual)
        altered["steps"][17]["virtual_commit"] = "0" * 40
        with self.assertRaises(AuditError):
            make_candidate(self.repo, self.audit, altered)

    def test_reject_wrong_parent_chain(self):
        altered = copy.deepcopy(self.virtual)
        altered["steps"][12]["virtual_commit"] = (
            altered["steps"][11]["virtual_commit"])
        with self.assertRaises(AuditError):
            make_candidate(self.repo, self.audit, altered)

    def test_reject_wrong_pinned_pr_order(self):
        altered = copy.deepcopy(self.virtual)
        altered["steps"][0], altered["steps"][1] = (
            altered["steps"][1], altered["steps"][0])
        with self.assertRaisesRegex(AuditError, "order"):
            make_candidate(self.repo, self.audit, altered)

    def test_reject_missing_intermediate_path_record(self):
        altered = copy.deepcopy(self.virtual)
        altered["steps"][8]["path_changes"] = []
        with self.assertRaisesRegex(AuditError, "change list"):
            make_candidate(self.repo, self.audit, altered)

    def test_reject_mismatched_audit_source(self):
        altered = copy.deepcopy(self.audit)
        altered["head_sha"] = "0" * 40
        with self.assertRaisesRegex(AuditError, "different source commits"):
            make_candidate(self.repo, altered, self.virtual)

    def test_reject_changed_candidate_receipt(self):
        original = make_candidate(self.repo, self.audit, self.virtual)
        altered = copy.deepcopy(original)
        altered["steps"][0]["changed_files"] += 1
        with self.assertRaisesRegex(AuditError, "mismatch"):
            validate_candidate(self.repo, self.audit, self.virtual, altered)

    def test_reject_release_or_main_merge_assertion(self):
        altered = copy.deepcopy(self.virtual)
        altered["real_merge_performed"] = True
        with self.assertRaisesRegex(AuditError, "non-read-only"):
            make_candidate(self.repo, self.audit, altered)

    def test_accept_matching_runtime_bundle_receipt(self):
        candidate = make_candidate(self.repo, self.audit, self.virtual)
        bundle = {
            "kind": "map02-nexium-self-contained-evidence",
            "source_commit": candidate["source_head_sha"],
            "source_tree": candidate["source_tree_sha"],
            "png_count": 24,
            "file_count": 35,
            "root_sha256": "1" * 64,
            "nro_sha256": "2" * 64,
        }
        self.assertTrue(match_runtime_receipt(candidate, bundle)["same_source"])

    def test_reject_other_commit_runtime_bundle(self):
        candidate = make_candidate(self.repo, self.audit, self.virtual)
        bad_bundle = {
            "kind": "map02-nexium-self-contained-evidence",
            "source_commit": "0" * 40,
            "source_tree": candidate["source_tree_sha"],
            "png_count": 24, "file_count": 35,
            "root_sha256": "1" * 64, "nro_sha256": "2" * 64,
        }
        with self.assertRaisesRegex(AuditError, "not bound"):
            match_runtime_receipt(candidate, bad_bundle)


if __name__ == "__main__":
    unittest.main()
