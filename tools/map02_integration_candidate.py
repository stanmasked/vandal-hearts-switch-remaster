#!/usr/bin/env python3
"""Produce and verify a review-only 26-PR MAP02 integration candidate.

Requires the successful full-stack audit and the *same-run* 26-step
virtual-merge report. It inspects every unreferenced commit object and
records a content-addressed receipt. It neither moves Git refs nor merges
to main. Optional --bundle-receipt checks a separately downloaded,
self-contained NeXium evidence manifest for this exact source SHA/tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_map02_stack import AuditError, git
from audit_map02_full_stack import NUMBERS

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
KIND = "map02-review-only-virtual-integration"
VERSION = 1


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require_sha(value: object, label: str, width: int = 40) -> str:
    valid = SHA40 if width == 40 else SHA64
    if not isinstance(value, str) or not valid.fullmatch(value):
        raise AuditError(f"invalid {label} SHA-{width}")
    return value


def inspect_commit(repo: Path, commit_sha: str) -> tuple[str, list[str]]:
    require_sha(commit_sha, "unreferenced virtual commit")
    contents = git(repo, "cat-file", "-p", commit_sha).stdout
    if not contents or "\n\n" not in contents:
        raise AuditError("virtual integration Git commit object unavailable")
    headers = contents.split("\n\n", 1)[0].splitlines()
    trees = [line[5:] for line in headers if line.startswith("tree ")]
    parents = [line[7:] for line in headers if line.startswith("parent ")]
    if len(trees) != 1 or len(parents) != 2:
        raise AuditError("expected one tree and two parents in virtual commit")
    for field in [*trees, *parents]:
        require_sha(field, "virtual commit header")
    return trees[0], parents


def validate_reports(repo: Path, audit: dict, virtual: dict) -> dict:
    if not isinstance(audit, dict) or not isinstance(virtual, dict):
        raise AuditError("missing integration audit or virtual-merge report")
    if audit.get("result") != "PASS" or virtual.get("result") != "PASS":
        raise AuditError("unverified upstream integration evidence")
    if (audit.get("pr_count") != 26 or audit.get("pinned_upstream_prs") != 25
            or audit.get("checked_edges") != 25
            or audit.get("integration_merge_performed") is not False
            or virtual.get("stages") != 26
            or virtual.get("unchanged_trees") != 26
            or virtual.get("git_refs_updated") is not False
            or virtual.get("worktree_updated") is not False
            or virtual.get("real_merge_performed") is not False
            or virtual.get("virtual_object_only_commits") != 26
            or virtual.get("forbidden_intermediate_assets") != []):
        raise AuditError("incomplete or non-read-only integration audit")
    live, ci = audit.get("live_pr_metadata"), audit.get("upstream_ci_provenance")
    if (not isinstance(live, dict) or live.get("verified") is not True
            or live.get("open_draft_unmerged") != 26
            or live.get("head_and_base_sha_pinned") != 26
            or not isinstance(ci, dict) or ci.get("verified") is not True
            or ci.get("successful_exact_commit_workflows") != 25):
        raise AuditError("Draft PR status or upstream CI evidence incomplete")

    head = require_sha(audit.get("head_sha"), "checkout HEAD")
    main = require_sha(audit.get("main_sha"), "origin/main")
    if (virtual.get("last_source_sha") != head
            or virtual.get("root_sha") != main):
        raise AuditError("reports refer to different source commits")
    source_tree = require_sha(
        virtual.get("final_source_tree"), "source Git tree")
    if virtual.get("final_virtual_tree") != source_tree:
        raise AuditError("final virtual merge changed the source tree")
    if git(repo, "rev-parse", "HEAD").stdout.strip() != head:
        raise AuditError("candidate checkout HEAD changed")
    if git(repo, "rev-parse", "HEAD^{tree}").stdout.strip() != source_tree:
        raise AuditError("candidate source tree does not match checkout")
    if git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip() != main:
        raise AuditError("candidate origin/main changed")

    rows = virtual.get("steps")
    if not isinstance(rows, list) or len(rows) != 26:
        raise AuditError("virtual integration chain incomplete")
    if not isinstance(live.get("prs"), list) or len(live["prs"]) != 26:
        raise AuditError("live PR chain missing")
    previous = main
    reviewed = []
    count_changes = 0
    paths = set()
    for index, (row, live_pr, number) in enumerate(zip(rows, live["prs"], NUMBERS)):
        if not isinstance(row, dict) or not isinstance(live_pr, dict):
            raise AuditError("malformed source stage")
        if row.get("number") != number or live_pr.get("number") != number:
            raise AuditError("virtual order differs from pinned PR order")
        child = require_sha(row.get("source_sha"), f"PR #{number} source")
        tree = require_sha(row.get("source_tree"), f"PR #{number} tree")
        virtual_sha = require_sha(row.get("virtual_commit"),
                                  f"PR #{number} ephemeral commit")
        if (row.get("rehearsed_tree") != tree
                or row.get("identical") is not True
                or live_pr.get("head_sha") != child):
            raise AuditError(f"PR #{number}: rehearsal differs from live head")
        actual_tree, actual_parents = inspect_commit(repo, virtual_sha)
        if actual_tree != tree or actual_parents != [previous, child]:
            raise AuditError(f"PR #{number}: virtual object ancestry invalid")
        if git(repo, "rev-parse", f"{child}^{{tree}}").stdout.strip() != tree:
            raise AuditError(f"PR #{number}: pinned tree not available")
        changes = row.get("path_changes")
        if (not isinstance(changes, list)
                or row.get("changed_file_count") != len(changes)):
            raise AuditError(f"PR #{number}: missing intermediate change list")
        for change in changes:
            if (not isinstance(change, dict)
                    or change.get("status") not in ("A", "M", "D", "T")
                    or not isinstance(change.get("path"), str)
                    or not change["path"]):
                raise AuditError(f"PR #{number}: malformed changed path")
            paths.add(change["path"])
        count_changes += len(changes)
        reviewed.append({
            "number": number, "source_sha": child, "tree_sha": tree,
            "virtual_commit_sha": virtual_sha,
            "changed_files": len(changes),
        })
        previous = virtual_sha
    if (rows[-1]["source_sha"] != head or rows[-1]["source_tree"] != source_tree
            or virtual.get("intermediate_changes_checked") != count_changes
            or virtual.get("unique_changed_paths") != len(paths)):
        raise AuditError("final source or intermediate path count differs")
    return {
        "kind": KIND, "schema_version": VERSION,
        "review_only": True, "merged_into_main": False,
        "origin_main_sha": main, "source_head_sha": head,
        "source_tree_sha": source_tree,
        "isolated_candidate_commit_sha": previous,
        "isolated_candidate_tree_sha": source_tree,
        "pr_count": len(reviewed),
        "changed_file_events": count_changes,
        "changed_paths": len(paths),
        "steps": reviewed,
        "input_audit_sha256": digest(audit),
        "input_virtual_merge_sha256": digest(virtual),
        "separate_nro_and_nexium_evidence_required": True,
    }


def make_candidate(repo: Path, audit: dict, virtual: dict) -> dict:
    content = validate_reports(repo, audit, virtual)
    return {**content, "receipt_sha256": digest(content)}


def validate_candidate(repo: Path, audit: dict, virtual: dict,
                       candidate: dict) -> dict:
    expected = make_candidate(repo, audit, virtual)
    if (not isinstance(candidate, dict) or candidate != expected
            or not isinstance(candidate.get("receipt_sha256"), str)
            or candidate["receipt_sha256"] != expected["receipt_sha256"]):
        raise AuditError("candidate receipt mismatch or tampered content")
    return expected


def match_runtime_receipt(candidate: dict, bundle: dict) -> dict:
    """Bind separate NeXium+NRO artifact to exact candidate source tree."""
    if not isinstance(candidate, dict) or not isinstance(bundle, dict):
        raise AuditError("missing candidate or NeXium receipt")
    if (bundle.get("kind") != "map02-nexium-self-contained-evidence"
            or bundle.get("source_commit") != candidate.get("source_head_sha")
            or bundle.get("source_tree") != candidate.get("source_tree_sha")
            or bundle.get("png_count") != 24
            or bundle.get("file_count") != 35
            or not isinstance(bundle.get("root_sha256"), str)
            or not SHA64.fullmatch(bundle["root_sha256"])
            or not isinstance(bundle.get("nro_sha256"), str)
            or not SHA64.fullmatch(bundle["nro_sha256"])):
        raise AuditError("candidate is not bound to the same NRO/runtime source")
    return {
        "source_head_sha": candidate["source_head_sha"],
        "source_tree_sha": candidate["source_tree_sha"],
        "bundle_root_sha256": bundle["root_sha256"],
        "nro_sha256": bundle["nro_sha256"],
        "same_source": True,
    }


def load_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 3_000_000:
        raise AuditError(f"missing, linked or oversized JSON report: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AuditError(f"invalid JSON report: {path.name}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"expected JSON object: {path.name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--virtual", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--action", choices=("create", "verify"), required=True)
    parser.add_argument("--bundle-receipt", type=Path)
    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        audit = load_json(args.audit)
        virtual = load_json(args.virtual)
        if args.action == "create":
            if args.candidate.exists() or args.candidate.is_symlink():
                raise AuditError("refusing to overwrite existing integration candidate")
            result = make_candidate(repo, audit, virtual)
            args.candidate.parent.mkdir(parents=True, exist_ok=True)
            args.candidate.write_text(json.dumps(result, sort_keys=True,
                                                  indent=2) + "\n", encoding="utf-8")
        else:
            result = validate_candidate(
                repo, audit, virtual, load_json(args.candidate))
        if args.bundle_receipt is not None:
            binding = match_runtime_receipt(
                result, load_json(args.bundle_receipt))
            print("VH_MAP02_CANDIDATE_RUNTIME_BIND_PASS "
                  f"source={binding['source_head_sha']} "
                  f"nro_sha256={binding['nro_sha256']} "
                  f"bundle_root_sha256={binding['bundle_root_sha256']}", flush=True)
        print(
            "VH_MAP02_ISOLATED_CANDIDATE_PASS "
            f"action={args.action} prs={result['pr_count']} "
            f"main_merged=0 source={result['source_head_sha']} "
            f"tree={result['source_tree_sha']} "
            f"receipt_sha256={result['receipt_sha256']}", flush=True)
        return 0
    except (AuditError, OSError, KeyError, ValueError) as exc:
        print("VH_MAP02_ISOLATED_CANDIDATE_FAIL: " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
