#!/usr/bin/env python3
"""Stage 240: offline preflight for one integrated tactical NRO artifact.

The caller must independently obtain the run metadata and expected NRO hash.
Matching a hash in the same artifact is byte consistency, NOT provenance.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_switch_audio_bundle as bundle

EXPECTED_ARTIFACT = "vandal-hearts-tactical-with-native-music"
EXPECTED_NRO = "vandal-hearts-prototype.nro"
EXPECTED_HASH_FILE = "tactical-native.sha256"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH_LINE = re.compile(r"([0-9a-f]{64})  (?:build/)?vandal-hearts-prototype\.nro\n?\Z")

class PreflightError(ValueError):
    pass

def check(directory: Path, *, git_sha: str, run_id: int, artifact_id: int,
          artifact_name: str, expected_sha256: str) -> dict:
    if not FULL_SHA.fullmatch(git_sha) or not isinstance(run_id, int) or run_id <= 0:
        raise PreflightError("invalid pinned Git SHA or run ID")
    if not isinstance(artifact_id, int) or artifact_id <= 0:
        raise PreflightError("invalid artifact ID")
    if artifact_name != EXPECTED_ARTIFACT:
        raise PreflightError("wrong workflow artifact name")
    if not bundle.SHA256_RE.fullmatch(expected_sha256):
        raise PreflightError("expected NRO SHA-256 must be 64 lowercase hex digits")
    if not directory.is_dir() or directory.is_symlink():
        raise PreflightError("artifact directory missing or symlinked")
    # A CI artifact for this workflow contains exactly these two regular files.
    # Reject nested entries and symlinks rather than silently ignoring them.
    expected = {EXPECTED_NRO, EXPECTED_HASH_FILE}
    observed = list(directory.iterdir())
    unexpected = sorted(p.name for p in observed if p.name not in expected)
    if unexpected:
        raise PreflightError("unexpected artifact member: " + unexpected[0])
    if any(p.is_symlink() or not p.is_file() for p in observed):
        raise PreflightError("artifact members must be regular files")
    nro = directory / EXPECTED_NRO
    sha_file = directory / EXPECTED_HASH_FILE
    for path in (nro, sha_file):
        if path.is_symlink() or not path.is_file():
            raise PreflightError("required artifact member missing or symlinked")
    if sha_file.stat().st_size > 256:
        raise PreflightError("SHA-256 file unexpectedly large")
    try:
        record = sha_file.read_text(encoding="ascii")
    except UnicodeError as exc:
        raise PreflightError("SHA-256 file is not ASCII") from exc
    match = HASH_LINE.fullmatch(record)
    if not match:
        raise PreflightError("invalid tactical-native.sha256 format or filename")
    size, actual = bundle.digest_file(nro)
    if not size or actual != match.group(1) or actual != expected_sha256:
        raise PreflightError("NRO SHA-256 disagreement between local bytes and pinned values")
    bundle.validate_nro_structure(nro)
    return {
        "result": "READY_FOR_SD_TRANSFER_REVIEW",
        "hardware_status": bundle.HARDWARE_STATUS,
        "workflow_artifact": artifact_name,
        "git_sha_self_reported": git_sha,
        "run_id_self_reported": run_id,
        "artifact_id_self_reported": artifact_id,
        "nro_filename": EXPECTED_NRO,
        "nro_size": size,
        "nro_sha256": actual,
        "nro_structure": "STRUCTURAL_ONLY",
        "provenance": "USER_PINNED_METADATA_NOT_INDEPENDENTLY_AUTHENTICATED",
        "physical_switch_execution": "NOT_ATTESTED",
    }

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("artifact_dir", type=Path)
    p.add_argument("--git-sha", required=True)
    p.add_argument("--run-id", required=True, type=int)
    p.add_argument("--artifact-id", required=True, type=int)
    p.add_argument("--artifact-name", default=EXPECTED_ARTIFACT)
    p.add_argument("--expected-nro-sha256", required=True)
    args = p.parse_args(argv)
    try:
        result = check(args.artifact_dir, git_sha=args.git_sha,
                       run_id=args.run_id, artifact_id=args.artifact_id,
                       artifact_name=args.artifact_name,
                       expected_sha256=args.expected_nro_sha256)
    except (PreflightError, bundle.BundleError, OSError, ValueError) as exc:
        print(json.dumps({"result": "STOP_INVALID_PREFLIGHT",
                          "hardware_status": bundle.HARDWARE_STATUS, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
