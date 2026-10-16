#!/usr/bin/env python3
"""Stage 217: live HTTPS GitHub preflight for the exact Switch audio NRO.

Unlike the offline stage 216 comparison, this fetches official GitHub API
metadata directly and refuses builds not at the branch HEAD *at check time*.
This is not signed build attestation, physical execution, or audio acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import ssl
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

import analyze_switch_audio_log as audio
import verify_switch_audio_bundle as bundle
import verify_switch_audio_build_provenance as provenance

API_ORIGIN = f"https://api.github.com/repos/{provenance.REPOSITORY}"
REF_PATH = "/git/ref/heads/" + provenance.BRANCH
MAX_AGE_DAYS = 30
MAX_CLOCK_SKEW = timedelta(minutes=5)
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise provenance.ProvenanceError("unexpected redirect from GitHub REST endpoint")


def fetch_github_json(path: str) -> dict:
    """Fixed-origin, fixed-path GitHub REST requests; no caller-provided URLs."""
    if not (path == REF_PATH or
            re.fullmatch(r"/actions/runs/[1-9][0-9]*", path) or
            re.fullmatch(r"/actions/artifacts/[1-9][0-9]*", path)):
        raise provenance.ProvenanceError("disallowed GitHub API endpoint")
    request = Request(API_ORIGIN + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "Vandal-Hearts-Switch-audio-preflight",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()),
                          NoRedirects())
    try:
        with opener.open(request, timeout=15) as response:
            require_json = response.headers.get("Content-Type", "").lower()
            provenance.require("json" in require_json, "GitHub response not JSON")
            raw = response.read(provenance.MAX_JSON + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise provenance.ProvenanceError(f"GitHub HTTPS request failed: {exc}") from exc
    provenance.require(len(raw) <= provenance.MAX_JSON, "GitHub JSON response too large")
    try:
        result = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise provenance.ProvenanceError(f"invalid GitHub HTTPS JSON: {exc}") from exc
    provenance.require(isinstance(result, dict), "GitHub API response must be an object")
    return result


def parse_time(obj: dict, key: str) -> datetime:
    value = obj.get(key)
    provenance.require(isinstance(value, str) and len(value) <= 40,
                       f"missing GitHub timestamp: {key}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise provenance.ProvenanceError(f"invalid GitHub timestamp: {key}") from exc
    provenance.require(parsed.tzinfo is not None,
                       f"GitHub timestamp must include timezone: {key}")
    return parsed.astimezone(timezone.utc)


def evaluate(root: Path, archive: Path, run_id: int, artifact_id: int,
             *, api_fetch=fetch_github_json, now: datetime | None = None,
             max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Use injected API fetch for tests; production calls fixed HTTPS endpoints."""
    provenance.require(provenance.number(run_id) and provenance.number(artifact_id),
                       "run and artifact IDs must be positive integers")
    provenance.require(type(max_age_days) is int and 1 <= max_age_days <= 365,
                       "max age must be 1..365 days")
    clock = now or datetime.now(timezone.utc)
    provenance.require(clock.tzinfo is not None, "current time must have timezone")
    clock = clock.astimezone(timezone.utc)

    checked = bundle.inspect(root)
    manifest = bundle.read_manifest(root)
    provenance.require(checked["integrity"] == "VERIFIED",
                       "NRO/CSV evidence integrity failure")
    # Match the run and artifact via live REST; no local JSON snapshots can be forged.
    run = api_fetch(f"/actions/runs/{run_id}")
    artifact = api_fetch(f"/actions/artifacts/{artifact_id}")
    provenance.verify_identity(manifest, run, artifact)
    provenance.require(run["id"] == run_id and artifact["id"] == artifact_id,
                       "requested run/artifact ID differs from GitHub response")

    # Read HEAD *after* run/artifact to minimize stale-branch acceptance.
    ref = api_fetch(REF_PATH)
    provenance.require(ref.get("ref") == "refs/heads/" + provenance.BRANCH,
                       "GitHub branch reference mismatch")
    target = ref.get("object")
    provenance.require(isinstance(target, dict) and
                       target.get("type") == "commit",
                       "branch HEAD does not reference a commit")
    head_sha = target.get("sha")
    provenance.require(isinstance(head_sha, str) and SHA40.fullmatch(head_sha),
                       "invalid branch HEAD commit SHA")
    provenance.require(head_sha == manifest["git_sha"] == run["head_sha"],
                       "STALE_BUILD: NRO/run commit is not current branch HEAD")

    created = parse_time(run, "created_at")
    artifact_created = parse_time(artifact, "created_at")
    artifact_expiry = parse_time(artifact, "expires_at")
    provenance.require(created <= clock + MAX_CLOCK_SKEW and
                       artifact_created <= clock + MAX_CLOCK_SKEW,
                       "future GitHub timestamp")
    provenance.require(clock - created <= timedelta(days=max_age_days),
                       "STALE_BUILD: workflow run exceeds permitted age")
    provenance.require(artifact_created + MAX_CLOCK_SKEW >= created,
                       "artifact creation predates workflow")
    provenance.require(artifact_expiry > clock,
                       "GitHub artifact expired by timestamp")

    nro = manifest["nro"]
    provenance.require(isinstance(nro, dict) and
                       Path(nro["path"]).name == provenance.NRO_NAME,
                       "manifest does not point to the primary tactical NRO")
    matched = provenance.check_zip(archive, artifact, nro["sha256"], nro["size"])
    return {
        "schema": "vh-switch-audio-live-preflight/v1",
        "result": "MATCHED_CURRENT_HEAD_AT_CHECK_TIME",
        "build_provenance": "GITHUB_HTTPS_METADATA_AND_BYTE_MATCH_NOT_SIGNED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "repo": provenance.REPOSITORY,
        "branch": provenance.BRANCH,
        "head_sha_at_check_time": head_sha,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "run_created_at": created.isoformat(),
        "artifact_expires_at": artifact_expiry.isoformat(),
        "checked_at_utc": clock.isoformat(),
        "max_run_age_days": max_age_days,
        "verified_archive": matched,
        "limitations": (
            "HTTPS metadata and NRO archive matched at the moment checked. "
            "The branch can advance immediately afterward; rerun before copying "
            "to Switch. There is no signed reproducible-build attestation. "
            "Physical execution, sound quality and SD persistence are untested."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--artifact-zip", type=Path, required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--max-run-age-days", type=int, default=MAX_AGE_DAYS)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.bundle.resolve(), args.artifact_zip,
                          args.run_id, args.artifact_id,
                          max_age_days=args.max_run_age_days)
    except (provenance.ProvenanceError, bundle.BundleError, audio.LogFormatError,
            KeyError, TypeError, OSError) as exc:
        print(json.dumps({"result": "FAILED", "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
