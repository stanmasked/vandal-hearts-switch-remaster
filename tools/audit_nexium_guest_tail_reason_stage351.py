#!/usr/bin/env python3
"""Stage351 strict guest-origin exit-tail reason source verifier.

Independent, new eight-row guest CSV; binds existing original Stage313 and
Stage348 receipts without changing either old source format. Software only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError

SOURCE = "audio-exit-tail-reason-000.csv"
SCHEMA = "vh-stage351-original-guest-exit-tail-reason/v1"
VERIFIED = "ORIGINAL_GUEST_EXIT_TAIL_CAUSE_SOURCE_VERIFIED"
REASONS = (
    "not_attempted", "precondition_failed", "lease_busy", "append_failed",
    "wait_failed", "wait_empty", "release_mismatch", "return_confirmed",
)
KEYS = (
    "software_exit_tail_reason_only",
    "tail_reason_code", "tail_attempted",
    "tail_descriptor_return_confirmed", "tail_lease_acquired",
    "lease_pages_acquired", "lease_pages_released", "abandoned_sessions",
)
MAX64 = (1 << 64) - 1
MAX32 = (1 << 32) - 1


def audit_source(raw: bytes, stage313: dict, stage348: dict) -> dict:
    if (not isinstance(raw, bytes) or len(raw) > 512 or
        not raw.startswith(b"scope,value\n") or not raw.endswith(b"\n") or
        b"\r" in raw or b"\x00" in raw):
        raise ExitTimelineError("invalid original Stage351 CSV encoding")
    lines = raw[len(b"scope,value\n"):].splitlines(keepends=True)
    if len(lines) != len(KEYS):
        raise ExitTimelineError("wrong original Stage351 row count")
    values = {}
    for key, row in zip(KEYS, lines):
        prefix = (key + ",").encode("ascii")
        if not row.startswith(prefix) or row.count(b",") != 1 or not row.endswith(b"\n"):
            raise ExitTimelineError("Stage351 noncanonical row name or order")
        number = row[len(prefix):-1]
        if (not number or not number.isascii() or not number.isdigit() or
            (len(number) > 1 and number.startswith(b"0"))):
            raise ExitTimelineError("Stage351 noncanonical integer")
        n = int(number)
        bound = MAX64 if key in ("lease_pages_acquired", "lease_pages_released") else MAX32
        if n > bound:
            raise ExitTimelineError("Stage351 counter overflow")
        values[key] = n

    code = values["tail_reason_code"]
    if code >= len(REASONS):
        raise ExitTimelineError("unknown Stage351 tail reason")
    attempted, confirmed, leased = (
        values[k] for k in (
            "tail_attempted","tail_descriptor_return_confirmed","tail_lease_acquired")
    )
    a, r, abandoned = (
        values[k] for k in (
            "lease_pages_acquired","lease_pages_released","abandoned_sessions")
    )
    if (values["software_exit_tail_reason_only"] != 1 or
        attempted != int(code != 0) or
        confirmed != int(code == 7) or
        leased != int(3 <= code <= 7) or
        a == 0 or a == MAX64 or r == MAX64 or abandoned == MAX32 or
        r > a or a-r != abandoned or
        (leased and not confirmed and abandoned == 0)):
        raise ExitTimelineError("Stage351 guest tail software lifecycle inconsistent")
    if (not isinstance(stage313,dict)
        or stage313.get("schema") != "vh-guest-last-audout-page-release-versus-exit/v1"
        or stage313.get("result") != "GUEST_LAST_AUDOUT_RELEASE_SOFTWARE_TIMING_VALIDATED"
        or stage313.get("original_guest_page_witness_observed") is not True
        or stage313.get("tail_bounded_attempt_observed") is not bool(attempted)
        or stage313.get("tail_release_confirmed") is not bool(confirmed)
        or stage313.get("hardware_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("Stage351 disagrees with original Stage313 source")
    if (not isinstance(stage348,dict)
        or stage348.get("schema") != "vh-stage348-original-software-lease-reconciliation/v1"
        or stage348.get("result") != "ORIGINAL_GUEST_SOFTWARE_PCM_LEASE_BALANCE_SOURCE_VERIFIED"
        or stage348.get("original_guest_software_lease_source_observed") is not True
        or stage348.get("physical_Nintendo_Switch_audio_tested") is not False
        or stage348.get("lease_pages_acquired") != a
        or stage348.get("lease_pages_released") != r
        or stage348.get("abandoned_sessions") != abandoned
        or type(stage348.get("accepted_pages_submitted")) is not int
        or stage348["accepted_pages_submitted"] > r):
        raise ExitTimelineError("Stage351 disagrees with original Stage348 source")
    return {
        "schema": SCHEMA,
        "result": VERIFIED,
        "original_guest_tail_reason_csv_sha256": hashlib.sha256(raw).hexdigest(),
        "original_guest_tail_reason_bytes_preserved": True,
        "original_guest_tail_reason_source_observed": True,
        "reason_code": code,
        "reason_name": REASONS[code],
        "tail_attempted": bool(attempted),
        "tail_descriptor_return_confirmed": bool(confirmed),
        "tail_lease_acquired": bool(leased),
        "lease_pages_acquired": a,
        "lease_pages_released": r,
        "abandoned_sessions": abandoned,
        "bound_to_original_stage313_tail_observation": True,
        "bound_to_original_stage348_lease_observation": True,
        "one_to_one_causal_attribution_proven": False,
        "physical_Nintendo_Switch_audio_tested": False,
        "DAC_or_speaker_audio_verified": False,
    }


def audit_guest(root: Path, stage313: dict, stage348: dict) -> tuple[dict,bytes]:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("missing or linked original guest SD root")
    directory = root
    for part in SUBDIR.parts:
        directory = directory / part
        if directory.is_symlink() or not directory.is_dir():
            raise ExitTimelineError("linked/missing original guest SD directory")
    target = directory / SOURCE
    if (target.is_symlink() or not target.is_file()
        or len(list(directory.glob("audio-exit-tail-reason-*.csv"))) != 1):
        raise ExitTimelineError("missing/ambiguous original tail reason source")
    raw = target.read_bytes()
    doc = audit_source(raw,stage313,stage348)
    doc["original_guest_source_relative_path"] = str(SUBDIR / SOURCE)
    return doc,raw


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",required=True,type=Path)
    p.add_argument("--stage313",required=True,type=Path)
    p.add_argument("--stage348",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--output-original",required=True,type=Path)
    a = p.parse_args(argv)
    try:
        for path in (a.output,a.output_original):
            if path.exists() or path.is_symlink():
                raise ExitTimelineError("refuse overwrite Stage351 evidence")
        for path in (a.guest_root_file,a.stage313,a.stage348):
            if path.is_symlink() or not path.is_file():
                raise ExitTimelineError("Stage351 original source dependency unavailable")
        root = a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("invalid NeXium guest SD locator")
        doc, raw = audit_guest(
            Path(root),
            json.loads(a.stage313.read_text(encoding="utf-8")),
            json.loads(a.stage348.read_text(encoding="utf-8")),
        )
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output_original.parent.mkdir(parents=True,exist_ok=True)
        with a.output_original.open("xb") as out:
            out.write(raw)
        if a.output_original.read_bytes() != raw:
            raise ExitTimelineError("Stage351 copied guest source changed bytes")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(doc,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,
            "reason_name":doc["reason_name"],
            "abandoned_sessions":doc["abandoned_sessions"],
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError) as exc:
        print(json.dumps({
            "result":"ORIGINAL_GUEST_EXIT_TAIL_REASON_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
