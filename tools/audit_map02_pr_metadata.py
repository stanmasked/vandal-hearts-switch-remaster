#!/usr/bin/env python3
"""Read-only, fail-closed GitHub PR metadata gate for the pinned MAP02 stack.

A Git ancestry graph does not prove the pull requests remain open Drafts
targeting the expected branches. Query the authenticated GitHub REST API for
each PR and compare live metadata to the committed manifest. No write API.
"""
from __future__ import annotations

import json
import os
import re
from urllib import error, request

from audit_map02_stack import AuditError

SHA = re.compile(r"^[0-9a-f]{40}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")


def validate_branch_contract(entries: list[dict]) -> None:
    for idx, entry in enumerate(entries):
        number = entry["number"]
        head = entry.get("head_branch")
        base = entry.get("base_branch")
        if not isinstance(head, str) or not BRANCH.fullmatch(head):
            raise AuditError(f"PR #{number}: missing/invalid pinned head branch")
        if not isinstance(base, str) or not BRANCH.fullmatch(base):
            raise AuditError(f"PR #{number}: missing/invalid pinned base branch")
        if any(x in ("", ".", "..") for x in head.split("/")):
            raise AuditError(f"PR #{number}: unsafe pinned head branch")
        expected = "main" if idx == 0 else entries[idx - 1]["head_branch"]
        if base != expected:
            raise AuditError(
                f"PR #{number}: base contract changed ({base} != {expected})")


def fetch_live_prs(repo: str, entries: list[dict], token: str) -> list[dict]:
    if not token:
        raise AuditError("GitHub token required for live PR status gate")
    result = []
    for entry in entries:
        number = entry["number"]
        url = f"https://api.github.com/repos/{repo}/pulls/{number}"
        req = request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "map02-readonly-pr-audit",
        })
        try:
            with request.urlopen(req, timeout=20) as response:
                if response.status != 200:
                    raise AuditError(
                        f"PR #{number}: GitHub API HTTP {response.status}")
                record = json.load(response)
        except (OSError, error.URLError, ValueError) as exc:
            raise AuditError(
                f"PR #{number}: unable to read current GitHub metadata: "
                f"{type(exc).__name__}") from exc
        if not isinstance(record, dict):
            raise AuditError(f"PR #{number}: malformed GitHub API response")
        result.append(record)
    return result


def validate_live_prs(
    repo: str, entries: list[dict], live: list[dict], head_sha: str,
    main_sha: str, divergence_base_sha: str,
) -> dict:
    validate_branch_contract(entries)
    if not all(SHA.fullmatch(x) for x in
               (head_sha, main_sha, divergence_base_sha)):
        raise AuditError("invalid Git revision in live PR status audit")
    if len(entries) != len(live):
        raise AuditError("live GitHub PR result count mismatch")
    records = []
    for idx, (expected, actual) in enumerate(zip(entries, live)):
        number = expected["number"]
        desired_head = head_sha if expected["head_sha"] == "HEAD" else expected["head_sha"]
        desired_base_sha = (
            main_sha if idx == 0
            else divergence_base_sha if number == 265
            else entries[idx - 1]["head_sha"]
        )
        if not isinstance(actual, dict) or actual.get("number") != number:
            raise AuditError(f"PR #{number}: response belongs to another PR")
        if (actual.get("state") != "open" or
                actual.get("draft") is not True or
                actual.get("merged_at") is not None):
            raise AuditError(f"PR #{number}: no longer open and unmerged Draft")
        h, b = actual.get("head"), actual.get("base")
        if not isinstance(h, dict) or not isinstance(b, dict):
            raise AuditError(f"PR #{number}: missing head or base metadata")
        if (h.get("ref") != expected["head_branch"]
                or b.get("ref") != expected["base_branch"]):
            raise AuditError(f"PR #{number}: head/base branch retargeted")
        if h.get("sha") != desired_head:
            raise AuditError(f"PR #{number}: head SHA changed")
        if b.get("sha") != desired_base_sha:
            raise AuditError(f"PR #{number}: base SHA changed")
        if (not isinstance(h.get("repo"), dict)
                or h["repo"].get("full_name") != repo
                or not isinstance(b.get("repo"), dict)
                or b["repo"].get("full_name") != repo):
            raise AuditError(f"PR #{number}: head/base moved to another repository")
        records.append({
            "number": number, "state": "open", "draft": True,
            "head_branch": h["ref"], "base_branch": b["ref"],
            "head_sha": h["sha"], "base_sha": b["sha"],
        })
    return {
        "verified": True,
        "pr_count": len(records),
        "open_draft_unmerged": len(records),
        "head_and_base_sha_pinned": len(records),
        "source": "authenticated GitHub REST pull requests (read-only)",
        "prs": records,
    }
