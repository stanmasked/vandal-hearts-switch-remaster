"""Synthetic Git graphs for MAP02 26-PR object-only merge rehearsal."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_map02_stack import AuditError
from rehearse_map02_full_stack import rehearse


def git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


class RehearsalTests(unittest.TestCase):
    def start(self, root: Path):
        git(root, "init", "-q")
        git(root, "config", "user.name", "MAP02 Audit Fixture")
        git(root, "config", "user.email", "fixture@example.invalid")
        (root / "map.txt").write_text("original\n", encoding="utf-8")
        git(root, "add", "map.txt")
        git(root, "commit", "-qm", "baseline")
        return git(root, "rev-parse", "HEAD")

    def commit_file(self, root: Path, file: str, value: str, msg: str) -> str:
        (root / file).write_text(value, encoding="utf-8")
        git(root, "add", file)
        git(root, "commit", "-qm", msg)
        return git(root, "rev-parse", "HEAD")

    def test_linear_chain_produces_exact_final_tree_without_checkout(self):
        with tempfile.TemporaryDirectory(prefix="map02-virtual-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            first = self.commit_file(root, "map.txt", "arena\n", "first")
            second = self.commit_file(root, "medic.txt", "heal\n", "second")
            prev_head = git(root, "rev-parse", "HEAD")
            prev_ref = git(root, "symbolic-ref", "HEAD")
            report = rehearse(root, original, [
                {"number": 241, "sha": first},
                {"number": 243, "sha": second},
            ], second)
            self.assertEqual(report["stages"], 2)
            self.assertEqual(report["unchanged_trees"], 2)
            self.assertEqual(report["final_virtual_tree"], report["final_source_tree"])
            self.assertFalse(report["git_refs_updated"])
            self.assertFalse(report["worktree_updated"])
            self.assertEqual(git(root, "rev-parse", "HEAD"), prev_head)
            self.assertEqual(git(root, "symbolic-ref", "HEAD"), prev_ref)
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_github_actions_detached_head_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="map02-detached-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            newer = self.commit_file(root, "map.txt", "updated\\n", "newer")
            git(root, "checkout", "--detach", "-q", newer)
            self.assertNotEqual(
                subprocess.run(["git", "-C", str(root), "symbolic-ref",
                                "--quiet", "HEAD"], capture_output=True).returncode, 0)
            report = rehearse(root, original, [
                {"number": 241, "sha": newer},
            ], newer)
            self.assertEqual(report["unchanged_trees"], 1)
            self.assertEqual(git(root, "rev-parse", "HEAD"), newer)
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_copied_history_same_tree_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="map02-virtual-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            older = self.commit_file(root, "map.txt", "fixed\n", "older")
            git(root, "checkout", "-qb", "independent", original)
            copied = self.commit_file(root, "map.txt", "fixed\n", "copied")
            newer = self.commit_file(root, "bow.txt", "arrow\n", "newer")
            report = rehearse(root, original, [
                {"number": 262, "sha": older},
                {"number": 265, "sha": copied},
                {"number": 270, "sha": newer},
            ], newer)
            self.assertEqual(report["stages"], 3)
            self.assertTrue(all(row["identical"] for row in report["steps"]))

    def test_conflict_free_merger_that_revives_older_file_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="map02-virtual-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            older = self.commit_file(root, "orphan.txt", "old\n", "older")
            git(root, "checkout", "-qb", "unrelated", original)
            newer = self.commit_file(root, "medic.txt", "new\n", "newer")
            before = git(root, "rev-parse", "HEAD")
            with self.assertRaisesRegex(
                AuditError, "reintroduces or changes contents"
            ):
                rehearse(root, original, [
                    {"number": 262, "sha": older},
                    {"number": 265, "sha": newer},
                ], newer)
            self.assertEqual(git(root, "rev-parse", "HEAD"), before)
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_true_conflicting_merger_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="map02-virtual-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            older = self.commit_file(root, "map.txt", "older\n", "older")
            git(root, "checkout", "-qb", "conflicting", original)
            newer = self.commit_file(root, "map.txt", "different\n", "newer")
            with self.assertRaisesRegex(AuditError, "has conflicts"):
                rehearse(root, original, [
                    {"number": 262, "sha": older},
                    {"number": 265, "sha": newer},
                ], newer)
            self.assertEqual(git(root, "rev-parse", "HEAD"), newer)
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_wrong_final_head_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="map02-virtual-") as tmp:
            root = Path(tmp)
            original = self.start(root)
            newer = self.commit_file(root, "map.txt", "new\n", "new")
            with self.assertRaisesRegex(AuditError, "locked checkout HEAD"):
                rehearse(root, original, [{"number": 241, "sha": newer}],
                        original)


if __name__ == "__main__":
    unittest.main()
