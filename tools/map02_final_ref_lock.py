#!/usr/bin/env python3
"""Last read-only MAP02 ref/CI lock before any human-reviewed integration.

Deliberately runs AFTER the virtual candidate is recorded. It re-queries
GitHub's current main ref, 26 open Draft PR heads/bases and the 25 pinned
upstream workflow results, compares them to the earlier Git audit, and
generates a source-bound receipt. No merge, push, checkout or Git ref writes.

This is a point-in-time preflight, NOT a GitHub merge authorization, a
cryptographic signature or an atomic lock on future remote changes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib import error, request
import sys

from audit_map02_stack import AuditError, git
from audit_map02_full_stack import validate_snapshot
from audit_map02_pr_metadata import fetch_live_prs, validate_live_prs
from audit_map02_upstream_ci import audit_upstream_ci
from map02_integration_candidate import (
    digest, load_json, require_sha, validate_candidate, match_runtime_receipt,
)

RECEIPT_KIND = "map02-point-in-time-final-ref-check"
VERSION = 1


def fetch_main_head(repo: str, token: str) -> str:
    if not token:
        raise AuditError("GitHub token required to reread main ref")
    url = f"https://api.github.com/repos/{repo}/git/ref/heads/main"
    req = request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "map02-last-check-no-write",
        "Cache-Control": "no-cache",
    })
    try:
        with request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                raise AuditError("could not reread origin/main")
            payload = json.load(response)
    except (OSError, error.URLError, ValueError) as exc:
        raise AuditError("unable to verify latest remote main ref") from exc
    obj = payload.get("object") if isinstance(payload, dict) else None
    if (payload.get("ref") != "refs/heads/main" or not isinstance(obj, dict)
            or obj.get("type") != "commit"):
        raise AuditError("invalid GitHub main ref response")
    return require_sha(obj.get("sha"), "GitHub remote main")


def validate_last_snapshot(
    repo: Path, spec: dict, core: dict, audit: dict, virtual: dict,
    candidate: dict, live: list[dict], main_head: str,
    upstream_ci: dict,
) -> dict:
    """Pure local evaluation of freshly obtained remote-state records."""
    repo = repo.resolve()
    expected = validate_candidate(repo, audit, virtual, candidate)
    entries = validate_snapshot(spec, core)
    main_head = require_sha(main_head, "fresh remote main")
    if expected["origin_main_sha"] != main_head:
        raise AuditError("main advanced after initial candidate audit")

    old = audit.get("live_pr_metadata")
    if not isinstance(old, dict) or old.get("verified") is not True:
        raise AuditError("original read-only PR snapshot missing")
    earlier = next(x["head_sha"] for x in entries if x["number"] == 262)
    later = next(x["head_sha"] for x in entries if x["number"] == 265)
    divergence_base = git(repo, "merge-base", earlier, later).stdout.strip()
    fresh = validate_live_prs(
        spec["repo"], entries, live, expected["source_head_sha"],
        main_head, divergence_base,
    )
    if fresh["prs"] != old.get("prs"):
        raise AuditError("GitHub PR states changed after original audit")

    previous_ci = audit.get("upstream_ci_provenance")
    if (not isinstance(previous_ci, dict)
            or previous_ci.get("verified") is not True):
        raise AuditError("original upstream Actions provenance missing")
    if (not isinstance(upstream_ci, dict)
            or upstream_ci.get("verified") is not True
            or upstream_ci.get("upstream_pr_count") != 25
            or upstream_ci.get("successful_exact_commit_workflows") != 25
            or upstream_ci.get("current_pr_self_run_excluded") is not True):
        raise AuditError("fresh upstream CI receipts incomplete")
    # The number of successful runs can grow; every originally selected
    # positive ID must still be among the current successful results.
    old_ci = previous_ci.get("prs")
    new_ci = upstream_ci.get("prs")
    if (not isinstance(old_ci, list) or not isinstance(new_ci, list)
            or len(old_ci) != 25 or len(new_ci) != 25):
        raise AuditError("upstream CI entries missing")
    for previous, now in zip(old_ci, new_ci):
        if (previous.get("number") != now.get("number")
                or previous.get("head_sha") != now.get("head_sha")
                or now.get("passed_runs", 0) < 1):
            raise AuditError("pinned upstream CI drift or mismatch")

    local_refs = [git(repo, "rev-parse", "HEAD").stdout.strip(),
                  git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip()]
    if local_refs != [expected["source_head_sha"], main_head]:
        raise AuditError("checkout HEAD or local main differs from candidate")

    seal = {
        "kind": RECEIPT_KIND, "schema_version": VERSION,
        "source_head_sha": expected["source_head_sha"],
        "source_tree_sha": expected["source_tree_sha"],
        "origin_main_sha": main_head,
        "candidate_receipt_sha256": expected["receipt_sha256"],
        "fresh_live_prs": 26, "fresh_upstream_ci": 25,
        "pr_states_unchanged": True, "upstream_ci_confirmed": True,
        "main_merged": False, "branch_mutations": False,
        "time_of_check_only": True,
        "integration_authorized": False,
    }
    return {**seal, "root_sha256": digest(seal)}


def make_last_seal(
    repo: Path, spec: dict, core: dict, audit: dict, virtual: dict,
    candidate: dict, token: str,
) -> dict:
    if not token:
        raise AuditError("missing GH_TOKEN for final remote check")
    entries = validate_snapshot(spec, core)
    main_head = fetch_main_head(spec["repo"], token)
    live = fetch_live_prs(spec["repo"], entries, token)
    ci = audit_upstream_ci(spec["repo"], entries, token)
    return validate_last_snapshot(repo, spec, core, audit, virtual,
                                  candidate, live, main_head, ci)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path,
                        default=Path("data/map02_full_stack_snapshot.json"))
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--virtual", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = load_json(args.manifest)
        core = load_json(Path(spec["existing_core_stack_snapshot"]))
        audit = load_json(args.audit)
        virtual = load_json(args.virtual)
        candidate = load_json(args.candidate)
        if args.report.exists() or args.report.is_symlink():
            raise AuditError("refusing to overwrite previous final ref check")
        seal = make_last_seal(args.repo, spec, core, audit, virtual, candidate,
                              os.environ.get("GH_TOKEN", ""))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(seal, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print("VH_MAP02_FINAL_REF_LOCK_PASS prs=26 upstream=25 "
              "main_unchanged=1 candidate_intact=1 merge=0 "
              f"source={seal['source_head_sha']} "
              f"root_sha256={seal['root_sha256']}", flush=True)
        return 0
    except (AuditError, OSError, KeyError, ValueError) as exc:
        print("VH_MAP02_FINAL_REF_LOCK_FAIL: " + str(exc),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
