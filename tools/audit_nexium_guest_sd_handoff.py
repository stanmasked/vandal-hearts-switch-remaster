#!/usr/bin/env python3
"""Recover actual post-join scene CSV from an isolated NeXium emulated SD.

No fallback to host timing: missing/ambiguous/unverifiable guest CSV fails
this independent evidence gate and leaves a separate machine-readable verdict.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

from audit_switch_guest_scene_trace import TraceError, analyze_sd_csv

EXPECTED_STATES = [2, 1, 2, 1]
SCHEMA = "vh-nexium-guest-sd-evidence/v1"

def run(root_file: Path, evidence_dir: Path, temp_dir: Path,
        run_id: str) -> dict:
    if not run_id.isdecimal():
        raise TraceError("invalid CI run ID")
    expected = (temp_dir / f"vh-nexium-stage266-{run_id}").resolve()
    if root_file.is_symlink() or not root_file.is_file():
        raise TraceError("missing or symlinked guest SD root receipt")
    actual = Path(root_file.read_text(encoding="utf-8").strip()).resolve()
    if actual != expected:
        raise TraceError("guest SD root differs from CI isolated directory")
    guest_dir = expected / "sdmc" / "switch" / "vandal-hearts-remake"
    if not guest_dir.is_dir() or guest_dir.is_symlink():
        raise TraceError("guest SD directory absent or symlinked")
    files = sorted(guest_dir.glob("audio-scene-trace-[0-9][0-9][0-9][0-9].csv"))
    pending = sorted(guest_dir.glob("audio-scene-trace-[0-9][0-9][0-9][0-9].tmp"))
    if len(files) != 1:
        raise TraceError(
            f"expected one newly committed guest scene CSV, found {len(files)}"
            f" (incomplete temp files: {len(pending)})")
    source = files[0]
    if not source.is_file() or source.is_symlink():
        raise TraceError("not a regular guest SD CSV")
    data = source.read_bytes()
    if not 0 < len(data) <= 16384:
        raise TraceError("unbounded or empty guest SD CSV")
    # No SD mutation should occur after the guest app exits. Recheck
    # the exact bytes before saving an independently verified copy.
    if data != source.read_bytes():
        raise TraceError("guest SD CSV changed during independent readback")
    report = analyze_sd_csv(data.decode("ascii"))
    accepted = report["complete_scene_serials"]
    if (report["result"] != "GUEST_INTERNAL_PHASES_OBSERVED"
        or report["sd_csv_dropped_total"] != 0
        or report["partial_scene_serials"]
        or len(accepted) != 4
        or [x["scene"] for x in accepted] != EXPECTED_STATES):
        raise TraceError("not all four guest A/B scene transitions independently confirmed")
    if not evidence_dir.is_dir() or evidence_dir.is_symlink():
        raise TraceError("evidence destination absent or symlinked")
    dst = evidence_dir / "guest-scene-trace.csv"
    if dst.exists() or dst.is_symlink():
        raise TraceError("refuse overwrite of earlier guest CSV evidence")
    with dst.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if dst.read_bytes() != data:
        raise TraceError("copied evidence differs from guest SD source")
    return {
        "schema": SCHEMA,
        "result": "FOUR_GUEST_SCENE_INTERNAL_PHASES_OBSERVED",
        "guest_sd_csv_name": source.name,
        "source_nro_digest": "read the independent NRO preflight receipt",
        "csv_sha256": hashlib.sha256(data).hexdigest(),
        "csv_bytes": len(data),
        "trace_audit": report,
        "hardware_status": "HARDWARE NOT TESTED",
        "actual_input_to_dac_latency_ms": None,
        "emulator_audibility_confirmed": False,
        "power_loss_durability_proven": False
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-file",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args=parser.parse_args()
    verdict = args.evidence_dir / "guest-scene-sd-verdict.json"
    try:
        result=run(args.root_file,args.evidence_dir,
                   Path(os.environ["RUNNER_TEMP"]),
                   os.environ["GITHUB_RUN_ID"])
        code=0
    except (TraceError,OSError,UnicodeError,KeyError) as exc:
        result={
            "schema": SCHEMA,
            "result": "GUEST_SD_TRACE_NOT_VERIFIED",
            "error": str(exc),
            "hardware_status": "HARDWARE NOT TESTED",
            "actual_input_to_dac_latency_ms": None
        }
        code=2
    payload=json.dumps(result,indent=2)+"\n"
    if verdict.exists() or verdict.is_symlink():
        print("refuse overwrite of guest SD verdict",file=sys.stderr)
        return 2
    verdict.write_text(payload,encoding="utf-8")
    print(payload,end="",flush=True)
    return code

if __name__=="__main__":
    raise SystemExit(main())
