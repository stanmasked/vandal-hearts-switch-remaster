#!/usr/bin/env python3
"""Stage 235: bind a pinned H05 before/after review to a stage-233 CSV bundle.

Offline and read-only. Verify both independently pinned host JSON files, the
unchanged original source manifest and transfer plan, and every byte of the
captured bundle. H05 old/new CSV must occur in that order with identical
digests; 'new' must not have been present in the pre-run SD inventory.

No digital signature, attested second Switch launch, physical SD identity,
audible sound or independent operator testimony is established.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_switch_audio_log as audio
import capture_switch_audio_sd_csv as capture
import verify_switch_audio_bundle as bundle
import verify_switch_audio_h05_csv_persistence as h05
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-h05-capture-binding/v1"
REVIEW_SCHEMA = "vh-switch-audio-h05-review/v1"
MAX_REVIEW = 32 * 1024
REVIEW_FIELDS = {
    "schema", "result", "hardware_status", "baseline_sha256",
    "git_sha_self_reported", "nro_sha256", "old_csv_name", "old_csv_sha256",
    "new_csv_name", "new_csv_sha256",
    "additional_new_csv_names_unattributed", "existing_csv_retained_count",
    "operator_claim", "physical_second_run_attested",
    "audio_attested", "manual_signoff", "limitations",
}


class BindingError(ValueError):
    """Pinned H05 report or exported CSV evidence is inconsistent."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise BindingError(why)


def pinned_file(path: Path, sha: str, max_bytes: int, label: str) -> bytes:
    require(isinstance(sha, str) and
            bundle.SHA256_RE.fullmatch(sha) is not None,
            f"invalid independently pinned {label} SHA-256")
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= max_bytes,
            f"missing, symlinked, empty or oversized {label}")
    data = path.read_bytes()
    require(len(data) <= max_bytes and h05.sha256(data) == sha,
            f"{label.upper()}_SHA256_MISMATCH")
    return data


def read_review(path: Path, independent_sha: str) -> dict:
    raw = pinned_file(path, independent_sha, MAX_REVIEW, "review")
    try:
        review = json.loads(raw.decode("utf-8"),
                            object_pairs_hook=bundle.unique_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise BindingError(f"invalid H05 review JSON: {exc}") from exc
    require(isinstance(review, dict) and set(review) == REVIEW_FIELDS and
            review["schema"] == REVIEW_SCHEMA and
            review["result"] == "H05_FILE_PERSISTENCE_CONSISTENT_FOR_MANUAL_REVIEW" and
            review["hardware_status"] == bundle.HARDWARE_STATUS and
            review["operator_claim"] == "SECOND_RUN_SELF_REPORTED_NOT_ATTESTED" and
            review["physical_second_run_attested"] is False and
            review["audio_attested"] is False and
            review["manual_signoff"] == "REQUIRED_NOT_AUTOMATED",
            "H05 review is malformed or falsely claims hardware PASS")
    require(isinstance(review["limitations"], str) and
            1 <= len(review["limitations"]) <= 2048,
            "H05 limitations are missing or too large")
    for key in ("baseline_sha256", "nro_sha256",
                "old_csv_sha256", "new_csv_sha256"):
        require(isinstance(review[key], str) and
                bundle.SHA256_RE.fullmatch(review[key]) is not None,
                f"invalid H05 review {key}")
    require(isinstance(review["git_sha_self_reported"], str) and
            bundle.GIT_SHA_RE.fullmatch(review["git_sha_self_reported"]) is not None,
            "invalid H05 review Git SHA")
    for key in ("old_csv_name", "new_csv_name"):
        require(isinstance(review[key], str) and
                capture.CSV_NAME.fullmatch(review[key]) is not None,
                f"invalid H05 review {key}")
    require(review["old_csv_name"] != review["new_csv_name"],
            "H05 review duplicates old and new CSV")
    require(type(review["existing_csv_retained_count"]) is int and
            1 <= review["existing_csv_retained_count"] <= h05.MAX_EXISTING,
            "invalid H05 preexisting CSV count")
    more = review["additional_new_csv_names_unattributed"]
    require(isinstance(more, list) and
            len(more) <= h05.MAX_EXISTING and
            len(set(map(str, more))) == len(more) and
            all(isinstance(name, str) and
                capture.CSV_NAME.fullmatch(name) is not None and
                name not in (review["old_csv_name"], review["new_csv_name"])
                for name in more), "invalid additional H05 CSV names")
    return review


def read_source(source: Path, plan: Path, baseline: dict) -> dict:
    require(source.is_dir() and not source.is_symlink(),
            "source bundle missing or symlinked")
    require(plan.is_file() and not plan.is_symlink(),
            "source SD transfer plan missing or symlinked")
    require(bundle.digest_file(source / bundle.MANIFEST_NAME)[1] ==
            baseline["source_manifest_sha256"],
            "PINNED_SOURCE_MANIFEST_CHANGED")
    require(bundle.digest_file(plan)[1] == baseline["transfer_plan_sha256"],
            "PINNED_SD_TRANSFER_PLAN_CHANGED")
    report = bundle.inspect(source)
    require(report["integrity"] == "VERIFIED",
            "original source bundle integrity is not verified")
    manifest = bundle.read_manifest(source)
    plan_record = transfer.read_plan(plan)
    require(plan_record["source_manifest_sha256"] ==
            baseline["source_manifest_sha256"] and
            plan_record["git_sha"] == baseline["git_sha_self_reported"] and
            plan_record["source_nro"] == manifest["nro"] and
            manifest["git_sha"] == baseline["git_sha_self_reported"] and
            manifest["nro"]["sha256"] == baseline["nro_sha256"] and
            manifest["nro"]["size"] == baseline["nro_size"],
            "SOURCE_PLAN_NRO_DISAGREES_WITH_H05_BASELINE")
    require(manifest["ci_run_url"].startswith(
        "https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/"),
        "source bundle lacks project GitHub run URL")
    return manifest


def examine(source_bundle: Path, transfer_plan: Path, captured: Path,
            baseline_path: Path, baseline_sha256: str,
            review_path: Path, review_sha256: str) -> dict:
    # Neither pinned host report should be embedded in the mutable evidence set.
    root = captured.resolve()
    source = source_bundle.resolve()
    require(root != source and captured.is_dir() and not captured.is_symlink(),
            "source and captured bundle must be separate real directories")
    require(not baseline_path.resolve().is_relative_to(root) and
            not review_path.resolve().is_relative_to(root) and
            not baseline_path.resolve().is_relative_to(source) and
            not review_path.resolve().is_relative_to(source),
            "pinned H05 reports must remain outside the evidence bundles")
    require(baseline_path.resolve() != review_path.resolve(),
            "H05 baseline and review must be separate files")
    baseline = h05.read_baseline(baseline_path, baseline_sha256)
    review = read_review(review_path, review_sha256)
    require(review["baseline_sha256"] == baseline_sha256 and
            review["git_sha_self_reported"] ==
            baseline["git_sha_self_reported"] and
            review["nro_sha256"] == baseline["nro_sha256"] and
            review["old_csv_name"] == baseline["old_csv_name"] and
            review["old_csv_sha256"] == baseline["old_csv_sha256"] and
            review["existing_csv_retained_count"] ==
            len(baseline["existing_csv"]),
            "H05_BEFORE_AFTER_IDENTITY_MISMATCH")
    prior = {x["name"]: x for x in baseline["existing_csv"]}
    require(review["new_csv_name"] not in prior,
            "H05_NEW_CSV_EXISTED_BEFORE_CLAIMED_RUN")
    require(all(review["new_csv_sha256"] != file["sha256"]
                for file in prior.values()),
            "H05_NEW_CSV_REUSED_OLD_BYTES")
    require(not set(review["additional_new_csv_names_unattributed"]) & set(prior),
            "H05_UNATTRIBUTED_CSV_ALREADY_IN_BASELINE")

    original = read_source(source_bundle, transfer_plan, baseline)
    verified = bundle.inspect(captured)
    require(verified["integrity"] == "VERIFIED",
            "captured bundle is not byte-verified")
    manifest = bundle.read_manifest(captured)
    require(manifest["git_sha"] == original["git_sha"] and
            manifest["ci_run_url"] == original["ci_run_url"] and
            manifest["nro"]["sha256"] == baseline["nro_sha256"] and
            manifest["nro"]["size"] == baseline["nro_size"],
            "H05_CAPTURED_BUILD_IDENTITY_MISMATCH")
    require(manifest["nro"]["path"] == capture.NRO_PATH,
            "H05_CAPTURED_NRO_PATH_MISMATCH")
    found: dict[str, dict] = {}
    for index, member in enumerate(manifest["sessions"], 1):
        relative = member["path"]
        require(isinstance(relative, str) and
                relative.startswith(f"session-{index:02d}/"),
                "H05_CAPTURED_SESSION_LAYOUT_MISMATCH")
        name = relative.rsplit("/", 1)[-1]
        require(capture.CSV_NAME.fullmatch(name) is not None and
                relative == capture.layout(index, name) and
                name not in found,
                "H05_CAPTURED_DUPLICATE_OR_UNEXPECTED_CSV")
        path = bundle.safe_member(captured, relative, ".csv")
        rows = audio.load_csv(path)
        require(rows[-1]["event"] == "EXIT",
                f"CAPTURED_CSV_INCOMPLETE_EXIT: {name}")
        found[name] = {**member, "index": index}

    old_name, new_name = review["old_csv_name"], review["new_csv_name"]
    require(old_name in found and new_name in found,
            "H05_OLD_OR_NEW_CSV_MISSING_FROM_CAPTURE")
    require(found[old_name]["index"] < found[new_name]["index"],
            "H05_CAPTURED_SESSION_ORDER_WRONG")
    require(found[old_name]["sha256"] == baseline["old_csv_sha256"] and
            found[old_name]["size"] == baseline["old_csv_size"] and
            found[new_name]["sha256"] == review["new_csv_sha256"],
            "H05_CAPTURED_CSV_SHA256_MISMATCH")
    for name, member in found.items():
        if name in prior:
            require(member["sha256"] == prior[name]["sha256"] and
                    member["size"] == prior[name]["size"],
                    f"H05_CAPTURED_PREEXISTING_CSV_CHANGED: {name}")
        else:
            require(name == new_name or
                    name in review["additional_new_csv_names_unattributed"],
                    f"H05_CAPTURED_NEW_CSV_NOT_PRESENT_IN_REVIEW: {name}")
    result = {
        "schema": SCHEMA,
        "result": "H05_CAPTURED_EVIDENCE_CONSISTENT_FOR_MANUAL_REVIEW",
        "hardware_status": bundle.HARDWARE_STATUS,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "baseline_sha256": baseline_sha256,
        "review_sha256": review_sha256,
        "captured_manifest_sha256": bundle.digest_file(
            captured / bundle.MANIFEST_NAME)[1],
        "git_sha_self_reported": baseline["git_sha_self_reported"],
        "nro_sha256": baseline["nro_sha256"],
        "old_csv": {
            "name": old_name,
            "captured_path": found[old_name]["path"],
            "sha256": found[old_name]["sha256"],
            "size": found[old_name]["size"],
        },
        "new_csv": {
            "name": new_name,
            "captured_path": found[new_name]["path"],
            "sha256": found[new_name]["sha256"],
            "size": found[new_name]["size"],
        },
        "captured_session_count": len(found),
        "unattributed_additional_captured_csv": sorted(
            name for name in found if name != new_name and name not in prior),
        "second_run_attested": False,
        "audible_audio_attested": False,
        "physical_sd_attested": False,
        "limitations": (
            "Pinned, unsigned H05 reports and a valid CSV bundle confirm only "
            "consistent file hashes, selected capture order and self-reported "
            "SD inventory history. No real Nintendo Switch launch, separate "
            "physical session, audio quality or device durability is attested."
        ),
    }
    # Detect changes during validation to the independently pinned reports.
    require(h05.sha256(baseline_path.read_bytes()) == baseline_sha256 and
            h05.sha256(review_path.read_bytes()) == review_sha256,
            "H05_PINNED_REPORT_CHANGED_DURING_VALIDATION")
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-bundle", required=True, type=Path)
    p.add_argument("--transfer-plan", required=True, type=Path)
    p.add_argument("--captured", required=True, type=Path)
    p.add_argument("--h05-baseline", required=True, type=Path)
    p.add_argument("--baseline-sha256", required=True)
    p.add_argument("--h05-review", required=True, type=Path)
    p.add_argument("--review-sha256", required=True)
    args = p.parse_args(argv)
    try:
        report = examine(args.source_bundle, args.transfer_plan,
                         args.captured, args.h05_baseline,
                         args.baseline_sha256, args.h05_review,
                         args.review_sha256)
    except (BindingError, h05.PersistenceError, capture.CaptureError,
            transfer.TransferError, bundle.BundleError, audio.LogFormatError,
            OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
