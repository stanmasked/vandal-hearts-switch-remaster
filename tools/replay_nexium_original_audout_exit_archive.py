#!/usr/bin/env python3
"""Stage315: independent original guest audout-page return archive replay.

Both original guest-created files (exit events and last page) and real
CRC-protected optical framebuffer must be available, unlike older
capture-time JSON-only witnesses. Reconstruct Stage307/308/310/313/314
from bytes, never trusting derived reports as substitute source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    OBSERVED, SUBDIR, parse_exit_csv,
)
from audit_nexium_guest_last_buffer_return import (
    COMPLETE, ORIGINAL as ORIGINAL_PAGE, audit_source as audit_page_source,
)
from audit_nexium_guest_optical_exit_clock import BOTH, audit_guest_clocks
from audit_switch_guest_scene_trace import TraceError
from replay_nexium_original_guest_exit_archive import (
    read_archive as read_stage311_archive,
    independent_archive_replay,
)

SCHEMA = "vh-independent-original-audout-page-guest-exit-archive/v1"
SOURCE313 = "guest-last-audout-release-stage313.json"
SOURCE314 = "guest-original-audout-last-page-stage314.json"
VERIFIED = "ORIGINAL_GUEST_AUDOUT_RELEASE_AND_EXIT_SOURCES_INDEPENDENTLY_REPLAYED"


def reconstruct_page_report(source: bytes, guest_exit: dict) -> dict:
    report = audit_page_source(source, guest_exit)
    if report["result"] != COMPLETE:
        raise TraceError("original guest page source not complete")
    report["original_guest_page_witness_observed"] = True
    report["guest_source_path"] = str(SUBDIR / ORIGINAL_PAGE)
    return report


def reconstruct_stage314(page: bytes, original_exit: bytes,
                         source313: dict) -> dict:
    if source313["result"] != COMPLETE:
        raise TraceError("unverified guest audout page source")
    return {
        "schema": "vh-guest-original-last-audout-release-preservation/v1",
        "result": "ORIGINAL_GUEST_LAST_AUDOUT_SOURCE_PRESERVED_AND_REAUDITED",
        "original_guest_output_csv_preserved": True,
        "original_guest_output_csv_filename": ORIGINAL_PAGE,
        "original_guest_output_csv_size": len(page),
        "original_guest_output_csv_sha256": hashlib.sha256(page).hexdigest(),
        "original_guest_exit_csv_sha256":
            hashlib.sha256(original_exit).hexdigest(),
        "source_stage307_reproduced": True,
        "source_stage310_original_bytes_reproduced": True,
        "source_stage313_reproduced": True,
        "original_page_count": source313["page_return_count"],
        "last_page_relative_to_Plus_ns":
            source313["last_page_relative_to_Plus_ns"],
        "original_guest_source_bytes_reaudited": True,
        "audout_buffer_release_not_speaker_playback": True,
        "guest_to_host_PCM_clock_calibration_verified": False,
        "original_soundtrack_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def independent_original_audout_replay(
        original_exit: bytes, original_page: bytes, optical_png: bytes,
        archived307: dict, archived308: dict, archived310: dict,
        archived313: dict, archived314: dict, run_id: int) -> dict:
    if (type(run_id) is not int or run_id <= 0
            or not original_page or len(original_page) > 1024
            or not isinstance(archived313, dict)
            or not isinstance(archived314, dict)):
        raise TraceError("invalid original source or capture ID")
    old = independent_archive_replay(
        original_exit, optical_png, archived307, archived308,
        archived310, run_id)
    if old["result"] != "INDEPENDENT_ORIGINAL_GUEST_EXIT_BYTES_FULLY_REPLAYED":
        raise TraceError("old exit source proof did not replay")

    guest = parse_exit_csv(original_exit)
    if guest["result"] != OBSERVED:
        raise TraceError("raw exit source is not fully observed")
    guest["guest_sd_receipt_observed"] = True
    guest["guest_csv_path"] = str(SUBDIR / "audio-exit-timeline-000.csv")
    if guest != archived307:
        raise TraceError("guest software exit source mismatch")
    optical = audit_guest_clocks(optical_png, guest)
    if optical["result"] != BOTH or optical != archived308:
        raise TraceError("guest optical provenance mismatch")
    fresh313 = reconstruct_page_report(original_page, guest)
    if fresh313 != archived313:
        raise TraceError("archived Stage313 last page does not reproduce")
    fresh314 = reconstruct_stage314(
        original_page, original_exit, fresh313)
    if fresh314 != archived314:
        raise TraceError("archived Stage314 original source preservation did not replay")
    return {
        "schema": SCHEMA,
        "result": VERIFIED,
        "original_capture_workflow_run_id": run_id,
        "original_guest_exit_csv_sha256":
            hashlib.sha256(original_exit).hexdigest(),
        "original_guest_exit_csv_byte_count": len(original_exit),
        "original_guest_audout_page_csv_sha256":
            hashlib.sha256(original_page).hexdigest(),
        "original_guest_audout_page_csv_byte_count": len(original_page),
        "optical_original_PNG_sha256": hashlib.sha256(optical_png).hexdigest(),
        "optical_original_packet_sha256": optical["optical_packet_sha256"],
        "stages_307_308_310_independently_replayed": True,
        "stages_313_314_independently_replayed": True,
        "both_original_guest_created_CSVs_reaudited_byte_exact": True,
        "original_guest_last_page_return_count": fresh313["page_return_count"],
        "original_guest_last_page_frames": fresh313["last_page_frames"],
        "last_page_relative_to_guest_Plus_observed_ns":
            fresh313["last_page_relative_to_Plus_ns"],
        "last_page_software_exit_category":
            fresh313["last_page_position_relative_to_guest_exit"],
        "bounded_tail_attempted": fresh313["tail_bounded_attempt_observed"],
        "bounded_tail_return_confirmed": fresh313["tail_release_confirmed"],
        "last_page_release_is_NOT_audible_sample_or_DAC_time": True,
        "normal_exit_taper_NOT_original_PS1_synth_music": True,
        "guest_monotonic_clock_not_host_PCM_sample_clock": True,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def read_original_archive(root: Path) -> tuple:
    # Stage311 reader checks one original exit CSV, one CRC-protected
    # optical PNG and the original Stage307/308/310 receipts in ONE
    # directory, refusing symlinks, duplicate names or separated files.
    exit_raw, png, s307, s308, s310 = read_stage311_archive(root)
    originals = root.rglob(ORIGINAL_PAGE)
    found = list(originals)
    if len(found) != 1 or found[0].is_symlink() or not found[0].is_file():
        raise TraceError("missing or ambiguous original guest audout source")
    common = found[0].parent
    for name in (SOURCE313, SOURCE314):
        docs = list(root.rglob(name))
        if len(docs) != 1 or docs[0].is_symlink() or not docs[0].is_file():
            raise TraceError("missing or ambiguous guest audout provenance report")
        if docs[0].parent != common or docs[0].stat().st_size > 16384:
            raise TraceError("source and audit receipts not co-located")
    required = [
        "audio-exit-timeline-000.csv", "scene-optical-trace.png",
        "guest-audio-exit-timeline-stage307.json",
        "guest-optical-exit-clock-stage308.json",
        "guest-original-exit-source-stage310.json",
    ]
    for name in required:
        item = list(root.rglob(name))
        if len(item) != 1 or item[0].parent != common:
            raise TraceError("original exit and original audout are not co-located")
    current=common
    while current != root:
        if current.is_symlink() or current == current.parent:
            raise TraceError("symlink archive parent directory")
        current=current.parent
    page=found[0].read_bytes()
    if len(page)>1024:
        raise TraceError("audout source exceeds fixed telemetry size")
    s313=json.loads((common/SOURCE313).read_text(encoding="utf-8"))
    s314=json.loads((common/SOURCE314).read_text(encoding="utf-8"))
    return exit_raw,page,png,s307,s308,s310,s313,s314


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-run-id", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse overwrite independent original byte report")
        result=independent_original_audout_replay(
            *read_original_archive(args.archive), args.original_run_id)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "source_guest_last_page_sha256":
                result["original_guest_audout_page_csv_sha256"],
            "last_page_guest_software_exit_category":
                result["last_page_software_exit_category"],
            "audible_sample_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE315_ORIGINAL_AUDOUT_ARCHIVE_NOT_VERIFIED",
                          "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
