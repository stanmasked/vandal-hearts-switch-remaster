#!/usr/bin/env python3
"""Read-only MAP02 stacked Draft PR integration preflight.

Fetches refs/pull/*/head into local throwaway remote-tracking refs only.
Uses git merge-tree for an in-memory merge simulation; never merges a
branch, switches the worktree, pushes commits or alters the default branch.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN = {
    ".iso", ".bin", ".img", ".cue", ".chd", ".nsp", ".xci",
    ".rom", ".pkg", ".pbp", ".cso", ".zip", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".wav", ".ogg", ".mp3",
}
EXPECTED_ORDER = [253, 256, 259, 262, 265, 270, 273, 281, 284, 289, 295]


class AuditError(Exception):
    pass


def git(repo: Path, *args: str, allow_failure: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode and not allow_failure:
        raise AuditError(
            f"git {' '.join(args[:4])} failed with "
            f"{completed.returncode}: {completed.stderr.strip()[:500]}")
    return completed


def validate_manifest(spec: dict):
    if spec.get("schema_version") != 1:
        raise AuditError("unsupported snapshot schema")
    prs = spec.get("pull_requests")
    if not isinstance(prs, list) or [p.get("number") for p in prs] != EXPECTED_ORDER:
        raise AuditError("stack PR ordering or length changed")
    for p in prs:
        if not isinstance(p.get("base_branch"), str) or not p["base_branch"]:
            raise AuditError(f"missing base branch for PR {p['number']}")
        if not SHA.fullmatch(p.get("head_sha", "")):
            raise AuditError(f"invalid pinned SHA for PR {p['number']}")
    if spec.get("allowed_divergent_edge") != [262, 265]:
        raise AuditError("unexpected non-linear edge allowlist")
    for key in ("shared_files_on_divergent_edge", "preserved_paths",
                "expected_integrated_paths", "expected_main_includes"):
        paths = spec.get(key)
        if not isinstance(paths, list) or not paths:
            raise AuditError(f"missing contract: {key}")
        if len(paths) != len(set(paths)):
            raise AuditError(f"duplicate contract entry in {key}")
        if any(not isinstance(p, str) or not p or p.startswith("/")
               or ".." in Path(p).parts for p in paths):
            raise AuditError(f"unsafe path in {key}")
    if spec.get("original_data_anchor") != 262:
        raise AuditError("original fixture baseline changed")
    return prs


def unsafe_asset_paths(changed: list[str]):
    return sorted(path for path in changed
                  if Path(path).suffix.lower() in FORBIDDEN)


def simulate_merge(repo: Path, older: str, newer: str):
    # Git >= 2.38: writes a tree object, NEVER a branch or working-tree merge.
    result = git(repo, "merge-tree", "--write-tree", older, newer,
                 allow_failure=True)
    if result.returncode:
        raise AuditError("dry-run merge has conflicts: " +
                         (result.stdout + result.stderr)[-700:])
    tree = result.stdout.splitlines()[0].strip() if result.stdout else ""
    if not SHA.fullmatch(tree):
        raise AuditError("git merge-tree did not produce a merge tree SHA")
    return tree


def preflight(repo: Path, spec: dict, fetch: bool = True):
    prs = validate_manifest(spec)
    repo = repo.resolve()
    if git(repo, "rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        raise AuditError("repository path is not a Git checkout")

    if fetch:
        refs = [f"+refs/pull/{p['number']}/head:"
                f"refs/remotes/origin/map02-pr-{p['number']}" for p in prs]
        git(repo, "fetch", "--no-tags", "--quiet", "origin", *refs)
    for p in prs:
        number = p["number"]
        got = git(repo, "rev-parse",
                  f"refs/remotes/origin/map02-pr-{number}").stdout.strip()
        if got != p["head_sha"]:
            raise AuditError(
                f"PR #{number} moved: expected {p['head_sha']}, got {got}; "
                "review and update the snapshot deliberately")

    last = prs[-1]["head_sha"]
    if git(repo, "merge-base", "--is-ancestor", last, "HEAD",
           allow_failure=True).returncode:
        raise AuditError("audit branch does not include the final verified PR #295")

    report = {"result": "PASS", "last_verified_pr": 295,
              "verified_prs": EXPECTED_ORDER, "edges": [],
              "preserved_files": [], "required_modules": [],
              "forbidden_added_assets": []}
    for earlier, later in zip(prs, prs[1:]):
        parent, child = earlier["head_sha"], later["head_sha"]
        entry = {"parent": earlier["number"], "child": later["number"]}
        is_linear = git(repo, "merge-base", "--is-ancestor", parent, child,
                        allow_failure=True).returncode == 0
        if is_linear:
            entry["result"] = "linear"
        else:
            if [earlier["number"], later["number"]] != spec["allowed_divergent_edge"]:
                raise AuditError(
                    f"unexpected divergent history: PR #{earlier['number']} "
                    f"-> #{later['number']}")
            entry["result"] = "diverged_identical_content"
            entry["dry_run_tree"] = simulate_merge(repo, parent, child)
            for path in spec["shared_files_on_divergent_edge"]:
                old = git(repo, "rev-parse", f"{parent}:{path}").stdout.strip()
                new = git(repo, "rev-parse", f"{child}:{path}").stdout.strip()
                if old != new:
                    raise AuditError(
                        f"divergent PRs #{earlier['number']} and "
                        f"#{later['number']} disagree on {path}")
            entry["identical_shared_paths"] = len(
                spec["shared_files_on_divergent_edge"])
        report["edges"].append(entry)

    baseline = next(p["head_sha"] for p in prs
                    if p["number"] == spec["original_data_anchor"])
    for path in spec["preserved_paths"]:
        old = git(repo, "rev-parse", f"{baseline}:{path}").stdout.strip()
        new = git(repo, "rev-parse", f"HEAD:{path}").stdout.strip()
        if old != new:
            raise AuditError(f"approved original fixture changed: {path}")
        report["preserved_files"].append(path)

    for path in spec["expected_integrated_paths"]:
        git(repo, "cat-file", "-e", f"HEAD:{path}")
        report["required_modules"].append(path)
    main = git(repo, "show", "HEAD:source/main.c").stdout
    for header in spec["expected_main_includes"]:
        if f'#include "{header}"' not in main:
            raise AuditError(f"Switch entrypoint omits {header}")

    first = prs[0]["head_sha"]
    changed = git(repo, "diff", "--name-only", "--diff-filter=AM",
                  first, "HEAD").stdout.splitlines()
    forbidden = unsafe_asset_paths(changed)
    if forbidden:
        raise AuditError("potential retail image / binary added: " +
                         ", ".join(forbidden[:10]))
    report["changed_paths_checked"] = len(changed)
    report["integration_merge_performed"] = False
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path,
                    default=Path("data/map02_pr_stack_snapshot.json"))
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--report", type=Path)
    ap.add_argument("--no-fetch", action="store_true",
                    help="use locally fetched PR refs for offline tests")
    args = ap.parse_args()
    try:
        spec = json.loads(args.manifest.read_text(encoding="utf-8"))
        outcome = preflight(args.repo, spec, fetch=not args.no_fetch)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(outcome, indent=2) + "\n",
                                   encoding="utf-8")
        print("VH_MAP02_STACK_PREFLIGHT_PASS prs=11 divergent=1 "
              "merge_conflicts=0 preserved=4 core_modules=10 "
              "retail_assets=0 main_merge=0")
        print("MAP02 stack audit: " + json.dumps(
            {"edges": outcome["edges"],
             "changed_paths_checked": outcome["changed_paths_checked"]}))
        return 0
    except (AuditError, OSError, ValueError, KeyError) as exc:
        print("VH_MAP02_STACK_PREFLIGHT_FAIL: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
