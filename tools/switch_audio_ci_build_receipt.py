#!/usr/bin/env python3
"""Stage 229: produce and verify an unsigned build receipt beside a Switch NRO.

Created only after a successful NRO build. This is a GitHub Actions run
fingerprint, NOT a cryptographic attestation, physical Switch execution, or
proof that an arbitrary local JSON originated in CI.

The verifier checks both file bytes and strict metadata, with an optional
expected Git SHA and run identity supplied independently.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-ci-build-receipt/v1"
HARDWARE_STATUS = bundle.HARDWARE_STATUS
NRO_NAME = "vandal-hearts-prototype.nro"
RECEIPT_NAME = "vandal-hearts-prototype.build.json"
WORKFLOW_PATH = ".github/workflows/switch-toolchain.yml"
WORKFLOW_NAME = "Switch toolchain readiness"
REPOSITORY = "stanmasked/vandal-hearts-switch-remaster"
MAX_RECEIPT = 16 * 1024
MAX_NRO_BYTES = 128 * 1024 * 1024
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,190}\Z")
FIELDS = {
    "schema", "hardware_status", "provenance", "repository",
    "workflow_name", "workflow_path", "git_sha", "head_branch",
    "run_id", "run_attempt", "nro",
}
NRO_FIELDS = {"name", "size", "sha256"}


class ReceiptError(ValueError):
    """Invalid build metadata, file identity or read-only boundary."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ReceiptError(why)


def positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def safe_nro(path: Path) -> tuple[int, str]:
    require(path.name == NRO_NAME and path.is_file() and not path.is_symlink(),
            "source must be a non-symlink primary prototype NRO")
    size, hash_value = bundle.digest_file(path)
    require(0 < size <= MAX_NRO_BYTES, "NRO file has invalid size")
    bundle.validate_nro_structure(path)
    return size, hash_value


def json_bytes(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def check_record(value: object) -> dict:
    require(isinstance(value, dict) and set(value) == FIELDS,
            "invalid build receipt fields")
    record = value
    require(record["schema"] == SCHEMA and
            record["hardware_status"] == HARDWARE_STATUS and
            record["provenance"] == "CI_METADATA_SELF_REPORTED_NOT_SIGNED" and
            record["repository"] == REPOSITORY and
            record["workflow_name"] == WORKFLOW_NAME and
            record["workflow_path"] == WORKFLOW_PATH,
            "unexpected build receipt origin or claimed hardware PASS")
    sha = record["git_sha"]
    require(isinstance(sha, str) and SHA40.fullmatch(sha) is not None,
            "invalid receipt Git commit")
    branch = record["head_branch"]
    require(isinstance(branch, str) and
            BRANCH.fullmatch(branch) is not None and
            not branch.startswith("/") and
            ".." not in branch and
            not branch.endswith("/"),
            "invalid GitHub branch")
    require(positive_int(record["run_id"]) and
            positive_int(record["run_attempt"]),
            "invalid GitHub Actions run ID or attempt")
    nro = record["nro"]
    require(isinstance(nro, dict) and set(nro) == NRO_FIELDS and
            nro["name"] == NRO_NAME and
            type(nro["size"]) is int and 0 < nro["size"] <= MAX_NRO_BYTES and
            isinstance(nro["sha256"], str) and SHA256.fullmatch(nro["sha256"]) is not None,
            "invalid NRO fingerprint")
    return record


def issue(nro: Path, git_sha: str, branch: str, run_id: int,
          run_attempt: int, output: Path) -> dict:
    size, fingerprint = safe_nro(nro)
    record = check_record({
        "schema": SCHEMA,
        "hardware_status": HARDWARE_STATUS,
        "provenance": "CI_METADATA_SELF_REPORTED_NOT_SIGNED",
        "repository": REPOSITORY,
        "workflow_name": WORKFLOW_NAME,
        "workflow_path": WORKFLOW_PATH,
        "git_sha": git_sha,
        "head_branch": branch,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "nro": {"name": NRO_NAME, "size": size, "sha256": fingerprint},
    })
    require(output.name == RECEIPT_NAME and output.parent.is_dir() and
            not output.exists() and not output.is_symlink(),
            "receipt must use the expected unused file path")
    require(output.parent.resolve() == nro.parent.resolve(),
            "receipt must be written beside built NRO")
    blob = json_bytes(record)
    require(len(blob) <= MAX_RECEIPT, "CI build receipt too large")
    with output.open("xb") as stream:
        stream.write(blob)
    return record


def parse(raw: bytes) -> dict:
    require(len(raw) <= MAX_RECEIPT, "receipt exceeds 16 KiB limit")
    try:
        value = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"invalid build receipt JSON: {exc}") from exc
    return check_record(value)


def verify(nro: Path, receipt: Path, *,
           expected_git_sha: str | None = None,
           expected_run_id: int | None = None,
           expected_branch: str | None = None) -> dict:
    size, digest = safe_nro(nro)
    require(receipt.name == RECEIPT_NAME and receipt.is_file() and
            not receipt.is_symlink(), "missing or symlinked CI build receipt")
    raw = receipt.read_bytes()
    record = parse(raw)
    require(raw == json_bytes(record), "noncanonical CI build receipt bytes")
    require(record["nro"]["size"] == size and
            record["nro"]["sha256"] == digest,
            "BUILD_RECEIPT_NRO_MISMATCH: binary differs from recorded build")
    if expected_git_sha is not None:
        require(record["git_sha"] == expected_git_sha,
                "BUILD_RECEIPT_COMMIT_MISMATCH")
    if expected_run_id is not None:
        require(positive_int(expected_run_id) and
                record["run_id"] == expected_run_id,
                "BUILD_RECEIPT_RUN_MISMATCH")
    if expected_branch is not None:
        require(record["head_branch"] == expected_branch,
                "BUILD_RECEIPT_BRANCH_MISMATCH")
    return {
        "result": "CI_RECEIPT_AND_NRO_BYTES_MATCH",
        "hardware_status": HARDWARE_STATUS,
        "git_sha_self_reported": record["git_sha"],
        "head_branch_self_reported": record["head_branch"],
        "run_id_self_reported": record["run_id"],
        "run_attempt_self_reported": record["run_attempt"],
        "nro_sha256": digest,
        "nro_size": size,
        "provenance": "UNSIGNED_LOCAL_RECORD",
        "limitations": (
            "This receipt was generated from workflow environment variables. "
            "Local JSON alone cannot authenticate GitHub origin. Independently "
            "verify GitHub run and artifact over HTTPS before copying to SD. "
            "No physical Switch launch or audible music has been verified."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("nro", type=Path)
    create.add_argument("--git-sha", required=True)
    create.add_argument("--branch", required=True)
    create.add_argument("--run-id", required=True, type=int)
    create.add_argument("--run-attempt", required=True, type=int)
    create.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("verify")
    check.add_argument("nro", type=Path)
    check.add_argument("--receipt", required=True, type=Path)
    check.add_argument("--expected-git-sha")
    check.add_argument("--expected-run-id", type=int)
    check.add_argument("--expected-branch")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            obj = issue(args.nro, args.git_sha, args.branch, args.run_id,
                        args.run_attempt, args.output)
            result = {"result": "CI_RECEIPT_CREATED",
                      "hardware_status": HARDWARE_STATUS,
                      "record": obj}
        else:
            result = verify(args.nro, args.receipt,
                            expected_git_sha=args.expected_git_sha,
                            expected_run_id=args.expected_run_id,
                            expected_branch=args.expected_branch)
    except (ReceiptError, bundle.BundleError, OSError, TypeError,
            KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
