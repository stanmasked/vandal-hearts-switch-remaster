#!/usr/bin/env python3
"""Stage 224: independent cross-computer archive snapshots and byte-level diffs.

'snapshot' writes a small report after re-verifying the ZIP and its separately
provided SHA-256. 'compare' re-verifies BOTH ZIP files with their independently
recorded detached SHA-256 values, checks that each report matches recomputed
data, then records which source files or semantic review fields differ.

Neither a snapshot nor SHA-256 authenticates an operator or hardware. Code 0
means the operation completed, not that two builds match or Switch audio passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import analyze_switch_audio_log as audio
import archive_switch_audio_handoff as transfer
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-cross-host-snapshot/v1"
COMPARISON_SCHEMA = "vh-switch-audio-cross-host-comparison/v1"
MAX_SNAPSHOT = 128 * 1024
SNAPSHOT_KEYS = {
    "schema", "hardware_status", "archive_sha256", "archive_bytes",
    "git_sha_self_reported", "handoff_review", "member_inventory",
    "scenario_statuses", "retest_scenarios", "session_claims",
    "manual_signoff",
}


class ComparisonError(ValueError):
    """Invalid independent report, mismatched ZIP, or unsafe output path."""


def require(ok: bool, detail: str) -> None:
    if not ok:
        raise ComparisonError(detail)


def verified_snapshot(zip_path: Path, independent_sha256: str) -> dict:
    checked = transfer.verify_archive(zip_path, independent_sha256)
    require(checked["result"] == "ARCHIVE_BYTES_AND_EVIDENCE_REVERIFIED" and
            checked["hardware_status"] == bundle.HARDWARE_STATUS,
            "ZIP has not passed strict source-evidence review")
    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "archive_sha256": checked["archive_sha256"],
        "archive_bytes": checked["archive_bytes"],
        "git_sha_self_reported": checked["git_sha_self_reported"],
        "handoff_review": checked["handoff_review"],
        "member_inventory": checked["member_inventory"],
        "scenario_statuses": checked["scenario_statuses"],
        "retest_scenarios": checked["retest_scenarios"],
        "session_claims": checked["session_claims"],
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def read_snapshot(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(),
            "snapshot missing or symbolic link")
    require(path.stat().st_size <= MAX_SNAPSHOT, "snapshot exceeds size limit")
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"invalid snapshot JSON: {exc}") from exc
    require(isinstance(data, dict) and set(data) == SNAPSHOT_KEYS and
            data.get("schema") == SCHEMA and
            data.get("hardware_status") == bundle.HARDWARE_STATUS and
            data.get("manual_signoff") == "REQUIRED_NOT_AUTOMATED",
            "unrecognized or forged snapshot schema/hardware status")
    return data


def verify_report(path: Path, zip_path: Path, sha256: str) -> dict:
    """Recompute every field from actual original ZIP; reject edited reports."""
    snapshot = read_snapshot(path)
    expected = verified_snapshot(zip_path, sha256)
    require(snapshot == expected,
            "SAVED_REPORT_MISMATCH: snapshot disagrees with reverified ZIP contents")
    return expected


def save_snapshot(zip_path: Path, sha256: str, output: Path) -> dict:
    require(output.parent.is_dir(), "snapshot output directory missing")
    require(not output.exists() and not output.is_symlink(),
            "snapshot already exists; refusing overwrite")
    require(output.absolute().resolve() != zip_path.absolute().resolve(),
            "snapshot output cannot overwrite input archive")
    snapshot = verified_snapshot(zip_path, sha256)
    body = (json.dumps(snapshot, indent=2, sort_keys=True,
                       ensure_ascii=False) + "\n").encode("utf-8")
    require(len(body) <= MAX_SNAPSHOT, "verified snapshot too large")
    with output.open("xb") as stream:
        stream.write(body)
    return {
        "result": "INDEPENDENT_ZIP_SNAPSHOT_CREATED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "archive_sha256": snapshot["archive_sha256"],
        "member_count": len(snapshot["member_inventory"]),
        "snapshot_path": str(output),
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def compare(source: dict, destination: dict) -> dict:
    """Compare only canonical snapshots that were revalidated by caller."""
    require(source["schema"] == destination["schema"] == SCHEMA and
            source["hardware_status"] == destination["hardware_status"] ==
            bundle.HARDWARE_STATUS, "unsupported archive snapshot schema")
    differences = []

    def add(category: str, code: str, name: str, before: object, after: object) -> None:
        differences.append({
            "category": category,
            "code": code,
            "subject": name,
            "source": before,
            "received": after,
        })

    before_files = {x["name"]: x for x in source["member_inventory"]}
    after_files = {x["name"]: x for x in destination["member_inventory"]}
    for name in sorted(set(before_files) | set(after_files)):
        if name not in after_files:
            add("EVIDENCE", "EVIDENCE_FILE_MISSING", name, before_files[name], None)
        elif name not in before_files:
            add("EVIDENCE", "NEW_EVIDENCE_FILE", name, None, after_files[name])
        elif before_files[name] != after_files[name]:
            add("EVIDENCE", "EVIDENCE_BYTES_DIFFER", name,
                before_files[name], after_files[name])

    if source["git_sha_self_reported"] != destination["git_sha_self_reported"]:
        add("IDENTITY", "BUILD_SHA_CHANGED", "git_sha_self_reported",
            source["git_sha_self_reported"], destination["git_sha_self_reported"])

    for field in ("handoff_review", "scenario_statuses", "retest_scenarios",
                  "session_claims", "manual_signoff"):
        if source[field] != destination[field]:
            add("REVIEW", "REVIEW_FIELD_CHANGED", field, source[field],
                destination[field])

    if not differences and source["archive_sha256"] != destination["archive_sha256"]:
        add("CONTAINER", "ZIP_CONTAINER_REPACKAGED", "archive_sha256",
            source["archive_sha256"], destination["archive_sha256"])

    if any(d["category"] in ("EVIDENCE", "IDENTITY") for d in differences):
        outcome = "EVIDENCE_CHANGED"
    elif any(d["category"] == "REVIEW" for d in differences):
        outcome = "REVIEW_CHANGED"
    elif differences:
        outcome = "CONTAINER_ONLY_DIFFERENCE"
    else:
        outcome = "EXACT_MATCH"
    return {
        "schema": COMPARISON_SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "result": outcome,
        "source_archive_sha256": source["archive_sha256"],
        "received_archive_sha256": destination["archive_sha256"],
        "source_review": source["handoff_review"],
        "received_review": destination["handoff_review"],
        "source_git_sha_self_reported": source["git_sha_self_reported"],
        "received_git_sha_self_reported": destination["git_sha_self_reported"],
        "differences": differences,
        "difference_count": len(differences),
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "limitations": (
            "Both ZIPs and reported snapshots were independently checked against "
            "their supplied detached SHA-256 anchors. Separate anchors must be "
            "obtained from a trusted out-of-band record to detect substitution. "
            "An equality report proves byte consistency only, not the physical "
            "origin of sessions, audible sound, SD durability, or hardware PASS."
        ),
    }


def markdown(report: dict) -> str:
    def safe(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
    lines = [
        "# Vandal Hearts Remake — Stage 224 Cross-Host Evidence Comparison",
        "",
        "**HARDWARE NOT TESTED — machine review is not hardware acceptance.**",
        "",
        f"Result: **{safe(report['result'])}**",
        f"Source ZIP SHA-256: \`{safe(report['source_archive_sha256'])}\`",
        f"Received ZIP SHA-256: \`{safe(report['received_archive_sha256'])}\`",
        "",
        "| Category | Difference | Subject |",
        "| --- | --- | --- |",
    ]
    if not report["differences"]:
        lines.append("| — | No differences | — |")
    else:
        for diff in report["differences"]:
            lines.append("| " + " | ".join(
                safe(diff[key]) for key in ("category", "code", "subject")) + " |")
    lines.extend([
        "", "## Interpretation", "",
        "- File changes require comparing the original evidence; never silently replace the source.",
        "- A container-only change means the internal file fingerprints remained equal.",
        "- Detached hashes and operator statements do not provide signed physical provenance.",
        "- No comparison result indicates physical Nintendo Switch hardware PASS.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("snapshot", help="save independently verified ZIP inventory")
    create.add_argument("archive", type=Path)
    create.add_argument("--expected-sha256", required=True)
    create.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("compare", help="compare two revalidated host snapshots")
    for role in ("source", "received"):
        check.add_argument(f"--{role}-report", type=Path, required=True)
        check.add_argument(f"--{role}-archive", type=Path, required=True)
        check.add_argument(f"--{role}-sha256", required=True)
    check.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = save_snapshot(args.archive, args.expected_sha256, args.output)
        else:
            before = verify_report(args.source_report, args.source_archive,
                                   args.source_sha256)
            after = verify_report(args.received_report, args.received_archive,
                                  args.received_sha256)
            result = compare(before, after)
    except (ComparisonError, transfer.ArchiveError, handoff.HandoffError,
            operator.OperatorError, bundle.BundleError, audio.LogFormatError,
            OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    if args.command == "compare" and args.format == "markdown":
        print(markdown(result))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
