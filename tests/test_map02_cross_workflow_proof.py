"""Synthetic-only adversarial tests of independent MAP02 CI artifact binding."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import map02_cross_workflow_proof as proof
from map02_integration_candidate import digest
from audit_map02_stack import AuditError


class CrossWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="map02-cross-ci-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.integration = base / "integration"
        self.integration.mkdir()
        self.runtime = base / "runtime"
        self.runtime.mkdir()
        self.sha = "a" * 40
        self.tree = "b" * 40
        self.main = "c" * 40
        self.repo = "stanmasked/vandal-hearts-switch-remaster"
        self.virtual = {
            "result": "PASS", "stages": 26, "unchanged_trees": 26,
            "last_source_sha": self.sha, "final_source_tree": self.tree,
            "final_virtual_tree": self.tree, "real_merge_performed": False,
            "git_refs_updated": False,
            "steps": [
                {"number": number, "source_sha": str(i).zfill(40),
                 "source_tree": self.tree,
                 "virtual_commit": str(i+200).zfill(40),
                 "changed_file_count": 1}
                for i, number in enumerate((
                    241,243,247,250,251,252,253,256,259,262,265,270,273,
                    281,284,289,295,302,305,314,318,322,325,333,347,352))
            ],
        }
        self.virtual["steps"][-1]["source_sha"] = self.sha
        self.audit = {
            "result": "PASS", "head_sha": self.sha,
            "main_sha": self.main, "pr_count": 26,
            "pinned_upstream_prs": 25,
            "integration_merge_performed": False,
            "live_pr_metadata": {"open_draft_unmerged": 26},
            "upstream_ci_provenance": {
                "successful_exact_commit_workflows": 25},
        }
        self.candidate = {
            "kind": "map02-review-only-virtual-integration",
            "schema_version": 1,
            "source_head_sha": self.sha,
            "source_tree_sha": self.tree,
            "isolated_candidate_tree_sha": self.tree,
            "origin_main_sha": self.main,
            "pr_count": 26,
            "review_only": True,
            "merged_into_main": False,
            "input_audit_sha256": digest(self.audit),
            "input_virtual_merge_sha256": digest(self.virtual),
            "steps": [
                {"number": x["number"], "source_sha": x["source_sha"],
                 "tree_sha": x["source_tree"],
                 "virtual_commit_sha": x["virtual_commit"],
                 "changed_files": x["changed_file_count"]}
                for x in self.virtual["steps"]],
        }
        self.candidate["receipt_sha256"] = digest(self.candidate)
        self.seal = {
            "kind": "map02-point-in-time-final-ref-check",
            "source_head_sha": self.sha,
            "source_tree_sha": self.tree,
            "origin_main_sha": self.main,
            "candidate_receipt_sha256": self.candidate["receipt_sha256"],
            "fresh_live_prs": 26, "fresh_upstream_ci": 25,
            "pr_states_unchanged": True, "time_of_check_only": True,
            "main_merged": False, "branch_mutations": False,
            "integration_authorized": False,
        }
        self.seal["root_sha256"] = digest(self.seal)
        self.bundle = {
            "kind": "map02-nexium-self-contained-evidence",
            "source_commit": self.sha, "source_tree": self.tree,
            "png_count": 24, "file_count": 35,
            "root_sha256": "d" * 64,
            "nro_sha256": "e" * 64,
        }
        self.write_files()

    def write_files(self):
        sources = {
            "report.json": self.audit,
            "virtual-merge.json": self.virtual,
            "integration-candidate.json": self.candidate,
            "final-ref-check.json": self.seal,
        }
        for filename in proof.INTEGRATION_FILES:
            file = self.integration / filename
            if filename in sources:
                file.write_text(json.dumps(sources[filename]), encoding="utf-8")
            else:
                file.write_text("synthetic test only\n", encoding="utf-8")

    def validate(self):
        with patch.object(proof, "verify_runtime_bundle", return_value=self.bundle):
            return proof.verify_artifacts(
                self.integration, self.runtime, self.sha, self.tree,
                self.repo, 111, 222)

    def test_accepts_matching_independent_synthetic_reports(self):
        result = self.validate()
        self.assertTrue(result["source_and_tree_match"])
        self.assertEqual(result["verified_png"], 24)
        self.assertEqual(result["pr_count"], 26)
        self.assertFalse(result["real_merge_performed"])
        self.assertEqual(len(result["root_sha256"]), 64)

    def test_rejects_swapped_source_commit(self):
        self.bundle["source_commit"] = "f" * 40
        with self.assertRaisesRegex(AuditError, "not bound"):
            self.validate()

    def test_rejects_swapped_tree(self):
        self.bundle["source_tree"] = "f" * 40
        with self.assertRaisesRegex(AuditError, "not bound"):
            self.validate()

    def test_rejects_tampered_candidate(self):
        self.candidate["steps"][10]["tree_sha"] = "0" * 40
        self.write_files()
        with self.assertRaisesRegex(proof.CrossProofError, "SHA-256 receipt mismatch"):
            self.validate()

    def test_rejects_forged_ref_seal(self):
        self.seal["fresh_live_prs"] = 25
        self.write_files()
        with self.assertRaisesRegex(proof.CrossProofError, "final ref"):
            self.validate()

    def test_rejects_old_integration_tree(self):
        self.virtual["final_virtual_tree"] = "0" * 40
        self.write_files()
        with self.assertRaisesRegex(proof.CrossProofError, "virtual"):
            self.validate()

    def test_rejects_missing_integration_file(self):
        (self.integration / "virtual-merge.json").unlink()
        with self.assertRaisesRegex(proof.CrossProofError, "incomplete"):
            self.validate()

    def test_rejects_duplicate_json_keys(self):
        (self.integration / "report.json").write_text(
            '{"result":"PASS","result":"PASS"}', encoding="utf-8")
        with self.assertRaisesRegex(proof.CrossProofError, "duplicate"):
            self.validate()

    def test_rejects_identical_workflow_run_ids(self):
        with self.assertRaisesRegex(proof.CrossProofError, "run IDs"):
            with patch.object(proof, "verify_runtime_bundle", return_value=self.bundle):
                proof.verify_artifacts(self.integration, self.runtime,
                                       self.sha, self.tree, self.repo, 111, 111)

    def run_obj(self, id, status="completed", conclusion="success",
                sha=None, event="pull_request"):
        return {
            "id": id, "head_sha": sha or self.sha,
            "name": proof.WORKFLOW_NAME, "path": proof.WORKFLOW_PATH,
            "event": event, "status": status, "conclusion": conclusion,
            "html_url": f"https://github.com/{self.repo}/actions/runs/{id}",
        }

    def test_selects_latest_successful_exact_sha(self):
        records = [self.run_obj(40), self.run_obj(70, sha="f"*40),
                   self.run_obj(41)]
        self.assertEqual(proof.latest_successful_run(records, self.sha,
                                                       self.repo), 41)

    def test_refuses_newer_failed_run_despite_older_success(self):
        records = [self.run_obj(40),
                   self.run_obj(41, conclusion="failure")]
        with self.assertRaisesRegex(proof.CrossProofError, "not successful"):
            proof.latest_successful_run(records, self.sha, self.repo)

    def test_refuses_newer_queued_run(self):
        records = [self.run_obj(40),
                   self.run_obj(41, status="queued", conclusion=None)]
        with self.assertRaisesRegex(proof.CrossProofError, "not successful"):
            proof.latest_successful_run(records, self.sha, self.repo)

    def test_refuses_non_pr_success(self):
        with self.assertRaisesRegex(proof.CrossProofError, "no exact-commit"):
            proof.latest_successful_run(
                [self.run_obj(41, event="workflow_dispatch")],
                self.sha, self.repo)


if __name__ == "__main__":
    unittest.main()
