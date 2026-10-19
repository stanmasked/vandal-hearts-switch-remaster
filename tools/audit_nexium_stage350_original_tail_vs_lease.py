#!/usr/bin/env python3
"""Stage350: source-pinned Stage313 exit-taper vs Stage348 PCM lease cohort audit.

Read both independently archived ORIGINAL guest CSVs and their already-produced
source receipts. Compare software observations only; no causal DAC/audio claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_guest_last_buffer_return import (
    SCHEMA as TAIL_SCHEMA,
    COMPLETE as TAIL_VERIFIED,
    FIELDS as TAIL_FIELDS,
)
from compare_nexium_stage349_original_lease_cohorts import read_original

SCHEMA = "vh-stage350-original-guest-tail-versus-software-lease/v1"
VERIFIED = "TWO_ORIGINAL_GUEST_EXIT_TAIL_AND_LEASE_SOURCES_CROSS_AUDITED"
PRESERVED = "ORIGINAL_GUEST_LAST_AUDOUT_SOURCE_PRESERVED_AND_REAUDITED"
MAX64 = 2**64 - 1


def safe_file(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError("original source/receipt missing or symlinked")


def read_tail_original(
    csv_path: Path, stage313_path: Path, stage314_path: Path, sha_pin: str
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", sha_pin):
        raise ValueError("original Stage314 CSV requires lowercase SHA-256")
    for path in (csv_path, stage313_path, stage314_path):
        safe_file(path)
    raw = csv_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != sha_pin:
        raise ValueError("original guest last-page/tail bytes differ from SHA pin")
    if (len(raw) > 1024 or b"\r" in raw or b"\x00" in raw
            or not raw.startswith(b"event,value\n") or not raw.endswith(b"\n")):
        raise ValueError("noncanonical original Stage313 source")
    rows = raw[len(b"event,value\n"):].splitlines(keepends=True)
    if len(rows) != len(TAIL_FIELDS):
        raise ValueError("original Stage313 source row count invalid")
    values = {}
    for label, row in zip(TAIL_FIELDS, rows):
        prefix = (label + ",").encode("ascii")
        if not row.startswith(prefix) or row.count(b",") != 1 or not row.endswith(b"\n"):
            raise ValueError("original Stage313 source row order/shape invalid")
        field = row[len(prefix):-1]
        if (not field or not field.isascii() or not field.isdigit()
                or (len(field) > 1 and field.startswith(b"0"))):
            raise ValueError("noncanonical original last page numeric value")
        value = int(field)
        if value > MAX64:
            raise ValueError("Stage313 software counter overflow")
        values[label] = value
    if (values["page_return_count"] == 0
            or not 0 < values["last_page_frames"] <= 4096
            or not values["last_page_return_guest_ns"]
            or (values["tail_attempt_guest_ns"]
                and values["tail_attempt_guest_ns"] <= values["last_page_return_guest_ns"])
            or (values["tail_success_return_guest_ns"]
                and (not values["tail_attempt_guest_ns"]
                     or values["tail_success_return_guest_ns"]
                        < values["tail_attempt_guest_ns"]))):
        raise ValueError("original source return/tail chronology incoherent")
    s313 = json.loads(stage313_path.read_text(encoding="utf-8"))
    s314 = json.loads(stage314_path.read_text(encoding="utf-8"))
    if not isinstance(s313, dict) or not isinstance(s314, dict):
        raise ValueError("Stage313/314 receipts must be objects")
    if (s313.get("schema") != TAIL_SCHEMA
        or s313.get("result") != TAIL_VERIFIED
        or s313.get("original_guest_page_witness_sha256") != sha
        or s313.get("original_guest_page_witness_observed") is not True
        or s314.get("result") != PRESERVED
        or s314.get("original_guest_output_csv_sha256") != sha
        or s314.get("original_guest_output_csv_preserved") is not True
        or s314.get("original_guest_source_bytes_reaudited") is not True
        or s314.get("source_stage313_reproduced") is not True):
        raise ValueError("Stage313/314 original source receipts mismatch")
    for name in ("page_return_count", "last_page_frames", "last_page_return_guest_ns",
                 "tail_attempt_guest_ns", "tail_success_return_guest_ns"):
        observed = values[name]
        expected = s313.get(name)
        if observed == 0 and name.endswith("_guest_ns"):
            if expected is not None:
                raise ValueError("Stage313 receipt zero-clock representation mismatch")
        elif type(expected) is not int or expected != observed:
            raise ValueError("Stage313 receipt value differs from original guest CSV: " + name)
    tail_attempted = values["tail_attempt_guest_ns"] > 0
    tail_returned = values["tail_success_return_guest_ns"] > 0
    if (s313.get("tail_bounded_attempt_observed") is not tail_attempted
        or s313.get("tail_release_confirmed") is not tail_returned
        or s313.get("last_page_return_is_not_DAC_or_speaker_output") is not True
        or s313.get("normal_exit_taper_is_not_PS1_SPU_rendered_music") is not True
        or s313.get("hardware_Nintendo_Switch_audio_tested") is not False
        or s313.get("audible_dropout_verified") is not False
        or s314.get("physical_Nintendo_Switch_audio_tested") is not False
        or s314.get("audout_buffer_release_not_speaker_playback") is not True):
        raise ValueError("Stage313/314 source-only scope altered")
    return {
        "original_tail_source_sha256": sha,
        "last_normal_page_return_count": values["page_return_count"],
        "bounded_exit_tail_attempted": tail_attempted,
        "bounded_exit_tail_return_confirmed": tail_returned,
    }


def read_pair(lease_csv: Path, lease_receipt: Path, lease_sha: str,
              tail_csv: Path, stage313: Path, stage314: Path, tail_sha: str) -> dict:
    lease = read_original(lease_csv, lease_receipt, lease_sha)
    tail = read_tail_original(tail_csv, stage313, stage314, tail_sha)
    return {
        "original_lease_sha256": lease["sha256"],
        "lease_pages_acquired": lease["lease_pages_acquired"],
        "lease_pages_released": lease["lease_pages_released"],
        "abandoned_sessions": lease["abandoned_sessions"],
        "accepted_pages_submitted": lease["accepted_pages_submitted"],
        **tail,
    }


def compare_pairs(first: dict, second: dict, first_run: int, second_run: int) -> dict:
    if (first_run <= 0 or second_run <= 0 or first_run == second_run
        or first["original_lease_sha256"] == second["original_lease_sha256"]
        or first["original_tail_source_sha256"] == second["original_tail_source_sha256"]):
        raise ValueError("two distinct paired original guest source runs are required")
    for cohort in (first, second):
        if (not cohort["bounded_exit_tail_attempted"]
            or cohort["lease_pages_acquired"] - cohort["lease_pages_released"]
                 != cohort["abandoned_sessions"]
            or cohort["accepted_pages_submitted"] > cohort["lease_pages_released"]):
            raise ValueError("original post-join PCM lease/tail source inconsistent")
    a_failed = not first["bounded_exit_tail_return_confirmed"]
    b_failed = not second["bounded_exit_tail_return_confirmed"]
    return {
        "schema": SCHEMA,
        "result": VERIFIED,
        "original_source_run_ids": [first_run, second_run],
        "first_original_source_pair": first,
        "second_original_source_pair": second,
        "first_unconfirmed_bounded_exit_tail": a_failed,
        "second_unconfirmed_bounded_exit_tail": b_failed,
        "unconfirmed_tail_and_abandoned_lease_coincide_in_both_sources": (
            first["abandoned_sessions"] == int(a_failed)
            and second["abandoned_sessions"] == int(b_failed)
        ),
        "stage313_314_348_original_sources_rechecked": True,
        "one_to_one_causal_attribution_proven": False,
        "audible_dropout_or_DAC_playback_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for cohort in ("first", "second"):
        for name in ("lease-csv", "lease-receipt", "tail-csv", "stage313",
                     "stage314"):
            p.add_argument(f"--{cohort}-{name}", type=Path, required=True)
        p.add_argument(f"--{cohort}-lease-sha256", required=True)
        p.add_argument(f"--{cohort}-tail-sha256", required=True)
        p.add_argument(f"--{cohort}-run-id", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("refuse to replace an existing original-source report")
        cohorts = []
        for cohort in ("first", "second"):
            get = lambda name: getattr(args, cohort + "_" + name)
            cohorts.append(read_pair(
                get("lease_csv"), get("lease_receipt"), get("lease_sha256"),
                get("tail_csv"), get("stage313"), get("stage314"), get("tail_sha256")))
        doc = compare_pairs(cohorts[0], cohorts[1],
                            args.first_run_id, args.second_run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(doc, out, sort_keys=True, indent=2)
            out.write("\n")
        print(json.dumps({
            "result": doc["result"],
            "both_original_source_pairs_verified": True,
            "unconfirmed_tails_coincide_with_abandonment":
                doc["unconfirmed_tail_and_abandoned_lease_coincide_in_both_sources"],
            "one_to_one_causal_attribution_proven": False,
            "physical_Nintendo_Switch_audio_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({
            "result": "STAGE350_ORIGINAL_GUEST_SOURCE_PAIR_NOT_VERIFIED",
            "error_kind": type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
