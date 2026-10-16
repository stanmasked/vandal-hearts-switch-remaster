#!/usr/bin/env python3
"""Stage 218: read-only verification of a manually copied Switch NRO.

'plan' writes a host-side evidence plan, never onto the SD. 'verify' hashes
both the recorded NRO and the file at a chosen SD-mount path. Matching bytes
do not prove the path is real removable SD media, durable after power loss,
or executable / audible on a physical Nintendo Switch.

The program NEVER copies, overwrites, deletes, renames or syncs SD files.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

import analyze_switch_audio_log as audio
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-sd-transfer/v1"
DEFAULT_DESTINATION = "switch/vandal-hearts-remake/vandal-hearts-prototype.nro"
NRO_FILENAME = "vandal-hearts-prototype.nro"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
MAX_PLAN = 32 * 1024


class TransferError(ValueError):
    """Unsafe path, modified source, or incomplete destination copy."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TransferError(message)


def within(child: Path, parent: Path) -> bool:
    return child == parent or child.is_relative_to(parent)


def roots(bundle_path: Path, sd_path: Path) -> tuple[Path, Path]:
    # A symlink pretending to be the SD mount path must not pass silently.
    require(not sd_path.is_symlink(), "SD mount root must not be a symbolic link")
    require(sd_path.is_dir(), "SD mount root is missing or is not a directory")
    root, sd_root = bundle_path.resolve(), sd_path.resolve()
    require(root.is_dir(), "source evidence bundle directory does not exist")
    require(not (within(root, sd_root) or within(sd_root, root)),
            "SD mount and evidence bundle must be separate directory trees")
    return root, sd_root


def destination(sd_root: Path, relative: str, *, must_exist: bool) -> Path:
    require(isinstance(relative, str) and relative and "\\" not in relative,
            "invalid SD destination path")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and relative == parsed.as_posix() and
            all(part not in ("", ".", "..") for part in relative.split("/")) and
            parsed.name == NRO_FILENAME, "unsafe or non-prototype SD destination path")
    current = sd_root
    for part in parsed.parts:
        current = current / part
        require(not current.is_symlink(), "SD destination contains a symbolic link")
    require(within(current.resolve(), sd_root),
            "SD destination escapes its mount root")
    if current.exists():
        require(current.is_file(), "SD destination must be a regular file")
    elif must_exist:
        raise TransferError("SD destination NRO is missing: copy manually before verify")
    return current


def source_record(root: Path) -> tuple[dict, dict]:
    report = bundle.inspect(root)
    require(report["integrity"] == "VERIFIED", "source bundle SHA verification failed")
    manifest = bundle.read_manifest(root)
    item = manifest["nro"]
    require(PurePosixPath(item["path"]).name == NRO_FILENAME,
            "source bundle is not the main tactical prototype NRO")
    return manifest, item


def fingerprint(path: Path) -> dict:
    size, digest = bundle.digest_file(path)
    return {"size": size, "sha256": digest}


def read_plan(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "missing or symbolic-link transfer plan")
    require(path.stat().st_size <= MAX_PLAN, "transfer plan exceeds 32 KiB")
    try:
        plan = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TransferError(f"invalid transfer plan: {exc}") from exc
    require(isinstance(plan, dict), "transfer plan must be an object")
    expected = {"schema", "hardware_status", "git_sha", "source_nro",
                "source_manifest_sha256", "sd_destination",
                "destination_before", "copy_performed"}
    require(set(plan) == expected and plan["schema"] == SCHEMA,
            "unsupported or invalid transfer plan format")
    require(plan["hardware_status"] == bundle.HARDWARE_STATUS and
            plan["copy_performed"] is False,
            "transfer plan must not claim hardware approval or copying")
    require(isinstance(plan["git_sha"], str) and
            bool(re.fullmatch(r"[a-f0-9]{40}", plan["git_sha"])),
            "invalid transfer plan commit SHA")
    require(isinstance(plan["source_manifest_sha256"], str) and
            bool(SHA256.fullmatch(plan["source_manifest_sha256"])),
            "invalid evidence manifest SHA-256")
    file = plan["source_nro"]
    require(isinstance(file, dict) and
            set(file) == {"path", "size", "sha256"} and
            isinstance(file["path"], str) and
            type(file["size"]) is int and file["size"] > 0 and
            isinstance(file["sha256"], str) and
            bool(SHA256.fullmatch(file["sha256"])),
            "invalid source NRO identity")
    old = plan["destination_before"]
    require(old is None or (isinstance(old, dict) and
            set(old) == {"size", "sha256"} and
            type(old["size"]) is int and old["size"] >= 0 and
            isinstance(old["sha256"], str) and
            bool(SHA256.fullmatch(old["sha256"]))),
            "invalid prior SD destination fingerprint")
    return plan


def create_plan(bundle_path: Path, sd_path: Path, output: Path,
                relative: str = DEFAULT_DESTINATION) -> dict:
    root, sd_root = roots(bundle_path, sd_path)
    manifest, nro = source_record(root)
    target = destination(sd_root, relative, must_exist=False)
    plan_file = output.absolute()
    require(not plan_file.is_symlink(), "plan path may not be a symbolic link")
    require(plan_file.parent.is_dir(), "plan output directory is missing")
    require(not within(plan_file.resolve(), root) and
            not within(plan_file.resolve(), sd_root),
            "transfer plan must be saved outside the evidence and SD trees")
    require(not plan_file.exists(), "transfer plan already exists; refusing overwrite")
    # If a previous NRO is present, preserve its fingerprint as a baseline.
    if target.exists():
        src = bundle.safe_member(root, nro["path"], ".nro")
        require(not os.path.samefile(src, target),
                "SD target and evidence source are the same underlying file")
    old = fingerprint(target) if target.exists() else None
    manifest_path = root / bundle.MANIFEST_NAME
    manifest_hash = fingerprint(manifest_path)["sha256"]
    plan = {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "git_sha": manifest["git_sha"],
        "source_nro": nro,
        "source_manifest_sha256": manifest_hash,
        "sd_destination": relative,
        "destination_before": old,
        "copy_performed": False,
    }
    with plan_file.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    return {
        "result": "SOURCE_FINGERPRINT_RECORDED",
        "source_nro": nro,
        "sd_destination": relative,
        "destination_previously_existed": old is not None,
        "requires_manual_copy": True,
        "destination_medium": "NOT_VERIFIED_AS_PHYSICAL_SD",
        "hardware_status": bundle.HARDWARE_STATUS,
    }


def verify(bundle_path: Path, sd_path: Path, plan_path: Path) -> dict:
    root, sd_root = roots(bundle_path, sd_path)
    plan_file = plan_path.absolute()
    require(not within(plan_file.resolve(), root) and
            not within(plan_file.resolve(), sd_root),
            "transfer plan must be outside the evidence and SD trees")
    plan = read_plan(plan_file)
    manifest, nro = source_record(root)
    require(manifest["git_sha"] == plan["git_sha"] and
            nro == plan["source_nro"], "bundle source identity changed after planning")
    require(fingerprint(root / bundle.MANIFEST_NAME)["sha256"] ==
            plan["source_manifest_sha256"], "source evidence manifest changed")
    target = destination(sd_root, plan["sd_destination"], must_exist=True)
    source = bundle.safe_member(root, nro["path"], ".nro")
    require(not os.path.samefile(source, target),
            "SD destination is the same underlying file as source")
    size, digest = bundle.digest_file(target)
    require(size == nro["size"] and digest == nro["sha256"],
            "SD NRO bytes differ from planned source SHA-256/size")
    # Destination is separately validated, not just accepted by matching
    # an unauthenticated local manifest hash.
    bundle.validate_nro_structure(target)
    old = plan["destination_before"]
    return {
        "result": "DESTINATION_BYTES_MATCH_PLANNED_NRO",
        "hardware_status": bundle.HARDWARE_STATUS,
        "source_git_sha_self_reported": manifest["git_sha"],
        "nro_sha256": digest,
        "nro_size": size,
        "sd_destination": plan["sd_destination"],
        "destination_previously_existed": old is not None,
        "destination_was_already_identical_before_plan": (
            old is not None and old["sha256"] == digest and old["size"] == size),
        "copy_operation": "NOT_OBSERVED_BY_VERIFIER",
        "destination_medium": "NOT_VERIFIED_AS_PHYSICAL_SD",
        "sd_durability": "NOT_TESTED",
        "nro_runtime_and_sound": "HARDWARE NOT TESTED",
        "limitations": (
            "Verification compares two local files; it does not perform or "
            "attest an SD copy, prove a removable SD mount, flush FAT metadata "
            "or test power-loss recovery. Independently run stage 217 live "
            "GitHub preflight and test audio on physical Nintendo Switch."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="action", required=True)
    prep = modes.add_parser("plan", help="record source and optional prior destination")
    prep.add_argument("bundle", type=Path)
    prep.add_argument("--sd-root", required=True, type=Path)
    prep.add_argument("--output", required=True, type=Path)
    prep.add_argument("--destination", default=DEFAULT_DESTINATION)
    check = modes.add_parser("verify", help="check manually copied NRO without modifying SD")
    check.add_argument("bundle", type=Path)
    check.add_argument("--sd-root", required=True, type=Path)
    check.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            result = create_plan(args.bundle, args.sd_root,
                                 args.output, args.destination)
        else:
            result = verify(args.bundle, args.sd_root, args.plan)
    except (TransferError, bundle.BundleError, audio.LogFormatError,
            OSError, TypeError, KeyError) as exc:
        print(json.dumps({"result": "FAILED", "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
