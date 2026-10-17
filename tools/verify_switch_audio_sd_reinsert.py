#!/usr/bin/env python3
"""Stage 231: independently pinned SD-root readback before/after manual reinsertion.

"record" performs stage 230 live GitHub-to-SD NRO validation and writes a
host-side baseline exclusively, outside the evidence bundle and SD root.
"recheck" accepts the baseline only when its SHA-256 has been retained in an
independent record, then reruns the WHOLE stage 230 live check and compares
all build, NRO, artifact, plan and manifest identities.

The operator explicitly declares they safely ejected and reinserted the card;
software CANNOT establish that it was really unmounted or is physical SD.
No file is written to the card, no unmount is attempted. Neither successful
result is proof of physical Switch execution, audible music or SD durability.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

import analyze_switch_audio_log as audio
import switch_audio_ci_build_receipt as ci_receipt
import verify_switch_audio_build_provenance as provenance
import verify_switch_audio_bundle as bundle
import verify_switch_audio_launch_gate as launch
import verify_switch_audio_live_preflight as preflight
import verify_switch_audio_sd_transfer as sd_transfer

SCHEMA = "vh-switch-audio-manual-sd-reinsert/v1"
MAX_BASELINE = 16 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
BASELINE_KEYS = {
    "schema", "hardware_status", "phase", "provenance", "build_git_sha",
    "run_id", "artifact_id", "run_attempt", "artifact_zip_sha256",
    "installed_nro_sha256", "installed_nro_size", "sd_destination_relative",
    "manifest_sha256", "transfer_plan_sha256", "checked_at_utc",
    "remount_performed", "physical_sd_attested",
}
IDENTITY_KEYS = (
    "build_git_sha", "run_id", "artifact_id", "run_attempt",
    "artifact_zip_sha256", "installed_nro_sha256", "installed_nro_size",
    "sd_destination_relative", "manifest_sha256", "transfer_plan_sha256",
)


class ReinsertError(ValueError):
    """Fail-closed altered baseline, unsafe output, or mismatched post-check."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ReinsertError(message)


def digest_file(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(),
            "baseline input missing or symlinked")
    return bundle.digest_file(path)[1]


def baseline_bytes(record: dict) -> bytes:
    return (json.dumps(record, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def anchored_file(path: Path, sd_root: Path, bundle_path: Path) -> None:
    require(path.parent.is_dir() and not path.is_symlink(),
            "baseline path parent missing or symlinked")
    saved = path.absolute().resolve()
    require(not saved.is_relative_to(sd_root.resolve()) and
            not saved.is_relative_to(bundle_path.resolve()),
            "baseline must be saved outside source evidence and SD directories")


def observed_values(report: dict, bundle_path: Path, plan: Path) -> dict:
    require(report["result"] == "READY_FOR_MANUAL_DEVICE_LAUNCH" and
            report["hardware_status"] == bundle.HARDWARE_STATUS,
            "the live stage 230 gate did not establish source/SD NRO identity")
    return {
        "build_git_sha": report["git_sha_confirmed_by_github_at_check_time"],
        "run_id": report["run_id"],
        "artifact_id": report["artifact_id"],
        "run_attempt": report["run_attempt"],
        "artifact_zip_sha256": report["artifact_zip_sha256"],
        "installed_nro_sha256": report["installed_nro_sha256"],
        "installed_nro_size": report["installed_nro_size"],
        "sd_destination_relative": report["sd_destination_relative"],
        "manifest_sha256": digest_file(
            bundle_path.resolve() / bundle.MANIFEST_NAME),
        "transfer_plan_sha256": digest_file(plan),
    }


def baseline_schema(record: object) -> dict:
    require(isinstance(record, dict) and set(record) == BASELINE_KEYS,
            "invalid SD readback baseline schema")
    require(record["schema"] == SCHEMA and
            record["hardware_status"] == bundle.HARDWARE_STATUS and
            record["phase"] == "BEFORE_MANUAL_REMOUNT" and
            record["provenance"] == "LIVE_GITHUB_AND_LOCAL_BYTE_MATCH_NOT_SIGNED" and
            record["remount_performed"] is False and
            record["physical_sd_attested"] is False,
            "forged hardware/remount state in baseline")
    require(isinstance(record["build_git_sha"], str) and
            ci_receipt.SHA40.fullmatch(record["build_git_sha"]) is not None,
            "invalid baseline Git commit")
    for key in ("run_id", "artifact_id", "run_attempt", "installed_nro_size"):
        require(type(record[key]) is int and record[key] > 0,
                f"invalid baseline {key}")
    for key in ("artifact_zip_sha256", "installed_nro_sha256",
                "manifest_sha256", "transfer_plan_sha256"):
        require(isinstance(record[key], str) and SHA256.fullmatch(record[key]) is not None,
                f"invalid baseline {key}")
    relative = record["sd_destination_relative"]
    require(isinstance(relative, str) and relative and
            "\\" not in relative and
            all(part not in ("", ".", "..") for part in relative.split("/")),
            "invalid SD NRO destination in baseline")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and parsed.as_posix() == relative and
            parsed.name == sd_transfer.NRO_FILENAME,
            "invalid SD NRO destination in baseline")
    value = record["checked_at_utc"]
    require(isinstance(value, str) and len(value) <= 40,
            "baseline timestamp missing")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReinsertError("baseline timestamp is invalid") from exc
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "baseline timestamp must have a timezone")
    return record


def read_baseline(path: Path, independent_sha256: str) -> dict:
    require(isinstance(independent_sha256, str) and
            SHA256.fullmatch(independent_sha256) is not None,
            "expected baseline SHA-256 must be 64 lowercase hex characters")
    require(path.is_file() and not path.is_symlink(),
            "baseline is missing or a symbolic link")
    require(path.stat().st_size <= MAX_BASELINE,
            "baseline exceeds 16 KiB limit")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == independent_sha256,
            "BASELINE_SHA256_MISMATCH: previous readback report was altered")
    try:
        record = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReinsertError(f"invalid baseline JSON: {exc}") from exc
    baseline_schema(record)
    require(baseline_bytes(record) == raw, "noncanonical baseline JSON")
    return record


def live_check(bundle_path: Path, archive: Path, sd_root: Path, plan: Path,
               run_id: int, artifact_id: int, *,
               api_fetch=None, now: datetime | None = None) -> dict:
    args = {}
    if api_fetch is not None:
        args["api_fetch"] = api_fetch
    if now is not None:
        args["now"] = now
    return launch.evaluate(
        bundle_path, archive, sd_root, plan, run_id, artifact_id, **args)


def record(bundle_path: Path, archive: Path, sd_root: Path, plan: Path,
           run_id: int, artifact_id: int, output: Path, *,
           api_fetch=None, now: datetime | None = None) -> dict:
    anchored_file(output, sd_root, bundle_path)
    require(not output.exists(), "baseline exists; refusing overwrite")
    verified = live_check(bundle_path, archive, sd_root, plan,
                          run_id, artifact_id, api_fetch=api_fetch, now=now)
    item = {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "phase": "BEFORE_MANUAL_REMOUNT",
        "provenance": "LIVE_GITHUB_AND_LOCAL_BYTE_MATCH_NOT_SIGNED",
        **observed_values(verified, bundle_path, plan),
        "checked_at_utc": verified["checked_at_utc"],
        "remount_performed": False,
        "physical_sd_attested": False,
    }
    baseline_schema(item)
    raw = baseline_bytes(item)
    require(len(raw) <= MAX_BASELINE, "baseline too large")
    with output.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "result": "PRE_REMOUNT_SD_READBACK_RECORDED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "baseline_sha256": hashlib.sha256(raw).hexdigest(),
        "build_git_sha": item["build_git_sha"],
        "installed_nro_sha256": item["installed_nro_sha256"],
        "baseline_outside_sd": True,
        "next_action": (
            "Save the baseline SHA-256 separately. Safely eject the removable "
            "medium using your OS, physically disconnect and reconnect it, "
            "then run recheck and explicitly acknowledge the manual steps."
        ),
        "physical_sd_attested": False,
    }


def recheck(bundle_path: Path, archive: Path, sd_root: Path, plan: Path,
            run_id: int, artifact_id: int, baseline: Path,
            expected_baseline_sha256: str, *,
            operator_confirmed_reinsert: bool = False,
            api_fetch=None, now: datetime | None = None) -> dict:
    require(operator_confirmed_reinsert is True,
            "OPERATOR_CONFIRMATION_REQUIRED: safely eject and reconnect "
            "the SD card manually before recheck")
    anchored_file(baseline, sd_root, bundle_path)
    before = read_baseline(baseline, expected_baseline_sha256)
    require(before["run_id"] == run_id and
            before["artifact_id"] == artifact_id,
            "RECHECK_RUN_ID_CHANGED")
    after_gate = live_check(bundle_path, archive, sd_root, plan,
                            run_id, artifact_id, api_fetch=api_fetch, now=now)
    after = observed_values(after_gate, bundle_path, plan)
    for key in IDENTITY_KEYS:
        require(before[key] == after[key],
                f"POST_REINSERT_IDENTITY_CHANGED: {key}")
    require(after_gate["checked_at_utc"] >= before["checked_at_utc"],
            "POST_REINSERT_CHECK_TIME_PREDATES_BASELINE")
    require(hashlib.sha256(baseline.read_bytes()).hexdigest() ==
            expected_baseline_sha256,
            "BASELINE_CHANGED_DURING_RECHECK")
    return {
        "schema": "vh-switch-audio-sd-reinsert-review/v1",
        "result": "POST_REINSERT_LOCAL_NRO_BYTES_MATCH",
        "hardware_status": bundle.HARDWARE_STATUS,
        "baseline_sha256": expected_baseline_sha256,
        "build_git_sha_confirmed_at_recheck": after["build_git_sha"],
        "run_id": run_id,
        "artifact_id": artifact_id,
        "run_attempt": after["run_attempt"],
        "installed_nro_sha256": after["installed_nro_sha256"],
        "installed_nro_size": after["installed_nro_size"],
        "checked_at_utc": after_gate["checked_at_utc"],
        "operator_reinsert_claim": "SELF_REPORTED_NOT_INDEPENDENTLY_ATTESTED",
        "physical_sd_medium": "NOT_ATTESTED",
        "physical_nro_execution": "HARDWARE NOT TESTED",
        "audible_music": "NOT_TESTED",
        "sd_power_loss_durability": "NOT_TESTED",
        "limitations": (
            "The software cannot observe safe ejection, physical reinsertion, "
            "FAT flush persistence, or true SD media. The operator confirmation "
            "is unverified; two matching reads are not hardware acceptance."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    actions = p.add_subparsers(dest="action", required=True)
    for name in ("record", "recheck"):
        x = actions.add_parser(name)
        x.add_argument("bundle", type=Path)
        x.add_argument("--artifact-zip", required=True, type=Path)
        x.add_argument("--sd-root", required=True, type=Path)
        x.add_argument("--transfer-plan", required=True, type=Path)
        x.add_argument("--run-id", required=True, type=int)
        x.add_argument("--artifact-id", required=True, type=int)
        if name == "record":
            x.add_argument("--output", required=True, type=Path)
        else:
            x.add_argument("--baseline", required=True, type=Path)
            x.add_argument("--expected-baseline-sha256", required=True)
            x.add_argument("--operator-confirmed-reinsert", action="store_true")
    args = p.parse_args(argv)
    try:
        kwargs = dict(bundle_path=args.bundle, archive=args.artifact_zip,
                      sd_root=args.sd_root, plan=args.transfer_plan,
                      run_id=args.run_id, artifact_id=args.artifact_id)
        if args.action == "record":
            outcome = record(**kwargs, output=args.output)
        else:
            outcome = recheck(
                **kwargs, baseline=args.baseline,
                expected_baseline_sha256=args.expected_baseline_sha256,
                operator_confirmed_reinsert=args.operator_confirmed_reinsert)
    except (ReinsertError, launch.GateError,
            provenance.ProvenanceError, sd_transfer.TransferError,
            ci_receipt.ReceiptError, bundle.BundleError,
            audio.LogFormatError, OSError, ValueError, KeyError,
            TypeError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
