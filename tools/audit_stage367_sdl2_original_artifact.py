#!/usr/bin/env python3
"""Stage367: independently validate preserved *original* failed SDL2 install evidence.

Verifies archived Github artifact identity and content. Never marks failed SDL2 CI
green, never substitutes native libnx results for unavailable SDL2 binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ARTIFACT_ID = 12246243370
RUN_ID = 39384172009
JOB_ID = 118499937561
HEAD_SHA = "f9a4354a9c98a29ff2676b2325c926587d2b897a"
ARTIFACT_NAME = "stage366-sdl2-portlib-install-evidence"
ARTIFACT_DIGEST = "sha256:3a1565e7b9b7e125dcb83e58a7a332b23c06fc454bd0b0f28ac9b165a046a676"
RAW = "stage366-sdl2-install.log"
REPORT = "stage366-sdl2-diagnostic.txt"
VERDICT = "STAGE367_ORIGINAL_SDL2_HTTP403_EVIDENCE_REAUDITED_CI_STILL_FAILED"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json_file(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 65536,
            "missing, linked, or oversized GitHub metadata")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(type(value) is dict, "metadata must be an object")
    return value


def audit(root: Path, meta: dict, job: dict) -> dict:
    require(root.is_dir() and not root.is_symlink() and
            not any(p.is_symlink() for p in root.parents),
            "original extracted artifact root invalid")
    require(type(meta.get("id")) is int and meta["id"] == ARTIFACT_ID and
            meta.get("name") == ARTIFACT_NAME and
            meta.get("digest") == ARTIFACT_DIGEST and
            meta.get("expired") is False and
            meta.get("size_in_bytes") == 905,
            "GitHub artifact metadata does not match pinned original")
    wr = meta.get("workflow_run")
    require(type(wr) is dict and
            type(wr.get("id")) is int and wr["id"] == RUN_ID and
            wr.get("head_sha") == HEAD_SHA and
            wr.get("head_branch") == "audio/stage322-rolling-playbuffer-history",
            "artifact not bound to original Stage366 workflow source")
    require(type(job.get("id")) is int and job["id"] == JOB_ID and
            type(job.get("run_id")) is int and job["run_id"] == RUN_ID and
            job.get("conclusion") == "failure" and
            job.get("name") == "Build and validate Switch SDL2 music audio NRO",
            "original job was not the expected failed SDL2 job")
    steps = job.get("steps")
    require(type(steps) is list, "missing original job step evidence")
    outcomes = {}
    for step in steps:
        require(type(step) is dict and type(step.get("name")) is str and
                type(step.get("conclusion")) is str and
                step["name"] not in outcomes, "ambiguous job step")
        outcomes[step["name"]] = step["conclusion"]
    require(
        outcomes.get("Install Nintendo Switch SDL2 development libraries") == "failure" and
        outcomes.get("Preserve Stage366 SDL2 install evidence even when dependency fails") == "success" and
        outcomes.get("Compile and inspect music NRO") == "skipped" and
        outcomes.get("Run synthetic native music tests") == "skipped" and
        outcomes.get("Upload synthetic/local-resource audio NRO") == "skipped",
        "failure or not-built boundary contradicted by original workflow job")
    entries = list(root.iterdir())
    require({p.name for p in entries} == {RAW, REPORT} and len(entries) == 2,
            "original artifact must contain exactly two known files")
    source = {}
    for name in (RAW, REPORT):
        f = root / name
        require(f.is_file() and not f.is_symlink() and
                0 < f.stat().st_size < 32768,
                "absent, empty, linked, or oversized original evidence: " + name)
        source[name] = f.read_bytes()
    raw = source[RAW].decode("utf-8")
    diagnosis = source[REPORT].decode("utf-8")
    require("curl: (22) The requested URL returned error: 403" in raw and
            "failed to synchronize all databases" in raw,
            "original pacman log does not establish the mirror HTTP 403")
    parser = json.JSONDecoder()
    obj, end = parser.raw_decode(diagnosis.lstrip())
    require(type(obj) is dict and
            diagnosis.lstrip()[end:].strip().startswith(
                "::error title=Optional Switch dependency unavailable::"),
            "missing structured classifier and original failure annotation")
    require(obj.get("result") == "OPTIONAL_DEPENDENCY_NOT_INSTALLED" and
            obj.get("failure_code") == "EXTERNAL_DEVKITPRO_MIRROR_HTTP_403" and
            obj.get("package") == "switch-sdl2" and
            obj.get("compile_performed") is False and
            obj.get("dependency_accepted") is False and
            obj.get("hardware_status") == "HARDWARE NOT TESTED" and
            "Keep this job failed" in str(obj.get("recommended_action", "")),
            "archived original diagnosis falsely claims SDL2 success")
    return {
        "schema": "vh-stage367-original-failed-sdl2-portlib-install/v1",
        "result": VERDICT,
        "original_run_id": RUN_ID,
        "original_job_id": JOB_ID,
        "original_artifact_id": ARTIFACT_ID,
        "original_source_commit": HEAD_SHA,
        "github_reported_artifact_zip_digest": ARTIFACT_DIGEST,
        "original_log_sha256": hashlib.sha256(source[RAW]).hexdigest(),
        "original_diagnostic_sha256": hashlib.sha256(source[REPORT]).hexdigest(),
        "original_install_http_403": True,
        "github_job_still_failed": True,
        "sdl2_compilation_performed": False,
        "sdl2_nro_produced": False,
        "physical_switch_audio_tested": False,
        "old_kernel_0xEA01_cause_proven": False,
    }


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--original", type=Path, required=True)
    cli.add_argument("--metadata", type=Path, required=True)
    cli.add_argument("--job", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    a = cli.parse_args(argv)
    try:
        require(not a.output.exists() and not a.output.is_symlink(),
                "refuse overwrite existing verdict")
        result = audit(a.original, read_json_file(a.metadata), read_json_file(a.job))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
        print(json.dumps({"result": VERDICT,
                          "original_job_still_failed": True,
                          "sdl2_nro_built": False}, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, UnicodeError, json.JSONDecodeError) as err:
        print(json.dumps({"result": "STAGE367_ORIGINAL_NOT_VERIFIED",
                          "error_kind": type(err).__name__,
                          "sdl2_build_success_claimed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
