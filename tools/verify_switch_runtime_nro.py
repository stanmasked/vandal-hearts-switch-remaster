#!/usr/bin/env python3
"""Verify an NRO downloaded from the build job in THIS SAME workflow run.

The manifest is emitted by the build job and checked against the live Actions
run identity and the downloaded NRO bytes. This is same-workflow traceability,
NOT independent attestation of a runner, author, console, or actual audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED = {"vandal-hearts-prototype.nro", "runtime-nro-manifest.json"}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class RuntimeNroError(ValueError):
    pass


def verify(folder: Path, *, sha: str, run_id: int, attempt: int) -> dict:
    if not HEX40.fullmatch(sha):
        raise RuntimeNroError("invalid current-run commit SHA")
    if type(run_id) is not int or run_id < 1:
        raise RuntimeNroError("invalid current workflow run ID")
    if type(attempt) is not int or attempt < 1:
        raise RuntimeNroError("invalid current workflow attempt")
    if folder.is_symlink() or not folder.is_dir():
        raise RuntimeNroError("missing or symlinked downloaded artifact folder")
    files = list(folder.iterdir())
    if {p.name for p in files} != EXPECTED:
        raise RuntimeNroError("artifact must contain precisely the NRO and manifest")
    if any(p.is_symlink() or not p.is_file() or p.stat().st_nlink != 1
           for p in files):
        raise RuntimeNroError("symlink, hardlink or non-regular artifact member")

    manifest_path = folder / "runtime-nro-manifest.json"
    if manifest_path.stat().st_size > 2048:
        raise RuntimeNroError("manifest too large")
    try:
        data = json.loads(manifest_path.read_text(encoding="ascii"))
    except (ValueError, UnicodeError) as exc:
        raise RuntimeNroError("invalid manifest JSON") from exc
    if not isinstance(data, dict) or set(data) != {
        "schema", "git_sha", "run_id", "run_attempt", "nro_name",
        "nro_bytes", "nro_sha256"
    }:
        raise RuntimeNroError("invalid manifest schema or extra fields")
    if (data["schema"] != "vh-switch-same-run-nro/v1"
            or data["git_sha"] != sha
            or type(data["run_id"]) is not int or data["run_id"] != run_id
            or type(data["run_attempt"]) is not int
            or data["run_attempt"] != attempt
            or data["nro_name"] != "vandal-hearts-prototype.nro"):
        raise RuntimeNroError("artifact from wrong commit, run or attempt")
    if (type(data["nro_bytes"]) is not int or data["nro_bytes"] < 1024
            or type(data["nro_sha256"]) is not str
            or not HEX64.fullmatch(data["nro_sha256"])):
        raise RuntimeNroError("invalid NRO size or digest field")
    nro = folder / "vandal-hearts-prototype.nro"
    size = nro.stat().st_size
    if size != data["nro_bytes"]:
        raise RuntimeNroError("NRO byte count does not match builder manifest")
    digest = hashlib.sha256()
    with nro.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != data["nro_sha256"]:
        raise RuntimeNroError("NRO SHA-256 disagrees with builder manifest")
    # The structure check is not an emulator/physical hardware test.
    import verify_switch_audio_bundle as bundle
    bundle.validate_nro_structure(nro)
    return {
        "result": "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED",
        "nro_filename": nro.name,
        "nro_sha256": digest.hexdigest(),
        "nro_bytes": size,
        "git_sha": sha,
        "run_id": run_id,
        "run_attempt": attempt,
        "scope": "same GitHub Actions workflow run build/upload/download; no independent attestation",
        "hardware_status": "HARDWARE NOT TESTED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("artifact_dir", type=Path)
    p.add_argument("--git-sha", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--run-attempt", type=int, required=True)
    args = p.parse_args(argv)
    try:
        result = verify(args.artifact_dir, sha=args.git_sha,
                        run_id=args.run_id, attempt=args.run_attempt)
    except (RuntimeNroError, OSError, ValueError) as exc:
        print(json.dumps({"result": "STOP_INVALID_SAME_RUN_NRO",
                          "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
