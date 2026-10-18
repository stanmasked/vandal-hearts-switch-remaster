#!/usr/bin/env python3
"""Stage314: preserve ORIGINAL guest-created last audout buffer-return CSV.

Re-read both original guest SD sources and require Stage307/310/313
source receipts to reproduce. Copy only five software-telemetry rows,
not retail music/PCM. Never reconstruct source CSV from derived JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    OBSERVED, SUBDIR, ExitTimelineError, audit_guest_root,
)
from audit_nexium_guest_last_buffer_return import (
    COMPLETE, ORIGINAL, audit_guest, audit_source,
)

SCHEMA = "vh-guest-original-last-audout-release-preservation/v1"
VERIFIED = "ORIGINAL_GUEST_LAST_AUDOUT_SOURCE_PRESERVED_AND_REAUDITED"


def preserve_original(root: Path, stage307: dict, stage310: dict,
                      stage313: dict, prior_exit_bytes: bytes,
                      destination: Path) -> dict:
    if (root.is_symlink() or not root.is_dir() or
            destination.exists() or destination.is_symlink() or
            not isinstance(stage307, dict) or
            not isinstance(stage310, dict) or
            not isinstance(stage313, dict)):
        raise ExitTimelineError("unsafe original source/output")
    # Verify the previously PRESERVED original exit source, rather
    # than trusting only the hash written in Stage307/310 JSON.
    exit_src = root / SUBDIR / "audio-exit-timeline-000.csv"
    page_src = root / SUBDIR / ORIGINAL
    if (exit_src.is_symlink() or page_src.is_symlink() or
            not exit_src.is_file() or not page_src.is_file()):
        raise ExitTimelineError("missing guest-created original event CSVs")
    fresh307 = audit_guest_root(root)
    if fresh307 != stage307 or fresh307.get("result") != OBSERVED:
        raise ExitTimelineError("Stage307 source receipt did not reproduce")
    if exit_src.read_bytes() != prior_exit_bytes:
        raise ExitTimelineError("original guest shutdown CSV differs from Stage310 copy")
    exit_sha = hashlib.sha256(prior_exit_bytes).hexdigest()
    if (not stage310.get("original_source_csv_bytes_independently_reaudited")
            or stage310.get("guest_exit_receipt_sha256") != exit_sha
            or stage310.get("original_guest_exit_csv_size") != len(prior_exit_bytes)
            or stage310.get("result") !=
            "ORIGINAL_GUEST_EXIT_CSV_BYTES_PRESERVED_AND_REAUDITED"):
        raise ExitTimelineError("Stage310 original exit source provenance invalid")
    fresh313 = audit_guest(root)
    if (fresh313 != stage313 or fresh313.get("result") != COMPLETE or
            fresh313.get("original_guest_page_witness_observed") is not True):
        raise ExitTimelineError("Stage313 original audout last-page receipt mismatch")
    original = page_src.read_bytes()
    if not original or len(original) > 1024:
        raise ExitTimelineError("unsafe guest audout original length")
    independent = audit_source(original, fresh307)
    digest = hashlib.sha256(original).hexdigest()
    if (independent.get("original_guest_page_witness_sha256") != digest or
            digest != fresh313.get("original_guest_page_witness_sha256")):
        raise ExitTimelineError("original audout page source hash mismatch")
    if (original != page_src.read_bytes() or
            prior_exit_bytes != exit_src.read_bytes()):
        raise ExitTimelineError("original guest source changed during replay")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(original)
    if destination.read_bytes() != original:
        raise ExitTimelineError("archived original audout source copy mismatch")
    return {
        "schema": SCHEMA,
        "result": VERIFIED,
        "original_guest_output_csv_preserved": True,
        "original_guest_output_csv_filename": ORIGINAL,
        "original_guest_output_csv_size": len(original),
        "original_guest_output_csv_sha256": digest,
        "original_guest_exit_csv_sha256": exit_sha,
        "source_stage307_reproduced": True,
        "source_stage310_original_bytes_reproduced": True,
        "source_stage313_reproduced": True,
        "original_page_count": independent["page_return_count"],
        "last_page_relative_to_Plus_ns":
            independent["last_page_relative_to_Plus_ns"],
        "original_guest_source_bytes_reaudited": True,
        "audout_buffer_release_not_speaker_playback": True,
        "guest_to_host_PCM_clock_calibration_verified": False,
        "original_soundtrack_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("guest-root-file", "stage307", "stage310", "stage313",
                 "prior-original-exit", "output-original", "output-report"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args(argv)
    try:
        if a.output_report.exists() or a.output_report.is_symlink():
            raise ExitTimelineError("refuse overwrite original output witness")
        paths = (a.guest_root_file,a.stage307,a.stage310,a.stage313,
                 a.prior_original_exit)
        if any(p.is_symlink() or not p.is_file() for p in paths):
            raise ExitTimelineError("one or more original provenance inputs missing")
        path = a.guest_root_file.read_text(encoding="utf-8").strip()
        if not path.startswith("/") or "\x00" in path or "\n" in path:
            raise ExitTimelineError("invalid isolated NeXium guest root locator")
        reports = [json.loads(p.read_text(encoding="utf-8"))
                   for p in (a.stage307,a.stage310,a.stage313)]
        result = preserve_original(
            Path(path), *reports, a.prior_original_exit.read_bytes(),
            a.output_original)
        a.output_report.write_text(json.dumps(result, sort_keys=True,indent=2)+"\n",
                                   encoding="utf-8")
        print(json.dumps({"result":result["result"],
                          "original_guest_output_csv_sha256":
                              result["original_guest_output_csv_sha256"],
                          "original_soundtrack_verified":False},sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"result":"STAGE314_ORIGINAL_BUFFER_SOURCE_NOT_VERIFIED",
                          "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
