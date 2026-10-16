#!/usr/bin/env python3
"""Offline cross-check of a Switch NRO with its GitHub Actions artifact ZIP.

Inputs are downloaded GitHub REST JSON snapshots and an artifact ZIP, all
supplied by the operator. Equality cannot authenticate editable local JSON.
Physical Nintendo Switch audio is not measured or certified here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

import verify_switch_audio_bundle as bundle
import analyze_switch_audio_log as audio

REPOSITORY = "stanmasked/vandal-hearts-switch-remaster"
BRANCH = "test/cdxa-extract-decode-pipeline"
WORKFLOW_NAME = "Switch toolchain readiness"
WORKFLOW_PATH = ".github/workflows/switch-toolchain.yml"
ARTIFACT_NAME = "vandal-hearts-switch-prototype"
NRO_NAME = "vandal-hearts-prototype.nro"
REPORT_SCHEMA = "vh-switch-audio-provenance/v1"
MAX_JSON = 2 * 1024 * 1024
MAX_ZIP = 512 * 1024 * 1024
MAX_ENTRIES = 128
MAX_NRO = 128 * 1024 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class ProvenanceError(ValueError):
    """Metadata, ZIP, SHA or declared build identity failed verification."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceError(message)


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "missing or symlinked JSON snapshot")
    require(path.stat().st_size <= MAX_JSON, "JSON snapshot exceeds 2 MiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProvenanceError(f"invalid saved GitHub JSON: {exc}") from exc
    require(isinstance(data, dict), "GitHub JSON snapshot must be an object")
    return data


def number(value: object) -> bool:
    return type(value) is int and value > 0


def verify_identity(manifest: dict, run: dict, artifact: dict) -> None:
    sha = manifest["git_sha"]
    require(bool(re.fullmatch(r"[a-f0-9]{40}", sha)), "invalid manifest commit SHA")
    require(number(run.get("id")), "invalid workflow run ID")
    require(run.get("name") == WORKFLOW_NAME and run.get("path") == WORKFLOW_PATH,
            "wrong workflow identity/path")
    require(run.get("status") == "completed" and run.get("conclusion") == "success",
            "workflow run is not completed successfully")
    require(run.get("head_branch") == BRANCH, "workflow used unexpected branch")
    require(run.get("head_sha") == sha, "workflow commit does not match NRO manifest")
    repository = run.get("repository")
    require(isinstance(repository, dict) and
            repository.get("full_name") == REPOSITORY,
            "workflow belongs to a different repository")
    url = f"https://github.com/{REPOSITORY}/actions/runs/{run['id']}"
    require(run.get("html_url") == url, "workflow run URL mismatch")
    require(manifest.get("ci_run_url") == url,
            "manifest CI URL missing or disagrees with workflow run")
    require(number(artifact.get("id")), "invalid GitHub artifact ID")
    require(artifact.get("name") == ARTIFACT_NAME, "wrong GitHub artifact name")
    require(artifact.get("expired") is False, "GitHub artifact is expired")
    require(number(artifact.get("size_in_bytes")), "invalid artifact ZIP size")
    expected_digest = artifact.get("digest")
    require(isinstance(expected_digest, str) and
            bool(SHA256.fullmatch(expected_digest.removeprefix("sha256:"))) and
            expected_digest.startswith("sha256:"),
            "GitHub artifact is missing a SHA-256 digest")
    workflow = artifact.get("workflow_run")
    require(isinstance(workflow, dict) and workflow.get("id") == run["id"] and
            workflow.get("head_sha") == sha and
            workflow.get("head_branch") == BRANCH,
            "artifact belongs to another workflow run, commit or branch")
    artifact_url = (f"https://api.github.com/repos/{REPOSITORY}/"
                    f"actions/artifacts/{artifact['id']}")
    require(artifact.get("url") == artifact_url,
            "artifact metadata URL does not match expected repository and ID")


def check_zip(zip_path: Path, artifact: dict, expected_nro_hash: str,
              expected_nro_size: int) -> dict:
    require(zip_path.is_file() and not zip_path.is_symlink(),
            "missing or symlinked GitHub artifact ZIP")
    size = zip_path.stat().st_size
    require(0 < size <= MAX_ZIP, "artifact ZIP size is outside allowed limits")
    require(size == artifact["size_in_bytes"], "artifact ZIP byte size mismatch")
    archive_hash = hashlib.sha256()
    with zip_path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            archive_hash.update(block)
    require("sha256:" + archive_hash.hexdigest() == artifact["digest"],
            "artifact ZIP SHA-256 mismatch")
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            members = archive.infolist()
            require(0 < len(members) <= MAX_ENTRIES, "artifact ZIP has invalid entry count")
            seen = set()
            candidates = []
            for info in members:
                name = info.filename
                parsed = PurePosixPath(name)
                require(isinstance(name, str) and name and
                        not parsed.is_absolute() and "\\" not in name and
                        all(part not in ("", ".", "..") for part in name.rstrip("/").split("/")),
                        "unsafe ZIP member path")
                require(name not in seen, "duplicate ZIP member path")
                seen.add(name)
                mode = info.external_attr >> 16
                require(not stat.S_ISLNK(mode), "ZIP contains a symbolic link")
                require(not (info.flag_bits & 0x1), "encrypted ZIP member")
                require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "unsupported ZIP compression method")
                if info.is_dir():
                    continue
                # GitHub Actions build/*.nro usually places files at ZIP root.
                if name in (NRO_NAME, "build/" + NRO_NAME):
                    candidates.append(info)
            require(len(candidates) == 1, "archive must contain exactly one expected NRO")
            info = candidates[0]
            require(0 < info.file_size <= MAX_NRO and
                    info.file_size == expected_nro_size,
                    "NRO size disagrees between archive and verified manifest")
            payload_hash = hashlib.sha256()
            total = 0
            with archive.open(info, "r") as payload:
                while block := payload.read(1024 * 1024):
                    total += len(block)
                    require(total <= MAX_NRO, "NRO exceeds bounded size")
                    payload_hash.update(block)
            require(total == expected_nro_size and
                    payload_hash.hexdigest() == expected_nro_hash,
                    "NRO bytes do not match the GitHub artifact ZIP")
            return {"archive_sha256": archive_hash.hexdigest(),
                    "zip_entry": info.filename, "nro_sha256": payload_hash.hexdigest(),
                    "nro_size": total}
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
        raise ProvenanceError(f"invalid or damaged artifact ZIP: {exc}") from exc


def crosscheck(root: Path, archive: Path, run_json: Path, artifact_json: Path) -> dict:
    checked = bundle.inspect(root)
    manifest = bundle.read_manifest(root)
    require(checked["integrity"] == "VERIFIED", "evidence bundle integrity failed")
    run = read_json(run_json)
    artifact = read_json(artifact_json)
    verify_identity(manifest, run, artifact)
    nro_file = manifest["nro"]
    require(isinstance(nro_file, dict) and
            PurePosixPath(nro_file["path"]).name == NRO_NAME,
            "manifest NRO is not the primary tactical prototype")
    result = check_zip(archive, artifact, nro_file["sha256"], nro_file["size"])
    return {
        "schema": REPORT_SCHEMA,
        "comparison": "CONSISTENT_WITH_PROVIDED_GITHUB_METADATA",
        "build_provenance": "LOCAL_METADATA_CROSSCHECK_NOT_SIGNED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "run_id": run["id"],
        "artifact_id": artifact["id"],
        "git_sha": manifest["git_sha"],
        "workflow_name": WORKFLOW_NAME,
        "artifact_name": ARTIFACT_NAME,
        "verified_archive": result,
        "limitations": (
            "The script cannot authenticate operator-supplied JSON metadata; "
            "obtain it over HTTPS directly from GitHub and retain its URLs. "
            "It compares a ZIP to a local NRO and GitHub metadata snapshots, "
            "not a signed build attestation. No physical Switch run or audible sound was tested."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--artifact-zip", type=Path, required=True)
    parser.add_argument("--run-json", type=Path, required=True)
    parser.add_argument("--artifact-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = crosscheck(args.bundle.resolve(), args.artifact_zip,
                            args.run_json, args.artifact_json)
    except (ProvenanceError, bundle.BundleError, audio.LogFormatError,
            OSError, KeyError, TypeError) as exc:
        print(json.dumps({"comparison": "FAILED", "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
