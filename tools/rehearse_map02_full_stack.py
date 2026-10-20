#!/usr/bin/env python3
"""Rehearse all 26 MAP02 merges using Git objects only, NEVER moving refs.

The rehearsal starts at pinned origin/main and simulates *merge commits*,
in PR order, with git merge-tree --write-tree followed by git commit-tree.
Every resulting tree MUST equal that step's already-reviewed PR head tree;
a conflict-free merge that restores obsolete contents fails closed.

commit-tree writes unreachable temporary objects to the local runner Git
object store. It never checks out or modifies branches, tags, the index, the
working tree, GitHub PRs, or origin/main.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from audit_map02_stack import AuditError, git, unsafe_asset_paths
from audit_map02_full_stack import validate_snapshot

SHA = re.compile(r"^[0-9a-f]{40}$")


def _tree(repo: Path, commit: str) -> str:
    if not SHA.fullmatch(commit):
        raise AuditError("virtual merge input is not a full commit SHA")
    tree = git(repo, "rev-parse", f"{commit}^{{tree}}").stdout.strip()
    if not SHA.fullmatch(tree):
        raise AuditError("unable to resolve virtual merge tree")
    return tree


def _object_only_commit(repo: Path, tree: str, parent: str,
                        child: str, number: int) -> str:
    args = [
        "git", "-C", str(repo), "-c", "user.name=MAP02 Audit",
        "-c", "user.email=map02-audit@example.invalid", "commit-tree",
        tree, "-p", parent, "-p", child,
        "-m", f"MAP02 ephemeral virtual merge PR #{number}",
    ]
    env = dict(os.environ, GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000",
               GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000")
    r = subprocess.run(args, capture_output=True, text=True, env=env,
                       check=False)
    if r.returncode:
        raise AuditError(f"virtual commit-tree failed at PR #{number}: "
                         + r.stderr.strip()[:450])
    sha = r.stdout.strip()
    if not SHA.fullmatch(sha):
        raise AuditError(f"invalid virtual commit SHA at PR #{number}")
    return sha


def _head_reference(repo: Path) -> tuple[int, str]:
    """Capture symbolic branch or detached HEAD without assuming either."""
    result = git(repo, "symbolic-ref", "--quiet", "HEAD", allow_failure=True)
    if result.returncode not in (0, 1):
        raise AuditError("unable to inspect current HEAD reference")
    return (result.returncode, result.stdout.strip())


def inspect_step_changes(repo: Path, before_tree: str,
                         after_tree: str, number: int) -> list[dict]:
    """Account for *every* intermediate path, even if later deleted.

    A final-tree-only scan misses transient retail data. Read Git's raw -z
    name/status stream so unusual filenames cannot masquerade as a status.
    """
    if not SHA.fullmatch(before_tree) or not SHA.fullmatch(after_tree):
        raise AuditError(f"PR #{number}: invalid tree in change inventory")
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-status",
         "--no-renames", "-z", before_tree, after_tree],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise AuditError(f"PR #{number}: cannot enumerate staged tree changes")
    tokens = result.stdout.split(b"\0")
    if not tokens or tokens[-1] != b"":
        raise AuditError(f"PR #{number}: truncated Git change inventory")
    tokens.pop()
    if len(tokens) % 2:
        raise AuditError(f"PR #{number}: malformed Git change inventory")
    inventory = []
    for i in range(0, len(tokens), 2):
        try:
            status = tokens[i].decode("ascii")
            filename = tokens[i + 1].decode("utf-8")
        except UnicodeError as exc:
            raise AuditError(f"PR #{number}: unsupported path encoding") from exc
        if status not in ("A", "M", "D", "T") or not filename:
            raise AuditError(f"PR #{number}: unsupported file change status")
        if filename.startswith("/") or any(
                part in ("", ".", "..") for part in filename.split("/")):
            raise AuditError(f"PR #{number}: unsafe changed path")
        inventory.append({"status": status, "path": filename})
    dangerous = unsafe_asset_paths([
        x["path"] for x in inventory if x["status"] in ("A", "M", "T")
    ])
    if dangerous:
        raise AuditError(
            f"PR #{number}: forbidden intermediate retail/binary assets: "
            + ", ".join(dangerous[:10]))
    return inventory


def rehearse(repo: Path, main_sha: str, pinned_prs: list[dict],
             expected_last_sha: str | None = None) -> dict:
    """Simulate one isolated merge object per stage and verify ALL trees."""
    repo = repo.resolve()
    if not SHA.fullmatch(main_sha) or not isinstance(pinned_prs, list) or not pinned_prs:
        raise AuditError("invalid virtual merge input or empty PR list")
    before_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    before_branch = _head_reference(repo)
    before_status = git(repo, "status", "--porcelain").stdout
    parent = main_sha
    items = []
    all_changes = 0
    changed_paths = set()
    for entry in pinned_prs:
        number = entry["number"]
        child = entry["sha"]
        target_tree = _tree(repo, child)
        result = git(repo, "merge-tree", "--write-tree", parent, child,
                     allow_failure=True)
        if result.returncode:
            detail = (result.stdout + result.stderr)[-650:]
            raise AuditError(
                f"PR #{number}: virtual integration merge has conflicts: {detail}")
        merged_tree = result.stdout.splitlines()[0].strip() if result.stdout else ""
        if not SHA.fullmatch(merged_tree):
            raise AuditError(f"PR #{number}: merge-tree yielded no valid tree")
        if merged_tree != target_tree:
            raise AuditError(
                f"PR #{number}: virtual integration reintroduces or changes "
                "contents absent from the reviewed downstream head")
        path_changes = inspect_step_changes(repo, _tree(repo, parent),
                                             target_tree, number)
        all_changes += len(path_changes)
        changed_paths.update(x["path"] for x in path_changes)
        virtual_sha = _object_only_commit(repo, merged_tree, parent, child,
                                           number)
        if _tree(repo, virtual_sha) != target_tree:
            raise AuditError(f"PR #{number}: virtual commit tree changed")
        items.append({
            "number": number, "source_sha": child,
            "source_tree": target_tree, "rehearsed_tree": merged_tree,
            "virtual_commit": virtual_sha, "identical": True,
            "changed_file_count": len(path_changes),
            "path_changes": path_changes,
        })
        parent = virtual_sha

    final_sha = pinned_prs[-1]["sha"]
    if expected_last_sha is not None and final_sha != expected_last_sha:
        raise AuditError("final PR SHA differs from locked checkout HEAD")
    if _tree(repo, parent) != _tree(repo, final_sha):
        raise AuditError("full virtual integration tree differs from final HEAD")
    if (git(repo, "rev-parse", "HEAD").stdout.strip() != before_head
            or _head_reference(repo) != before_branch
            or git(repo, "status", "--porcelain").stdout != before_status):
        raise AuditError("virtual merge unexpectedly changed worktree or ref")
    return {
        "result": "PASS",
        "root_sha": main_sha,
        "last_source_sha": final_sha,
        "final_source_tree": _tree(repo, final_sha),
        "final_virtual_tree": _tree(repo, parent),
        "stages": len(items),
        "unchanged_trees": len(items),
        "virtual_object_only_commits": len(items),
        "intermediate_changes_checked": all_changes,
        "unique_changed_paths": len(changed_paths),
        "forbidden_intermediate_assets": [],
        "git_refs_updated": False, "worktree_updated": False,
        "real_merge_performed": False,
        "steps": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path,
                        default=Path("data/map02_full_stack_snapshot.json"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.manifest.read_text(encoding="utf-8"))
        core = json.loads(Path(spec["existing_core_stack_snapshot"])
                          .read_text(encoding="utf-8"))
        entries = validate_snapshot(spec, core)
        repo = args.repo.resolve()
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        main_ref = git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()
        pinned_prs = []
        for entry in entries:
            number = entry["number"]
            sha = head if entry["head_sha"] == "HEAD" else entry["head_sha"]
            actual = git(repo, "rev-parse",
                         f"refs/remotes/origin/map02-pr-{number}").stdout.strip()
            if actual != sha:
                raise AuditError(f"PR #{number}: stale PR snapshot")
            pinned_prs.append({"number": number, "sha": sha})
        report = rehearse(repo, main_ref, pinned_prs, head)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n",
                                   encoding="utf-8")
        if report["stages"] != 26:
            raise AuditError("unexpected number of rehearsal stages")
        print("VH_MAP02_VIRTUAL_MERGE_PASS stages=26 unchanged_trees=26 "
              "git_refs_updated=0 worktree_updated=0", flush=True)
        return 0
    except (AuditError, OSError, ValueError, KeyError) as exc:
        print("VH_MAP02_VIRTUAL_MERGE_FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
