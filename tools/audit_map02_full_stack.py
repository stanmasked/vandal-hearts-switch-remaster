#!/usr/bin/env python3
"""Read-only end-to-end audit of the 26 stacked MAP02 Draft pull requests.

This audits Git ancestry and reuses the existing 11-PR source/merge-tree
preflight. It does not change a branch, merge a PR, or read original PS1 assets.
The final pull request uses HEAD instead of pinning its own moving SHA.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from audit_map02_stack import (
    AuditError, git, preflight as core_preflight, unsafe_asset_paths,
)
from audit_map02_pr_metadata import (
    fetch_live_prs, validate_branch_contract, validate_live_prs,
)
from audit_map02_upstream_ci import audit_upstream_ci

NUMBERS = (
    241, 243, 247, 250, 251, 252, 253, 256, 259, 262, 265, 270,
    273, 281, 284, 289, 295, 302, 305, 314, 318, 322, 325, 333,
    347, 352,
)
SHA = re.compile(r"^[0-9a-f]{40}$")


def verify_divergent_tree(merged_tree: str, child_tree: str) -> None:
    """Fail closed if a dry-run merge resurrects any older-only content."""
    if not SHA.fullmatch(merged_tree) or not SHA.fullmatch(child_tree):
        raise AuditError("malformed #262/#265 reconciliation tree SHA")
    if merged_tree != child_tree:
        raise AuditError(
            "#262/#265 dry-run merge changes the #265 tree; "
            "manual reconciliation required before integration")


def validate_snapshot(spec: dict, core_spec: dict) -> list[dict]:
    if spec.get("schema_version") != 1:
        raise AuditError("unsupported full-stack schema")
    if spec.get("repo") != "stanmasked/vandal-hearts-switch-remaster":
        raise AuditError("wrong GitHub repository")
    if spec.get("expected_pr_count") != len(NUMBERS):
        raise AuditError("unexpected PR count")
    if spec.get("root_base") != "main":
        raise AuditError("full stack root must be main")
    if spec.get("permitted_divergent_edge") != [262, 265]:
        raise AuditError("unexpected divergent edge exception")
    entries = spec.get("pull_requests")
    if not isinstance(entries, list) or [
            x.get("number") for x in entries if isinstance(x, dict)
    ] != list(NUMBERS):
        raise AuditError("unexpected full-stack order or repeated PR number")
    for entry in entries[:-1]:
        if not SHA.fullmatch(entry.get("head_sha", "")):
            raise AuditError(f"bad upstream SHA at #{entry['number']}")
    if entries[-1].get("head_sha") != "HEAD":
        raise AuditError("last PR must use self-referential HEAD token")
    if spec.get("existing_core_stack_snapshot") != (
            "data/map02_pr_stack_snapshot.json"):
        raise AuditError("core audit manifest reference changed")
    pinned = {entry["number"]: entry["head_sha"] for entry in entries}
    for old in core_spec.get("pull_requests", []):
        if pinned.get(old.get("number")) != old.get("head_sha"):
            raise AuditError(
                f"existing protected core PR #{old.get('number')} pin changed")
    validate_branch_contract(entries)
    return entries


def preflight(repo: Path, spec: dict, core_spec: dict, fetch: bool = True):
    entries = validate_snapshot(spec, core_spec)
    repo = repo.resolve()
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if not SHA.fullmatch(head):
        raise AuditError("invalid current HEAD")
    if git(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        raise AuditError("not in a Git worktree")
    before = git(repo, "status", "--porcelain").stdout

    if fetch:
        refs = [
            f"+refs/pull/{entry['number']}/head:"
            f"refs/remotes/origin/map02-pr-{entry['number']}"
            for entry in entries
        ]
        git(repo, "fetch", "--no-tags", "--quiet", "origin", *refs)

    resolved = []
    for entry in entries:
        number = entry["number"]
        actual = git(repo, "rev-parse",
                     f"refs/remotes/origin/map02-pr-{number}").stdout.strip()
        expected = head if entry["head_sha"] == "HEAD" else entry["head_sha"]
        if actual != expected:
            raise AuditError(
                f"PR #{number} changed: expected {expected}, actual {actual}")
        resolved.append({"number": number, "sha": actual})

    main = git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()
    if git(repo, "merge-base", "--is-ancestor", main, resolved[0]["sha"],
           allow_failure=True).returncode:
        raise AuditError("first MAP02 PR is not based on current main")

    core = core_preflight(repo, core_spec, fetch=False)
    divergence = [
        e for e in core["edges"]
        if e["result"] == "diverged_identical_content"
    ]
    if len(divergence) != 1 or [
            divergence[0]["parent"], divergence[0]["child"]
    ] != [262, 265]:
        raise AuditError("historical #262/#265 divergence not validated")

    # The earlier #262 commits were copied independently onto #265's
    # ancestry. A conflict-free merge alone is NOT enough: require the
    # resulting Git tree to equal the unchanged downstream #265 tree.
    # This check never updates refs, index or the working tree.
    child_sha = next(e["sha"] for e in resolved if e["number"] == 265)
    child_tree = git(repo, "rev-parse", f"{child_sha}^{{tree}}").stdout.strip()
    merged_tree = divergence[0]["dry_run_tree"]
    verify_divergent_tree(merged_tree, child_tree)

    edges = []
    for previous, following in zip(resolved, resolved[1:]):
        parent, child = previous["number"], following["number"]
        linear = not git(repo, "merge-base", "--is-ancestor",
                         previous["sha"], following["sha"],
                         allow_failure=True).returncode
        if (parent, child) == (262, 265):
            if linear:
                raise AuditError("historical divergent edge unexpectedly moved")
            kind = "reviewed_core_divergence"
        elif not linear:
            raise AuditError(f"non-linear MAP02 PR edge #{parent} -> #{child}")
        else:
            kind = "linear"
        edges.append({"parent": parent, "child": child, "result": kind})

    changed = git(repo, "diff", "--name-only", "--diff-filter=AM",
                  main, head).stdout.splitlines()
    banned = unsafe_asset_paths(changed)
    if banned:
        raise AuditError("possibly copyrighted retail assets added: " +
                         ", ".join(banned[:10]))

    after = git(repo, "status", "--porcelain").stdout
    if before != after:
        raise AuditError("preflight changed worktree files")

    return {
        "result": "PASS",
        "head_sha": head,
        "main_sha": main,
        "pr_count": len(entries),
        "pinned_upstream_prs": len(entries) - 1,
        "checked_edges": len(edges),
        "edges": edges,
        "core_audit": core,
        "divergent_tree_reconciliation": {
            "edge": [262, 265],
            "simulated_merge_tree": merged_tree,
            "unchanged_downstream_tree": child_tree,
            "tree_identical": True,
            "history_rewritten": False,
        },
        "changed_paths_checked": len(changed),
        "forbidden_added_assets": banned,
        "integration_merge_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path,
                        default=Path("data/map02_full_stack_snapshot.json"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--verify-live-prs", action="store_true",
                        help="require current GitHub API Draft/head/base status")
    parser.add_argument("--verify-upstream-ci", action="store_true",
                        help="require exact-SHA successful Actions evidence for 25 upstream PRs")
    args = parser.parse_args()
    try:
        spec = json.loads(args.manifest.read_text(encoding="utf-8"))
        core = json.loads(Path(spec["existing_core_stack_snapshot"])
                          .read_text(encoding="utf-8"))
        report = preflight(args.repo, spec, core, fetch=not args.no_fetch)
        if args.verify_live_prs:
            entries = validate_snapshot(spec, core)
            earlier = next(e["head_sha"] for e in entries if e["number"] == 262)
            later = next(e["head_sha"] for e in entries if e["number"] == 265)
            divergence_base = git(args.repo.resolve(), "merge-base", earlier,
                                  later).stdout.strip()
            current = fetch_live_prs(spec["repo"], entries,
                                     os.environ.get("GH_TOKEN", ""))
            report["live_pr_metadata"] = validate_live_prs(
                spec["repo"], entries, current, report["head_sha"],
                report["main_sha"], divergence_base)
        if args.verify_upstream_ci:
            entries = validate_snapshot(spec, core)
            report["upstream_ci_provenance"] = audit_upstream_ci(
                spec["repo"], entries, os.environ.get("GH_TOKEN", ""))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n",
                                   encoding="utf-8")
        print("VH_MAP02_FULL_STACK_AUDIT_PASS prs=26 pinned=25 "
              "linear_edges=24 reviewed_divergent=1 "
              "retail_assets=0 main_merge=0", flush=True)
        if args.verify_live_prs:
            print("VH_MAP02_FULL_STACK_LIVE_PRS_PASS count=26 "
                  "draft=26 bases=26 head_shas=26", flush=True)
        if args.verify_upstream_ci:
            print("VH_MAP02_UPSTREAM_CI_PASS pinned=25 "
                  "success_exact_sha=25 self_excluded=1", flush=True)
        return 0
    except (AuditError, OSError, KeyError, ValueError) as exc:
        print("VH_MAP02_FULL_STACK_AUDIT_FAIL: " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
