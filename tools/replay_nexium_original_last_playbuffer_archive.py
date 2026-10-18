#!/usr/bin/env python3
"""Stage321: independent replay of ORIGINAL last audoutPlayBuffer bracket.

The source is a guest-created software telemetry CSV saved by Stage320.
Reconstruct original exit, audout-page, worker-stop and CRC optical
receipts first; then reparse the original final PlayBuffer call bytes.
Do not confuse service return, DAC playback, or the host PCM sample clock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError
from audit_nexium_guest_last_playbuffer import (
    FILE as PLAYBUFFER_SOURCE,
    VERIFIED as PLAYBUFFER_VERIFIED,
    audit_original as audit_last_call,
)
from audit_switch_guest_scene_trace import TraceError
from replay_nexium_original_worker_stop_archive import (
    read_archive as read_stage318,
    audit_original_worker_stop,
)

SCHEMA="vh-independent-original-guest-last-playbuffer-call/v1"
VERIFIED="ORIGINAL_LAST_PLAYBUFFER_AND_WORKER_STOP_SOURCES_INDEPENDENTLY_REPLAYED"
CAPTURE_RECEIPT="guest-last-playbuffer-stage320.json"


def independently_replay(originals: tuple, worker_source: bytes,
                         stage317: dict, original_call: bytes,
                         stage320: dict, run_id: int) -> dict:
    if (type(run_id) is not int or run_id <= 0
            or not isinstance(original_call, bytes)
            or not original_call or len(original_call)>512
            or not isinstance(stage320, dict)):
        raise TraceError("invalid original call source, receipt or capture id")
    stage318=audit_original_worker_stop(
        originals,worker_source,stage317,run_id)
    if (stage318["result"] !=
            "ORIGINAL_GUEST_WORKER_STOP_AND_AUDOUT_SOURCES_INDEPENDENTLY_REPLAYED"):
        raise TraceError("earlier raw original guest source chain invalid")
    original_exit, original_page, original_png, guest307, guest308, guest310, guest313, guest314=originals
    try:
        fresh=audit_last_call(original_call,guest307,guest313,stage317)
    except ExitTimelineError as exc:
        # An invalid original CSV is an independent archive-source
        # verification failure, not an uncaught parser exception.
        # Keep the exact same strict Stage320 source checks.
        raise TraceError("original PlayBuffer CSV cannot be independently re-audited") from exc
    if fresh["result"]!=PLAYBUFFER_VERIFIED:
        raise TraceError("no valid last normal PlayBuffer source")
    fresh["original_guest_playbuffer_source_observed"]=True
    fresh["original_guest_playbuffer_source_path"]=str(SUBDIR/PLAYBUFFER_SOURCE)
    fresh["original_source_bytes_preserved"]=True
    if fresh != stage320:
        raise TraceError("original Stage320 receipt does not reproduce from source bytes")
    if (fresh["original_guest_worker_stop_csv_sha256"]!=
            stage318["original_guest_worker_stop_csv_sha256"]
            or fresh["original_guest_exit_csv_sha256"]!=
            stage318["original_guest_exit_csv_sha256"]
            or fresh["original_guest_last_page_csv_sha256"]!=
            stage318["original_guest_last_page_csv_sha256"]):
        raise TraceError("PlayBuffer bracket bound to different guest original files")
    begin=fresh["last_successful_PlayBuffer_begin_guest_ns"]
    end=fresh["last_successful_PlayBuffer_return_guest_ns"]
    stop=guest307["guest_monotonic_timestamps_ns"]["stop_requested"]
    last_page=guest313["last_page_return_guest_ns"]
    seen_stop=stage317["worker_stop_observation_guest_ns"]
    if not begin<=end<=last_page<=seen_stop:
        raise TraceError("source-verified final call not ordered with last page/stop")
    overlap=fresh["portion_of_last_call_after_stop_request_ns"]
    duration=end-begin
    if not 0<=overlap<=duration:
        raise TraceError("invalid overlap of last PlayBuffer call and exit")
    # Partition the WHOLE guest software interval from the main-thread
    # stop request to the last normal PCM page return. This does NOT
    # imply that every nanosecond outside this one PlayBuffer bracket
    # was spent in a single other service call or produced audible PCM.
    stop_to_page=last_page-stop
    before_call=max(0,begin-stop) if end>stop else 0
    after_call=last_page-max(end,stop)
    if (stop_to_page<0 or before_call<0 or after_call<0 or
            before_call+overlap+after_call!=stop_to_page):
        raise TraceError("final original audout call partition does not conserve guest time")
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "original_capture_workflow_run_id":run_id,
        "original_guest_last_playbuffer_source_sha256":
            hashlib.sha256(original_call).hexdigest(),
        "original_guest_worker_stop_source_sha256":
            hashlib.sha256(worker_source).hexdigest(),
        "original_guest_exit_source_sha256":
            hashlib.sha256(original_exit).hexdigest(),
        "original_guest_last_page_source_sha256":
            hashlib.sha256(original_page).hexdigest(),
        "original_guest_optical_PNG_sha256":
            hashlib.sha256(original_png).hexdigest(),
        "original_guest_optical_packet_sha256":
            stage318["original_optical_packet_sha256"],
        "original_PlayBuffer_CSV_bytes_independently_reaudited":True,
        "original_exit_page_stop_CSVs_independently_reaudited":True,
        "original_guest_optical_CRC_replayed":True,
        "capture_time_stage307_308_310_313_314_317_320_reproduced":True,
        "last_successful_PlayBuffer_begin_guest_ns":begin,
        "last_successful_PlayBuffer_return_guest_ns":end,
        "last_successful_PlayBuffer_call_duration_guest_ns":duration,
        "last_successful_PlayBuffer_overlap_after_stop_request_ns":overlap,
        "last_call_position_relative_to_stop_request":
            fresh["last_successful_call_relative_to_stop_request"],
        "last_call_return_to_last_page_witness_guest_ns":last_page-end,
        "last_page_to_worker_observed_stop_guest_ns":seen_stop-last_page,
        "stop_request_to_last_normal_PCM_page_return_guest_ns":stop_to_page,
        "post_stop_before_last_successful_call_guest_ns":before_call,
        "post_stop_inside_last_successful_call_guest_ns":overlap,
        "post_stop_after_last_successful_call_to_page_return_guest_ns":after_call,
        "source_time_partition_exactly_conserved":True,
        "last_service_call_is_not_entire_stop_delay_proof":True,
        "guest_software_time_not_host_PCM_or_DAC_sample_clock":True,
        "last_buffer_release_not_audible_speaker_output":True,
        "plus_causes_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def read_archive(root: Path) -> tuple:
    originals, worker_source, stage317=read_stage318(root)
    required=(PLAYBUFFER_SOURCE,CAPTURE_RECEIPT)
    targets={}
    for name in required:
        matches=list(root.rglob(name))
        if len(matches)!=1 or matches[0].is_symlink() or not matches[0].is_file():
            raise TraceError("missing/duplicate/symlinked original last PlayBuffer evidence")
        targets[name]=matches[0]
    earlier=list(root.rglob("audio-exit-timeline-000.csv"))
    if len(earlier)!=1 or any(
            p.parent!=earlier[0].parent for p in targets.values()):
        raise TraceError("last PlayBuffer original CSV not co-located with exit original")
    if targets[PLAYBUFFER_SOURCE].stat().st_size>512 or (
            targets[CAPTURE_RECEIPT].stat().st_size>16384):
        raise TraceError("unbounded final PlayBuffer original source/receipt")
    ancestor=targets[PLAYBUFFER_SOURCE].parent
    while ancestor!=root:
        if ancestor==ancestor.parent or ancestor.is_symlink():
            raise TraceError("untrusted original source parent directory")
        ancestor=ancestor.parent
    return (
        originals,worker_source,stage317,
        targets[PLAYBUFFER_SOURCE].read_bytes(),
        json.loads(targets[CAPTURE_RECEIPT].read_text(encoding="utf-8")),
    )


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-run-id",type=int,required=True)
    p.add_argument("--archive",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise TraceError("never overwrite independently replayed source report")
        result=independently_replay(*read_archive(a.archive),a.original_run_id)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "original_source_run_id":result["original_capture_workflow_run_id"],
            "last_PlayBuffer_service_duration_guest_ns":
                result["last_successful_PlayBuffer_call_duration_guest_ns"],
            "last_PlayBuffer_overlap_after_stop_guest_ns":
                result["last_successful_PlayBuffer_overlap_after_stop_request_ns"],
            "audible_speaker_output_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE321_ORIGINAL_CALL_REPLAY_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
