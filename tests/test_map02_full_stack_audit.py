"""Adversarial tests for the read-only 26-PR MAP02 integration snapshot."""
from __future__ import annotations

import copy
import json
import subprocess
import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_map02_full_stack as audit


class FullStackSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((ROOT / "data/map02_full_stack_snapshot.json")
                               .read_text(encoding="utf-8"))
        self.core = json.loads((ROOT / "data/map02_pr_stack_snapshot.json")
                               .read_text(encoding="utf-8"))

    def test_correct_26_pr_snapshot(self):
        entries = audit.validate_snapshot(self.spec, self.core)
        self.assertEqual(len(entries), 26)
        self.assertEqual(entries[0]["number"], 241)
        self.assertEqual(entries[-1]["number"], 352)
        self.assertEqual(entries[-1]["head_sha"], "HEAD")

    def test_divergence_requires_identical_40_digit_git_trees(self):
        good = "a" * 40
        self.assertIsNone(audit.verify_divergent_tree(good, good))
        with self.assertRaisesRegex(audit.AuditError, "manual reconciliation"):
            audit.verify_divergent_tree("a" * 40, "b" * 40)
        with self.assertRaisesRegex(audit.AuditError, "malformed"):
            audit.verify_divergent_tree("not-a-tree", good)

    def test_nonconflicting_dry_run_can_still_change_downstream_tree(self):
        def git(root, *args):
            p = subprocess.run(["git", "-C", str(root), *args],
                               text=True, capture_output=True, check=True)
            return p.stdout.strip()

        with tempfile.TemporaryDirectory(prefix="map02-divergence-") as tmp:
            root = Path(tmp)
            git(root, "init", "-q")
            git(root, "config", "user.name", "MAP02 Audit")
            git(root, "config", "user.email", "audit@example.invalid")
            (root / "shared.txt").write_text("base\n", encoding="utf-8")
            git(root, "add", "shared.txt")
            git(root, "commit", "-qm", "common")
            common = git(root, "rev-parse", "HEAD")
            (root / "older-only.txt").write_text("important\n", encoding="utf-8")
            git(root, "add", "older-only.txt")
            git(root, "commit", "-qm", "older-only change")
            older = git(root, "rev-parse", "HEAD")
            git(root, "checkout", "-qb", "child", common)
            (root / "child-only.txt").write_text("new\n", encoding="utf-8")
            git(root, "add", "child-only.txt")
            git(root, "commit", "-qm", "child-only change")
            newer = git(root, "rev-parse", "HEAD")
            before_status = git(root, "status", "--porcelain")
            merged_tree = audit.core_preflight.__globals__["simulate_merge"](
                root, older, newer)
            child_tree = git(root, "rev-parse", f"{newer}^{{tree}}")
            with self.assertRaisesRegex(audit.AuditError, "manual reconciliation"):
                audit.verify_divergent_tree(merged_tree, child_tree)
            self.assertEqual(git(root, "rev-parse", "HEAD"), newer)
            self.assertEqual(git(root, "status", "--porcelain"), before_status)

    def test_reject_pr_reordering(self):
        bad = copy.deepcopy(self.spec)
        bad["pull_requests"][3], bad["pull_requests"][4] = (
            bad["pull_requests"][4], bad["pull_requests"][3])
        with self.assertRaisesRegex(audit.AuditError, "order"):
            audit.validate_snapshot(bad, self.core)

    def test_reject_unpinned_upstream_head(self):
        bad = copy.deepcopy(self.spec)
        bad["pull_requests"][-2]["head_sha"] = "HEAD"
        with self.assertRaisesRegex(audit.AuditError, "upstream SHA"):
            audit.validate_snapshot(bad, self.core)

    def test_reject_pinning_self_moving_head(self):
        bad = copy.deepcopy(self.spec)
        bad["pull_requests"][-1]["head_sha"] = "0" * 40
        with self.assertRaisesRegex(audit.AuditError, "self-referential HEAD"):
            audit.validate_snapshot(bad, self.core)

    def test_reject_core_pin_changed(self):
        bad = copy.deepcopy(self.spec)
        entry = next(e for e in bad["pull_requests"] if e["number"] == 262)
        entry["head_sha"] = "0" * 40
        with self.assertRaisesRegex(audit.AuditError, "protected core PR"):
            audit.validate_snapshot(bad, self.core)

    def test_reject_undeclared_history_exception(self):
        bad = copy.deepcopy(self.spec)
        bad["permitted_divergent_edge"] = [347, 352]
        with self.assertRaisesRegex(audit.AuditError, "divergent edge"):
            audit.validate_snapshot(bad, self.core)

    def test_reject_wrong_repository(self):
        bad = copy.deepcopy(self.spec)
        bad["repo"] = "other/project"
        with self.assertRaisesRegex(audit.AuditError, "repository"):
            audit.validate_snapshot(bad, self.core)


if __name__ == "__main__":
    unittest.main()
