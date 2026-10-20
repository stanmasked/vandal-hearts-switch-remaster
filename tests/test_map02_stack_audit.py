"""Unit tests for read-only stacked MAP02 integration preflight.

These local test repositories are generated from scratch. They contain
no copyrighted game data, and test git merge-tree without merging HEAD.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_map02_stack as audit

ROOT = Path(__file__).resolve().parents[1]


def run(root, *args):
    proc = subprocess.run(
        ["git", "-C", str(root), *args], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode:
        raise AssertionError(
            f"git {args}: {proc.returncode} / {proc.stderr}")
    return proc.stdout.strip()


class IntegrationPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(
            (ROOT / "data/map02_pr_stack_snapshot.json").read_text(
                encoding="utf-8"))

    def test_known_snapshot_is_well_formed(self):
        self.assertEqual(
            [p["number"] for p in audit.validate_manifest(self.snapshot)],
            audit.EXPECTED_ORDER)
        self.assertEqual(self.snapshot["allowed_divergent_edge"], [262, 265])

    def test_reject_non_monotonic_or_missing_pr(self):
        invalid = json.loads(json.dumps(self.snapshot))
        invalid["pull_requests"].pop()
        with self.assertRaisesRegex(audit.AuditError, "ordering"):
            audit.validate_manifest(invalid)

    def test_reject_invalid_revision_or_branch(self):
        invalid = json.loads(json.dumps(self.snapshot))
        invalid["pull_requests"][4]["head_sha"] = "not-a-git-commit"
        with self.assertRaisesRegex(audit.AuditError, "invalid pinned SHA"):
            audit.validate_manifest(invalid)
        invalid = json.loads(json.dumps(self.snapshot))
        invalid["pull_requests"][4]["base_branch"] = ""
        with self.assertRaisesRegex(audit.AuditError, "missing base"):
            audit.validate_manifest(invalid)

    def test_reject_added_duplicate_or_unsafe_file_paths(self):
        invalid = json.loads(json.dumps(self.snapshot))
        invalid["preserved_paths"].append(invalid["preserved_paths"][0])
        with self.assertRaisesRegex(audit.AuditError, "duplicate"):
            audit.validate_manifest(invalid)
        invalid = json.loads(json.dumps(self.snapshot))
        invalid["preserved_paths"].append("../../not-allowed")
        with self.assertRaisesRegex(audit.AuditError, "unsafe"):
            audit.validate_manifest(invalid)

    def test_refuse_new_original_game_binaries_or_screenshots(self):
        self.assertEqual(audit.unsafe_asset_paths([
            "assets/original_disc.iso", "screenshots/image.PNG",
            "private/retail.XCI", "source/clean.c",
            "data/synthetic_map02.json"]),
            ["assets/original_disc.iso",
             "private/retail.XCI", "screenshots/image.PNG"])
        self.assertEqual(audit.unsafe_asset_paths(
            ["tests/test_map02_stack_audit.py"]), [])

    def git_fixture(self, root):
        run(root, "init", "-q")
        run(root, "config", "user.name", "MAP02 CI")
        run(root, "config", "user.email", "map02@example.invalid")
        (root / "shared.txt").write_text("base\n", encoding="utf-8")
        run(root, "add", "shared.txt")
        run(root, "commit", "-qm", "common base")
        return run(root, "rev-parse", "HEAD")

    def test_merge_tree_accepts_equivalent_divergent_commits_without_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = self.git_fixture(root)
            (root / "shared.txt").write_text("fixed\n", encoding="utf-8")
            run(root, "add", "shared.txt")
            run(root, "commit", "-qm", "first fix")
            older = run(root, "rev-parse", "HEAD")
            run(root, "checkout", "-q", "-b", "copied", common)
            (root / "shared.txt").write_text("fixed\n", encoding="utf-8")
            run(root, "add", "shared.txt")
            run(root, "commit", "-qm", "independent identical fix")
            newer = run(root, "rev-parse", "HEAD")
            head_before = run(root, "rev-parse", "HEAD")
            index_before = run(root, "status", "--porcelain")
            tree = audit.simulate_merge(root, older, newer)
            self.assertRegex(tree, r"^[0-9a-f]{40}$")
            self.assertEqual(run(root, "rev-parse", "HEAD"), head_before)
            self.assertEqual(run(root, "status", "--porcelain"),
                             index_before)

    def test_merge_tree_rejects_real_conflicts_without_modifying_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = self.git_fixture(root)
            (root / "shared.txt").write_text("parent edit\n",
                                             encoding="utf-8")
            run(root, "add", "shared.txt")
            run(root, "commit", "-qm", "parent")
            parent = run(root, "rev-parse", "HEAD")
            run(root, "checkout", "-q", "-b", "child", common)
            (root / "shared.txt").write_text("conflicting child edit\n",
                                             encoding="utf-8")
            run(root, "add", "shared.txt")
            run(root, "commit", "-qm", "child")
            child = run(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(audit.AuditError, "conflicts"):
                audit.simulate_merge(root, parent, child)
            self.assertEqual(run(root, "rev-parse", "HEAD"), child)
            self.assertEqual(run(root, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
