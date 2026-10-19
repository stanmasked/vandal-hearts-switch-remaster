#!/usr/bin/env python3
"""Stage349: compare two SHA-pinned original NeXium guest PCM lease receipts.

These are guest software ownership counters, not device queue depth, DAC
delivery, audible audio, or tests on a physical Nintendo Switch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_guest_lease_reconciliation_stage348 import (
    SCHEMA as ORIGINAL_SCHEMA,
    VERIFIED as ORIGINAL_VERDICT,
    ExitTimelineError,
    audit_source,
)

SCHEMA = "vh-stage349-two-original-guest-lease-cohorts/v1"
VERDICT = "TWO_DISTINCT_ORIGINAL_GUEST_SOFTWARE_LEASE_SOURCES_RECONCILED"
COUNTS = (
    "lease_pages_acquired",
    "lease_pages_released",
    "abandoned_sessions",
    "busy_begin_rejections",
    "mismatched_releases",
    "accepted_pages_submitted",
    "submit_failures",
)
FALSE_FLAGS = (
    "playback_at_DAC_or_speaker_verified",
    "original_PS1_soundtrack_verified",
    "physical_Nintendo_Switch_audio_tested",
)
TRUE_FLAGS = (
    "original_guest_software_lease_source_observed",
    "original_guest_software_lease_bytes_preserved",
    "only_software_owner_counters_checked",
)


def read_original(csv_path: Path, receipt_path: Path, sha_pin: str) -> dict:
    """Recheck original preserved bytes AND independent Stage348 receipt."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha_pin):
        raise ValueError("original CSV SHA pin must be a lowercase SHA-256")
    for path in (csv_path, receipt_path):
        if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
            raise ValueError("original source/receipt missing or symlinked")
    raw = csv_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != sha_pin:
        raise ValueError("original guest CSV SHA-256 differs from pin")
    source = audit_source(raw)  # strict original eight-row, balance, saturation checks
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("original receipt is not a JSON object")
    if (receipt.get("schema") != ORIGINAL_SCHEMA
        or receipt.get("result") != ORIGINAL_VERDICT
        or receipt.get("original_guest_software_lease_csv_sha256") != sha):
        raise ValueError("original Stage348 source receipt does not match")
    for name in COUNTS:
        if type(receipt.get(name)) is not int or receipt[name] != source[name]:
            raise ValueError("original Stage348 receipt count differs from CSV: " + name)
    for name in TRUE_FLAGS:
        if receipt.get(name) is not True or source.get(name) is not True:
            raise ValueError("missing source-only true guard: " + name)
    for name in FALSE_FLAGS:
        if receipt.get(name) is not False or source.get(name) is not False:
            raise ValueError("incorrect hardware/sound scope: " + name)
    return {"sha256": sha, **{name: source[name] for name in COUNTS}}


def compare_originals(a: dict, b: dict, first_run: int, second_run: int) -> dict:
    if first_run <= 0 or second_run <= 0 or first_run == second_run:
        raise ValueError("require two distinct valid source workflow run IDs")
    if a["sha256"] == b["sha256"]:
        raise ValueError("duplicate original guest CSV cannot form two cohorts")
    if a["lease_pages_acquired"] - a["lease_pages_released"] != a["abandoned_sessions"]:
        raise ValueError("first guest ownership source unbalanced")
    if b["lease_pages_acquired"] - b["lease_pages_released"] != b["abandoned_sessions"]:
        raise ValueError("second guest ownership source unbalanced")
    return {
        "schema": SCHEMA,
        "result": VERDICT,
        "original_source_run_ids": [first_run, second_run],
        "first_original": a,
        "second_original": b,
        "second_minus_first": {name: b[name] - a[name] for name in COUNTS},
        "two_distinct_SHA_pinned_original_guest_CSV_sources": True,
        "each_original_receipt_independently_rechecked": True,
        "guest_software_ownership_balanced_in_both": True,
        "same_audio_hardware_or_device_queue_state_proven": False,
        "physical_Nintendo_Switch_audio_tested": False,
        "DAC_or_speaker_playback_verified": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-csv", type=Path, required=True)
    p.add_argument("--first-receipt", type=Path, required=True)
    p.add_argument("--first-sha256", required=True)
    p.add_argument("--first-run-id", type=int, required=True)
    p.add_argument("--second-csv", type=Path, required=True)
    p.add_argument("--second-receipt", type=Path, required=True)
    p.add_argument("--second-sha256", required=True)
    p.add_argument("--second-run-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("refusing to overwrite evidence report")
        a = read_original(args.first_csv, args.first_receipt, args.first_sha256)
        b = read_original(args.second_csv, args.second_receipt, args.second_sha256)
        doc = compare_originals(a, b, args.first_run_id, args.second_run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(doc, out, sort_keys=True, indent=2)
            out.write("\n")
        print(json.dumps({
            "result": doc["result"],
            "first_acquired": a["lease_pages_acquired"],
            "first_released": a["lease_pages_released"],
            "first_abandoned": a["abandoned_sessions"],
            "second_acquired": b["lease_pages_acquired"],
            "second_released": b["lease_pages_released"],
            "second_abandoned": b["abandoned_sessions"],
            "physical_Nintendo_Switch_audio_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ExitTimelineError) as exc:
        print(json.dumps({
            "result": "TWO_ORIGINAL_GUEST_LEASE_SOURCES_NOT_RECONCILED",
            "error_kind": type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
