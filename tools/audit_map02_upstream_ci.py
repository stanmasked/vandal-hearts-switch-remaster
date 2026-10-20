#!/usr/bin/env python3
"""Read-only GitHub Actions provenance audit for 25 pinned upstream MAP02 PRs.

Only *completed successful* pull_request workflow runs on the exact pinned
commit count as evidence. Unrelated SHA, pending, failed, cancelled, or
unreadable runs cannot silently become an integration approval. The current
head PR is tested by its own CI jobs and is deliberately excluded to avoid
requiring a run to pass itself before that run finishes.
"""
from __future__ import annotations

import json
import re
from urllib import error, parse, request

from audit_map02_stack import AuditError

SHA = re.compile(r"^[0-9a-f]{40}$")


def fetch_commit_runs(repo: str, sha: str, token: str) -> list[dict]:
    if not token:
        raise AuditError("GitHub token required for upstream workflow evidence")
    if not SHA.fullmatch(sha):
        raise AuditError("invalid upstream SHA")
    params = parse.urlencode({
        "head_sha": sha, "event": "pull_request", "per_page": 100,
    })
    url = f"https://api.github.com/repos/{repo}/actions/runs?{params}"
    req = request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "map02-upstream-ci-provenance",
    })
    try:
        with request.urlopen(req, timeout=25) as response:
            if response.status != 200:
                raise AuditError(f"workflow API HTTP {response.status}")
            data = json.load(response)
    except (OSError, error.URLError, ValueError) as exc:
        raise AuditError("unable to retrieve upstream workflow evidence") from exc
    if not isinstance(data, dict):
        raise AuditError("malformed GitHub Actions response")
    total = data.get("total_count")
    runs = data.get("workflow_runs")
    if (type(total) is not int or total < 0 or total > 100
            or not isinstance(runs, list) or len(runs) != total):
        raise AuditError("incomplete or invalid workflow run listing")
    return runs


def validate_commit_runs(repo: str, number: int, sha: str,
                         runs: list[dict]) -> dict:
    if not SHA.fullmatch(sha) or not isinstance(runs, list):
        raise AuditError(f"PR #{number}: malformed workflow evidence")
    passed = []
    failures = []
    for run in runs:
        if not isinstance(run, dict):
            raise AuditError(f"PR #{number}: malformed run record")
        # Discard unrelated results: they never count toward the exact SHA.
        if run.get("head_sha") != sha or run.get("event") != "pull_request":
            continue
        if (not isinstance(run.get("id"), int)
                or not isinstance(run.get("html_url"), str)
                or not run["html_url"].startswith(
                    f"https://github.com/{repo}/actions/runs/")):
            raise AuditError(f"PR #{number}: missing workflow run provenance")
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") == "success":
            passed.append(run)
        elif run.get("conclusion") in ("failure", "timed_out", "action_required"):
            failures.append(run)
    if failures:
        raise AuditError(
            f"PR #{number}: failed completed CI on pinned commit")
    if not passed:
        raise AuditError(
            f"PR #{number}: no successful completed CI for pinned commit")
    selected = sorted(passed, key=lambda x: x["id"])[-1]
    return {
        "number": number, "head_sha": sha,
        "passed_runs": len(passed), "representative_id": selected["id"],
        "representative_url": selected["html_url"],
        "conclusion": "success",
    }


def audit_upstream_ci(repo: str, entries: list[dict], token: str) -> dict:
    if not entries or entries[-1].get("head_sha") != "HEAD":
        raise AuditError("current PR must be the terminal HEAD entry")
    verified = []
    for entry in entries[:-1]:
        sha = entry["head_sha"]
        number = entry["number"]
        runs = fetch_commit_runs(repo, sha, token)
        verified.append(validate_commit_runs(repo, number, sha, runs))
    if len(verified) != len(entries) - 1:
        raise AuditError("upstream workflow coverage incomplete")
    return {
        "verified": True,
        "upstream_pr_count": len(verified),
        "successful_exact_commit_workflows": len(verified),
        "source": "authenticated GitHub Actions REST, pull_request runs",
        "current_pr_self_run_excluded": True,
        "prs": verified,
    }
