#!/usr/bin/env python3
"""Verify two independent, exact-source MAP02 CI artifact sets without merging.

This digest is a review aid, not a digital signature or merge authorization.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib import parse, request, error

from map02_integration_candidate import digest, match_runtime_receipt
from audit_map02_stack import AuditError
from map02_candidate_receipt import ReceiptError
from map02_evidence_bundle import EvidenceError
from map02_evidence_bundle import verify as verify_runtime_bundle

SHA40 = re.compile(r"^[0-9a-f]{40}$")
WORKFLOW_PATH = ".github/workflows/map02-full-stack-integration.yml"
WORKFLOW_NAME = "MAP02 complete 26-PR read-only integration audit"
INTEGRATION_FILES = frozenset((
    "report.json", "result.log", "virtual-merge.json", "virtual-merge.log",
    "integration-candidate.json", "integration-candidate.log",
    "final-ref-check.json", "final-ref-check.log",
))


class CrossProofError(ValueError):
    pass


def sha40(value: object, name: str) -> str:
    if not isinstance(value, str) or not SHA40.fullmatch(value):
        raise CrossProofError(f"invalid {name}")
    return value


def unique_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 3_000_000:
        raise CrossProofError(f"missing or unsafe JSON: {path.name}")

    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CrossProofError("duplicate JSON evidence key")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError) as exc:
        raise CrossProofError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise CrossProofError(f"expected JSON object: {path.name}")
    return value


def latest_successful_run(runs: list[dict], sha: str, repo: str) -> int:
    sha40(sha, "source commit")
    if not isinstance(runs, list):
        raise CrossProofError("GitHub workflow run list missing")
    eligible = []
    for item in runs:
        if not isinstance(item, dict):
            raise CrossProofError("malformed GitHub workflow run")
        if (item.get("head_sha") != sha or item.get("path") != WORKFLOW_PATH
                or item.get("name") != WORKFLOW_NAME
                or item.get("event") != "pull_request"):
            continue
        run_id = item.get("id")
        if (type(run_id) is not int or run_id <= 0
                or item.get("html_url") !=
                f"https://github.com/{repo}/actions/runs/{run_id}"):
            raise CrossProofError("GitHub integration run provenance mismatch")
        eligible.append(item)
    if not eligible:
        raise CrossProofError("no exact-commit integration workflow")
    newest = max(eligible, key=lambda item: item["id"])
    if newest.get("status") != "completed" or newest.get("conclusion") != "success":
        raise CrossProofError("newest exact-commit integration workflow not successful")
    return newest["id"]


def discover(sha: str, repo: str, token: str) -> int:
    if not token:
        raise CrossProofError("GitHub token missing")
    params = parse.urlencode({"head_sha": sha, "event": "pull_request", "per_page": 100})
    url = (f"https://api.github.com/repos/{repo}/actions/workflows/"
           f"map02-full-stack-integration.yml/runs?{params}")
    req = request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "map02-cross-workflow-proof",
        "Cache-Control": "no-cache",
    })
    try:
        with request.urlopen(req, timeout=25) as response:
            if response.status != 200:
                raise CrossProofError("GitHub returned non-200")
            data = json.load(response)
    except (OSError, error.URLError, ValueError) as exc:
        raise CrossProofError("unable to query GitHub Actions") from exc
    if (not isinstance(data, dict)
            or type(data.get("total_count")) is not int
            or data["total_count"] > 100
            or not isinstance(data.get("workflow_runs"), list)
            or len(data["workflow_runs"]) != data["total_count"]):
        raise CrossProofError("incomplete GitHub workflow page")
    return latest_successful_run(data["workflow_runs"], sha, repo)


def verify_artifacts(integration: Path, runtime: Path, sha: str, tree: str,
                     repo: str, integration_run: int, runtime_run: int) -> dict:
    sha40(sha, "source commit")
    sha40(tree, "source tree")
    if (type(integration_run) is not int or type(runtime_run) is not int
            or integration_run <= 0 or runtime_run <= 0
            or integration_run == runtime_run):
        raise CrossProofError("invalid independent workflow run IDs")
    if integration.is_symlink() or not integration.is_dir():
        raise CrossProofError("integration artifact directory absent")
    if {p.name for p in integration.iterdir()} != INTEGRATION_FILES:
        raise CrossProofError("incomplete or unexpected integration evidence")
    if any(p.is_symlink() or not p.is_file() for p in integration.iterdir()):
        raise CrossProofError("unsafe integration evidence entry")
    audit = unique_json(integration / "report.json")
    virtual = unique_json(integration / "virtual-merge.json")
    candidate = unique_json(integration / "integration-candidate.json")
    seal = unique_json(integration / "final-ref-check.json")
    # This independent call verifies 35 exact files, NRO, 24 PNG, 72 hashes,
    # RGB regions, different PIDs and genuine per-boot + offline log evidence.
    bundle = verify_runtime_bundle(runtime, sha, tree)
    if match_runtime_receipt(candidate, bundle).get("same_source") is not True:
        raise CrossProofError("candidate and runtime source differ")
    if (audit.get("result") != "PASS" or audit.get("head_sha") != sha
            or audit.get("main_sha") != candidate.get("origin_main_sha")
            or audit.get("pr_count") != 26 or audit.get("pinned_upstream_prs") != 25
            or audit.get("integration_merge_performed") is not False):
        raise CrossProofError("integration audit identity or status mismatch")
    live, upstream = audit.get("live_pr_metadata"), audit.get("upstream_ci_provenance")
    if (not isinstance(live, dict) or live.get("open_draft_unmerged") != 26
            or not isinstance(upstream, dict)
            or upstream.get("successful_exact_commit_workflows") != 25):
        raise CrossProofError("live Draft/CI evidence incomplete")
    if (virtual.get("result") != "PASS" or virtual.get("stages") != 26
            or virtual.get("unchanged_trees") != 26
            or virtual.get("last_source_sha") != sha
            or virtual.get("final_source_tree") != tree
            or virtual.get("final_virtual_tree") != tree
            or virtual.get("real_merge_performed") is not False
            or virtual.get("git_refs_updated") is not False):
        raise CrossProofError("virtual 26-PR integration not proved")
    if (candidate.get("kind") != "map02-review-only-virtual-integration"
            or candidate.get("schema_version") != 1
            or candidate.get("source_head_sha") != sha
            or candidate.get("source_tree_sha") != tree
            or candidate.get("isolated_candidate_tree_sha") != tree
            or candidate.get("pr_count") != 26
            or candidate.get("merged_into_main") is not False
            or candidate.get("review_only") is not True
            or candidate.get("input_audit_sha256") != digest(audit)
            or candidate.get("input_virtual_merge_sha256") != digest(virtual)):
        raise CrossProofError("candidate not derived from audited virtual tree")
    basis = {k: v for k, v in candidate.items() if k != "receipt_sha256"}
    if candidate.get("receipt_sha256") != digest(basis):
        raise CrossProofError("candidate SHA-256 receipt mismatch")
    if (seal.get("kind") != "map02-point-in-time-final-ref-check"
            or seal.get("source_head_sha") != sha
            or seal.get("source_tree_sha") != tree
            or seal.get("origin_main_sha") != candidate.get("origin_main_sha")
            or seal.get("candidate_receipt_sha256") != candidate["receipt_sha256"]
            or seal.get("fresh_live_prs") != 26
            or seal.get("fresh_upstream_ci") != 25
            or seal.get("pr_states_unchanged") is not True
            or seal.get("time_of_check_only") is not True
            or seal.get("main_merged") is not False
            or seal.get("branch_mutations") is not False
            or seal.get("integration_authorized") is not False):
        raise CrossProofError("incompatible final ref-check receipt")
    seal_basis = {k: v for k, v in seal.items() if k != "root_sha256"}
    if seal.get("root_sha256") != digest(seal_basis):
        raise CrossProofError("final ref-check digest mismatch")
    a, b = candidate.get("steps"), virtual.get("steps")
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != 26 or len(b) != 26:
        raise CrossProofError("virtual integration steps missing")
    for claimed, original in zip(a, b):
        if (claimed.get("number") != original.get("number")
                or claimed.get("source_sha") != original.get("source_sha")
                or claimed.get("tree_sha") != original.get("source_tree")
                or claimed.get("virtual_commit_sha") != original.get("virtual_commit")
                or claimed.get("changed_files") != original.get("changed_file_count")):
            raise CrossProofError("virtual PR tree sequence changed")
    result = {
        "kind": "map02-verified-independent-ci-proof",
        "schema_version": 1,
        "repository": repo,
        "source_commit": sha, "source_tree": tree,
        "integration_workflow_run_id": integration_run,
        "runtime_workflow_run_id": runtime_run,
        "integration_artifact": "map02-full-stack-no-merge-audit",
        "runtime_artifact": "nexium-map02-cold-restart-runtime",
        "integration_candidate_sha256": candidate["receipt_sha256"],
        "integration_final_ref_sha256": seal["root_sha256"],
        "nexium_bundle_sha256": bundle["root_sha256"],
        "nro_sha256": bundle["nro_sha256"],
        "verified_files": bundle["file_count"], "verified_png": bundle["png_count"],
        "pr_count": 26, "upstream_successful_prs": 25,
        "source_and_tree_match": True,
        "real_merge_performed": False,
        "physical_switch_verified": False,
    }
    return {**result, "root_sha256": digest(result)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    locate = subs.add_parser("discover")
    locate.add_argument("--repo", required=True)
    locate.add_argument("--sha", required=True)
    locate.add_argument("--github-output", type=Path)
    proof = subs.add_parser("verify")
    proof.add_argument("--repo", required=True)
    proof.add_argument("--sha", required=True)
    proof.add_argument("--tree", required=True)
    proof.add_argument("--integration-dir", type=Path, required=True)
    proof.add_argument("--runtime-dir", type=Path, required=True)
    proof.add_argument("--integration-run", required=True, type=int)
    proof.add_argument("--runtime-run", required=True, type=int)
    proof.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "discover":
            run = discover(args.sha, args.repo, os.environ.get("GH_TOKEN", ""))
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as handle:
                    handle.write(f"integration_run_id={run}\n")
            print(f"VH_MAP02_INTEGRATION_RUN_FOUND run={run} source={args.sha}")
        else:
            if args.report.exists() or args.report.is_symlink():
                raise CrossProofError("refusing to overwrite existing proof")
            data = verify_artifacts(args.integration_dir, args.runtime_dir,
                                    args.sha, args.tree, args.repo,
                                    args.integration_run, args.runtime_run)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n",
                                   encoding="utf-8")
            print(f"VH_MAP02_CROSS_WORKFLOW_PASS prs=26 upstream=25 png=24 "
                  f"source={args.sha} root_sha256={data['root_sha256']} "
                  "main_merge=0")
        return 0
    except (CrossProofError, AuditError, ReceiptError, EvidenceError, OSError, KeyError, ValueError) as exc:
        print(f"VH_MAP02_CROSS_WORKFLOW_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
