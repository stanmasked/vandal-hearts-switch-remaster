#!/usr/bin/env python3
"""Verify an opt-in research NRO against the SAME-run baseline binary.

These hashes bind two downloaded artifacts to the workflow producer.
They are not signatures, emulator execution, or evidence of audible sound.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from verify_switch_runtime_nro import (
    HEX40, HEX64, RuntimeNroError, verify as verify_baseline,
)

EXPECTED = {"vandal-hearts-wet-tail.nro", "runtime-wet-tail-manifest.json"}
FIELDS = {
    "schema", "git_sha", "run_id", "run_attempt", "mode", "nro_name",
    "nro_bytes", "nro_sha256", "baseline_sha256",
}


def verify_pair(baseline_folder: Path, wet_folder: Path, *,
                sha: str, run_id: int, attempt: int) -> dict:
    """Reject changed, cross-run, structurally invalid or extra NRO bytes."""
    baseline = verify_baseline(baseline_folder, sha=sha,
                               run_id=run_id, attempt=attempt)
    if not HEX40.fullmatch(sha):
        raise RuntimeNroError("invalid commit SHA")
    if wet_folder.is_symlink() or not wet_folder.is_dir():
        raise RuntimeNroError("missing or symlinked experimental artifact")
    members = list(wet_folder.iterdir())
    if {m.name for m in members} != EXPECTED:
        raise RuntimeNroError("experimental artifact must contain exactly two files")
    if any(m.is_symlink() or not m.is_file() or m.stat().st_nlink != 1
           for m in members):
        raise RuntimeNroError("invalid experimental artifact member")
    manifest = wet_folder / "runtime-wet-tail-manifest.json"
    if manifest.stat().st_size > 2048:
        raise RuntimeNroError("experimental manifest too large")
    try:
        data = json.loads(manifest.read_text(encoding="ascii"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeNroError("invalid experimental JSON") from exc
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise RuntimeNroError("experimental manifest fields mismatch")
    if (data["schema"] != "vh-switch-explicit-wet-tail/v1"
            or data["git_sha"] != sha
            or type(data["run_id"]) is not int or data["run_id"] != run_id
            or type(data["run_attempt"]) is not int
            or data["run_attempt"] != attempt
            or type(data["mode"]) is not int or data["mode"] != 1
            or data["nro_name"] != "vandal-hearts-wet-tail.nro"):
        raise RuntimeNroError("wrong commit, run, attempt, mode or name")
    if (type(data["nro_bytes"]) is not int or data["nro_bytes"] < 1024
            or type(data["nro_sha256"]) is not str
            or not HEX64.fullmatch(data["nro_sha256"])
            or type(data["baseline_sha256"]) is not str
            or not HEX64.fullmatch(data["baseline_sha256"])):
        raise RuntimeNroError("bad size/digest fields")
    if data["baseline_sha256"] != baseline["nro_sha256"]:
        raise RuntimeNroError("experimental baseline hash mismatch")
    nro = wet_folder / "vandal-hearts-wet-tail.nro"
    if nro.stat().st_size != data["nro_bytes"]:
        raise RuntimeNroError("experimental byte size mismatch")
    digest = hashlib.sha256()
    with nro.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != data["nro_sha256"] or actual == baseline["nro_sha256"]:
        raise RuntimeNroError("altered or identical experimental NRO")
    import verify_switch_audio_bundle as bundle
    bundle.validate_nro_structure(nro)
    return {
        "result": "SAME_RUN_WET_TAIL_NRO_PAIR_VERIFIED",
        "git_sha": sha, "run_id": run_id, "run_attempt": attempt,
        "legacy_sha256": baseline["nro_sha256"],
        "wet_tail_sha256": actual,
        "hardware_status": "HARDWARE NOT TESTED",
        "emulator_status": "NOT LAUNCHED BY THIS CHECK",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_dir", type=Path)
    parser.add_argument("wet_tail_dir", type=Path)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        outcome = verify_pair(args.baseline_dir, args.wet_tail_dir,
                              sha=args.git_sha, run_id=args.run_id,
                              attempt=args.run_attempt)
    except (RuntimeNroError, OSError, ValueError) as exc:
        print(json.dumps({"result": "STOP_INVALID_WET_TAIL_PAIR",
                          "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(outcome, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
