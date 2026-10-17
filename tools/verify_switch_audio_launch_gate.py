#!/usr/bin/env python3
"""Stage 230: read-only final host gate before a manual Switch audio test.

Require a current, successful GitHub Actions run, an exact artifact ZIP with
the stage-229 CI build receipt, a separately planned source NRO and an exact
manually installed SD-root NRO. This ties three file identities to one build.

This does NOT install software, establish the existence of a removable SD,
execute on hardware, listen to audio, or approve a device. Repeat right
before an actual Switch launch; GitHub branch HEAD can move immediately.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

import analyze_switch_audio_log as audio
import switch_audio_ci_build_receipt as ci_receipt
import verify_switch_audio_build_provenance as provenance
import verify_switch_audio_bundle as bundle
import verify_switch_audio_live_preflight as preflight
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-launch-gate/v1"


class GateError(ValueError):
    """No go: at least one independent binary/build identity was not verified."""


def require(condition: bool, why: str) -> None:
    if not condition:
        raise GateError(why)


def evaluate(bundle_path: Path, archive: Path, sd_root: Path, plan: Path,
             run_id: int, artifact_id: int, *,
             api_fetch=None, now: datetime | None = None,
             max_age_days: int = preflight.MAX_AGE_DAYS) -> dict:
    """Live mode fetches official GitHub REST; tests inject local mock responses."""
    require(provenance.number(run_id) and provenance.number(artifact_id),
            "run ID and artifact ID must be positive integers")
    require(type(max_age_days) is int and 1 <= max_age_days <= 365,
            "max age must be 1..365 days")
    kwargs = {"max_age_days": max_age_days}
    if api_fetch is not None:
        kwargs["api_fetch"] = api_fetch
    if now is not None:
        kwargs["now"] = now
    live = preflight.evaluate(
        bundle_path, archive, run_id, artifact_id, **kwargs)
    require(live["result"] == "MATCHED_CURRENT_HEAD_AT_CHECK_TIME" and
            live["hardware_status"] == bundle.HARDWARE_STATUS,
            "live GitHub preflight did not confirm the exact current build")
    official = live["verified_archive"]
    require(official["ci_receipt_state"] == "VERIFIED_UNTRUSTED",
            "CI_BUILD_RECEIPT_REQUIRED: stage 230 rejects legacy NRO-only artifact")
    signed_by_ci = official["ci_receipt"]
    require(isinstance(signed_by_ci, dict) and
            signed_by_ci["run_id"] == run_id and
            signed_by_ci["git_sha"] == live["head_sha_at_check_time"] and
            signed_by_ci["head_branch"] == provenance.BRANCH,
            "CI_BUILD_RECEIPT_IDENTITY_MISMATCH")

    moved = transfer.verify(bundle_path, sd_root, plan)
    require(moved["result"] == "DESTINATION_BYTES_MATCH_PLANNED_NRO" and
            moved["hardware_status"] == bundle.HARDWARE_STATUS,
            "host SD-root file has not passed transfer validation")
    require(moved["source_git_sha_self_reported"] ==
            live["head_sha_at_check_time"],
            "SOURCE_COMMIT_DISAGREES_WITH_GITHUB_HEAD")
    require(moved["nro_sha256"] == official["nro_sha256"] ==
            signed_by_ci["nro"]["sha256"] and
            moved["nro_size"] == official["nro_size"] ==
            signed_by_ci["nro"]["size"],
            "INSTALLED_NRO_DOES_NOT_MATCH_GITHUB_ARTIFACT")

    manifest = bundle.read_manifest(bundle_path)
    require(manifest["nro"]["sha256"] == moved["nro_sha256"] and
            manifest["nro"]["size"] == moved["nro_size"],
            "SOURCE_MANIFEST_DISAGREES_WITH_VERIFIED_SD_BYTES")
    plan_data = transfer.read_plan(plan)
    require(plan_data["source_nro"] == manifest["nro"] and
            plan_data["git_sha"] == live["head_sha_at_check_time"],
            "STORED_TRANSFER_PLAN_DISAGREES_WITH_CURRENT_CI_BUILD")

    return {
        "schema": SCHEMA,
        "result": "READY_FOR_MANUAL_DEVICE_LAUNCH",
        "hardware_status": bundle.HARDWARE_STATUS,
        "git_sha_confirmed_by_github_at_check_time": live["head_sha_at_check_time"],
        "run_id": run_id,
        "artifact_id": artifact_id,
        "run_attempt": signed_by_ci["run_attempt"],
        "checked_at_utc": live["checked_at_utc"],
        "artifact_zip_sha256": official["archive_sha256"],
        "installed_nro_sha256": moved["nro_sha256"],
        "installed_nro_size": moved["nro_size"],
        "sd_destination_relative": moved["sd_destination"],
        "verified_layers": [
            "LIVE_GITHUB_RUN_ARTIFACT_AND_CURRENT_HEAD",
            "CI_RECEIPT_WITH_EXACT_RUN_AND_ATTEMPT",
            "SOURCE_NRO_SHA256_AND_MANIFEST",
            "PRECOPY_PLAN_AND_SEPARATELY_READ_SD_ROOT_NRO",
        ],
        "manual_copy_witnessed": False,
        "physical_sd_medium_attested": False,
        "physical_launch_attested": False,
        "audible_music_attested": False,
        "home_sleep_cycles_attested": False,
        "csv_diagnostics_attested": False,
        "manual_next_action": (
            "Physically launch this exact NRO on Nintendo Switch; confirm "
            "audible music, HOME, sleep, and 2 independent CSV sessions "
            "using the stage 219 operator protocol."
        ),
        "limitations": (
            "GitHub HTTPS state was read only at the recorded check time, "
            "and may change. Read-only SD-root fingerprinting does not "
            "prove that the path is removable media or the file actually "
            "executed on Nintendo Switch; no physical test was performed."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle", type=Path)
    p.add_argument("--artifact-zip", required=True, type=Path)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--artifact-id", type=int, required=True)
    p.add_argument("--sd-root", type=Path, required=True)
    p.add_argument("--transfer-plan", type=Path, required=True)
    p.add_argument("--max-run-age-days", type=int, default=preflight.MAX_AGE_DAYS)
    args = p.parse_args(argv)
    try:
        result = evaluate(
            args.bundle, args.artifact_zip, args.sd_root,
            args.transfer_plan, args.run_id, args.artifact_id,
            max_age_days=args.max_run_age_days)
    except (GateError, preflight.provenance.ProvenanceError,
            transfer.TransferError, ci_receipt.ReceiptError,
            bundle.BundleError, audio.LogFormatError,
            OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
