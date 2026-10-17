#!/usr/bin/env python3
"""Stage 234: pinned H05 baseline of an old audio CSV before a later launch.

A BEFORE snapshot lists *all* existing numbered SD CSV files plus their
original SHA256. An AFTER verification requires the earlier detached SHA256,
checks the exact old file remains unchanged, verifies pre-existing inventory,
and requires an explicitly selected *new* completed CSV absent at baseline.

Only a host-side read is performed; manual console runs, card reinsertion,
audible playback, and physical session independence are NOT attested. This
script never touches or writes files on the supplied SD-root.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import analyze_switch_audio_log as audio
import capture_switch_audio_sd_csv as capture
import verify_switch_audio_bundle as bundle
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-h05-csv-persistence/v1"
MAX_BASELINE = 64 * 1024
MAX_EXISTING = 128
FILE_FIELDS = {"name", "size", "sha256"}
KEYS = {
    "schema", "hardware_status", "phase", "git_sha_self_reported",
    "source_manifest_sha256", "transfer_plan_sha256", "nro_sha256",
    "nro_size", "old_csv_name", "old_csv_sha256", "old_csv_size",
    "existing_csv", "physical_second_run_attested", "manual_signoff",
}


class PersistenceError(ValueError):
    """Missing, replaced, reordered, noncanonical or unverifiable SD evidence."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise PersistenceError(reason)


def bytes_for(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def source_identity(source_bundle: Path, sd_root: Path, plan: Path) -> dict:
    root, mounted = transfer.roots(source_bundle, sd_root)
    require(plan.is_file() and not plan.is_symlink(),
            "original SD transfer plan absent or symbolic link")
    checked = transfer.verify(root, mounted, plan)
    manifest = bundle.read_manifest(root)
    require(manifest["ci_run_url"].startswith(
                "https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/"),
            "source manifest has no project GitHub Actions run")
    return {
        "git_sha_self_reported": checked["source_git_sha_self_reported"],
        "source_manifest_sha256": bundle.digest_file(
            root / bundle.MANIFEST_NAME)[1],
        "transfer_plan_sha256": bundle.digest_file(plan)[1],
        "nro_sha256": checked["nro_sha256"],
        "nro_size": checked["nro_size"],
    }


def inventory(sd_root: Path) -> list[dict]:
    capture.check_incomplete_exports(sd_root)
    directory = sd_root / capture.AUDIO_DIR
    names = sorted(p.name for p in directory.iterdir()
                   if capture.CSV_NAME.fullmatch(p.name) is not None)
    require(len(names) <= MAX_EXISTING, "more than 128 SD audio CSV entries")
    rows = []
    for name in names:
        path = capture.safe_source(sd_root, name)
        parsed = audio.load_csv(path)
        require(parsed[-1]["event"] == "EXIT",
                f"INCOMPLETE_CSV_EXPORT: {name} does not end with EXIT")
        size, digest = bundle.digest_file(path)
        require(0 < size <= audio.BYTES_LIMIT,
                "SD CSV outside bounded journal size")
        rows.append({"name": name, "size": size, "sha256": digest})
    return rows


def stable_inventory(sd_root: Path) -> list[dict]:
    before = inventory(sd_root)
    after = inventory(sd_root)
    require(before == after,
            "SD_CSV_INVENTORY_CHANGED_DURING_READBACK")
    return before


def validate_baseline(value: object) -> dict:
    require(isinstance(value, dict) and set(value) == KEYS,
            "invalid H05 baseline schema")
    obj = value
    require(obj["schema"] == SCHEMA and
            obj["hardware_status"] == bundle.HARDWARE_STATUS and
            obj["phase"] == "BEFORE_CLAIMED_SECOND_RUN" and
            obj["physical_second_run_attested"] is False and
            obj["manual_signoff"] == "REQUIRED_NOT_AUTOMATED",
            "H05 baseline must never claim physical testing")
    require(isinstance(obj["git_sha_self_reported"], str) and
            bundle.GIT_SHA_RE.fullmatch(obj["git_sha_self_reported"]) is not None,
            "invalid baseline full Git SHA")
    for key in ("source_manifest_sha256", "transfer_plan_sha256",
                "nro_sha256", "old_csv_sha256"):
        require(isinstance(obj[key], str) and
                bundle.SHA256_RE.fullmatch(obj[key]) is not None,
                f"invalid H05 {key}")
    for key in ("nro_size", "old_csv_size"):
        require(type(obj[key]) is int and obj[key] > 0,
                f"invalid H05 {key}")
    require(isinstance(obj["old_csv_name"], str) and
            capture.CSV_NAME.fullmatch(obj["old_csv_name"]) is not None,
            "invalid old CSV name")
    items = obj["existing_csv"]
    require(isinstance(items, list) and
            1 <= len(items) <= MAX_EXISTING, "invalid existing CSV inventory")
    prior = ""
    for item in items:
        require(isinstance(item, dict) and set(item) == FILE_FIELDS and
                isinstance(item["name"], str) and
                capture.CSV_NAME.fullmatch(item["name"]) is not None and
                item["name"] > prior and
                type(item["size"]) is int and
                0 < item["size"] <= audio.BYTES_LIMIT and
                isinstance(item["sha256"], str) and
                bundle.SHA256_RE.fullmatch(item["sha256"]) is not None,
                "invalid or unordered existing SD CSV entries")
        prior = item["name"]
    match = [item for item in items if item["name"] == obj["old_csv_name"]]
    require(len(match) == 1 and match[0]["sha256"] == obj["old_csv_sha256"] and
            match[0]["size"] == obj["old_csv_size"],
            "old CSV fingerprint differs from its baseline inventory")
    return obj


def read_baseline(path: Path, expected_sha256: str) -> dict:
    require(isinstance(expected_sha256, str) and
            bundle.SHA256_RE.fullmatch(expected_sha256) is not None,
            "independent baseline SHA-256 must contain 64 lowercase hex digits")
    require(path.is_file() and not path.is_symlink(),
            "H05 baseline missing or symlinked")
    require(0 < path.stat().st_size <= MAX_BASELINE,
            "H05 baseline exceeds 64 KiB limit")
    raw = path.read_bytes()
    require(sha256(raw) == expected_sha256,
            "H05_BASELINE_SHA256_MISMATCH: original baseline was modified")
    try:
        obj = json.loads(raw.decode("utf-8"),
                         object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PersistenceError(f"malformed H05 baseline JSON: {exc}") from exc
    validated = validate_baseline(obj)
    require(raw == bytes_for(validated),
            "NONCANONICAL_H05_BASELINE")
    return validated


def outside_evidence(path: Path, source_bundle: Path, sd_root: Path) -> None:
    require(path.parent.is_dir() and not path.parent.is_symlink() and
            not path.is_symlink(), "baseline parent missing or symbolic link")
    absolute = path.absolute().resolve()
    require(not absolute.is_relative_to(source_bundle.resolve()) and
            not absolute.is_relative_to(sd_root.resolve()),
            "H05 baseline must be outside original source and SD directories")


def record(source_bundle: Path, sd_root: Path, plan: Path,
           old_csv_name: str, output: Path) -> dict:
    outside_evidence(output, source_bundle, sd_root)
    require(not output.exists(), "H05 baseline exists; refusing overwrite")
    capture.csv_selection([old_csv_name])
    build = source_identity(source_bundle, sd_root, plan)
    items = stable_inventory(sd_root)
    old = next((item for item in items if item["name"] == old_csv_name), None)
    require(old is not None,
            "OLD_CSV_NOT_PRESENT_BEFORE_SECOND_RUN")
    obj = validate_baseline({
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "phase": "BEFORE_CLAIMED_SECOND_RUN",
        **build,
        "old_csv_name": old_csv_name,
        "old_csv_sha256": old["sha256"],
        "old_csv_size": old["size"],
        "existing_csv": items,
        "physical_second_run_attested": False,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    })
    raw = bytes_for(obj)
    require(len(raw) <= MAX_BASELINE, "H05 inventory baseline too large")
    # Output is intentionally host-only, exclusive-create, never overwrite.
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "result": "H05_OLD_CSV_BASELINE_RECORDED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "baseline_sha256": sha256(raw),
        "old_csv_sha256": old["sha256"],
        "existing_csv_count": len(items),
        "physical_second_run_attested": False,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "next_action": (
            "Save baseline SHA-256 independently. Only after an actual safe "
            "second Switch run and completed EXIT CSV, recheck using the "
            "independently pinned baseline and new numbered CSV filename."
        ),
    }


def recheck(source_bundle: Path, sd_root: Path, plan: Path,
            baseline_path: Path, expected_sha256: str,
            new_csv_name: str, *, operator_confirmed_second_run: bool = False) -> dict:
    require(operator_confirmed_second_run is True,
            "OPERATOR_CONFIRMATION_REQUIRED: second physical run must "
            "be independently documented")
    outside_evidence(baseline_path, source_bundle, sd_root)
    baseline = read_baseline(baseline_path, expected_sha256)
    require(isinstance(new_csv_name, str) and
            capture.CSV_NAME.fullmatch(new_csv_name) is not None,
            "new CSV name is not a numbered audio export")
    require(new_csv_name != baseline["old_csv_name"],
            "NEW_CSV_IS_OLD_FILE")
    prior = {item["name"]: item for item in baseline["existing_csv"]}
    require(new_csv_name not in prior,
            "NEW_CSV_ALREADY_PRESENT_AT_BASELINE")
    identity = source_identity(source_bundle, sd_root, plan)
    for key in identity:
        require(identity[key] == baseline[key],
                f"SOURCE_BUILD_CHANGED_SINCE_H05_BASELINE: {key}")
    current = stable_inventory(sd_root)
    present = {item["name"]: item for item in current}
    require(new_csv_name in present, "NEW_CSV_MISSING_AFTER_SECOND_RUN")
    require(baseline["old_csv_name"] in present and
            present[baseline["old_csv_name"]]["sha256"] ==
            baseline["old_csv_sha256"] and
            present[baseline["old_csv_name"]]["size"] ==
            baseline["old_csv_size"], "H05_OLD_CSV_CHANGED_OR_REMOVED")
    for name, old in prior.items():
        require(name in present and old == present[name],
                f"PREEXISTING_CSV_CHANGED_OR_REMOVED: {name}")
    require(present[new_csv_name]["sha256"] != baseline["old_csv_sha256"],
            "NEW_CSV_IDENTICAL_TO_OLD_PAYLOAD")
    require(all(present[new_csv_name]["sha256"] != file["sha256"]
                for file in prior.values()),
            "NEW_CSV_DUPLICATES_PREEXISTING_CSV_PAYLOAD")
    require(sha256(baseline_path.read_bytes()) == expected_sha256,
            "H05_BASELINE_CHANGED_DURING_RECHECK")
    added = [name for name in present if name not in prior]
    return {
        "schema": "vh-switch-audio-h05-review/v1",
        "result": "H05_FILE_PERSISTENCE_CONSISTENT_FOR_MANUAL_REVIEW",
        "hardware_status": bundle.HARDWARE_STATUS,
        "baseline_sha256": expected_sha256,
        "git_sha_self_reported": identity["git_sha_self_reported"],
        "nro_sha256": identity["nro_sha256"],
        "old_csv_name": baseline["old_csv_name"],
        "old_csv_sha256": baseline["old_csv_sha256"],
        "new_csv_name": new_csv_name,
        "new_csv_sha256": present[new_csv_name]["sha256"],
        "additional_new_csv_names_unattributed":
            [name for name in added if name != new_csv_name],
        "existing_csv_retained_count": len(prior),
        "operator_claim": "SECOND_RUN_SELF_REPORTED_NOT_ATTESTED",
        "physical_second_run_attested": False,
        "audio_attested": False,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "limitations": (
            "A new filename and changed CSV SHA do not establish a second "
            "independent physical Switch run, audible output, true SD media, "
            "or FAT durability. The operator's confirmation is unverified."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_subparsers(dest="action", required=True)
    for mode in ("record", "recheck"):
        cmd = actions.add_parser(mode)
        cmd.add_argument("--source-bundle", type=Path, required=True)
        cmd.add_argument("--sd-root", type=Path, required=True)
        cmd.add_argument("--transfer-plan", type=Path, required=True)
        if mode == "record":
            cmd.add_argument("--old-csv", required=True)
            cmd.add_argument("--output", required=True, type=Path)
        else:
            cmd.add_argument("--baseline", required=True, type=Path)
            cmd.add_argument("--expected-baseline-sha256", required=True)
            cmd.add_argument("--new-csv", required=True)
            cmd.add_argument("--operator-confirmed-second-run", action="store_true")
    args = p.parse_args(argv)
    try:
        if args.action == "record":
            result = record(args.source_bundle, args.sd_root, args.transfer_plan,
                            args.old_csv, args.output)
        else:
            result = recheck(
                args.source_bundle, args.sd_root, args.transfer_plan,
                args.baseline, args.expected_baseline_sha256, args.new_csv,
                operator_confirmed_second_run=args.operator_confirmed_second_run)
    except (PersistenceError, capture.CaptureError, transfer.TransferError,
            bundle.BundleError, audio.LogFormatError,
            OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
