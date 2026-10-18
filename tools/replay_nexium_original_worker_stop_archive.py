#!/usr/bin/env python3
"""Stage318: independent runner replays ORIGINAL guest worker-stop CSV bytes.

Re-audits BOTH earlier original exit/audout CSVs, true CRC-protected
optical guest image and all Stage307/308/310/313/314 reports BEFORE
recomputing Stage317 worker-observed mailbox marker. No JSON substitutes
for original guest source bytes, no guest->host PCM/DAC clock fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import SUBDIR
from audit_nexium_guest_worker_stop_observed import (
    VERIFIED, FILE as WORKER_FILE, audit_worker_stop_csv,
)
from audit_switch_guest_scene_trace import TraceError
from replay_nexium_original_audout_exit_archive import (
    read_original_archive, independent_original_audout_replay,
)

SCHEMA="vh-original-guest-worker-stop-independent-archive-replay/v1"
RESULT="ORIGINAL_GUEST_WORKER_STOP_AND_AUDOUT_SOURCES_INDEPENDENTLY_REPLAYED"
STAGE317="guest-worker-stop-observed-stage317.json"


def audit_original_worker_stop(originals:tuple, worker_raw:bytes,
                               original_stage317:dict, run_id:int)->dict:
    if (not isinstance(originals,tuple) or len(originals)!=8
            or type(run_id) is not int or run_id<=0
            or not isinstance(original_stage317,dict)
            or not isinstance(worker_raw,bytes) or
            not worker_raw or len(worker_raw)>128):
        raise TraceError("missing raw original worker stop source or invalid run")
    old=independent_original_audout_replay(*originals,run_id)
    if old["result"]!="ORIGINAL_GUEST_AUDOUT_RELEASE_AND_EXIT_SOURCES_INDEPENDENTLY_REPLAYED":
        raise TraceError("Stage315 exit/audout source chain not independently replayed")
    exit_raw,page_raw,optical,s307,s308,s310,s313,s314=originals
    fresh=audit_worker_stop_csv(worker_raw,s307,s313)
    if fresh["result"]!=VERIFIED:
        raise TraceError("original guest software worker never observed stop")
    fresh["original_worker_stop_source_observed"]=True
    fresh["original_worker_stop_source_path"]=str(SUBDIR/WORKER_FILE)
    fresh["original_worker_stop_csv_bytes_preserved"]=True
    if fresh!=original_stage317:
        raise TraceError("Stage317 capture-time result differs from source original")
    if (not 0<=fresh["last_page_return_to_worker_observation_ns"]
            or not 0<=fresh["worker_observation_to_cleanup_ns"]
            or not 0<=fresh["stop_request_to_worker_observation_ns"]):
        raise TraceError("source guest software chronology not conserved")
    if (old["original_guest_audout_page_csv_sha256"]!=
            fresh["source_last_page_csv_sha256"] or
            old["original_guest_exit_csv_sha256"]!=
            fresh["source_guest_exit_csv_sha256"]):
        raise TraceError("worker marker source hashes conflict with independently reaudited sources")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "original_neXium_workflow_run_id":run_id,
        "original_guest_worker_stop_csv_sha256":hashlib.sha256(worker_raw).hexdigest(),
        "original_guest_exit_csv_sha256":hashlib.sha256(exit_raw).hexdigest(),
        "original_guest_last_page_csv_sha256":hashlib.sha256(page_raw).hexdigest(),
        "original_optical_png_sha256":hashlib.sha256(optical).hexdigest(),
        "original_optical_packet_sha256":old["optical_original_packet_sha256"],
        "original_guest_worker_stop_source_bytes_independently_reaudited":True,
        "original_guest_exit_and_last_page_bytes_independently_reaudited":True,
        "original_guest_crc_optical_frame_independently_replayed":True,
        "original_stage307_308_310_313_314_receipts_reproduced":True,
        "original_stage317_receipt_reproduced":True,
        "original_last_page_position_relative_to_guest_exit":
            old["last_page_software_exit_category"],
        "guest_stop_request_to_last_page_return_ns":
            fresh["guest_stop_requested_to_last_page_return_ns"],
        "guest_last_page_return_to_worker_stop_observed_ns":
            fresh["last_page_return_to_worker_observation_ns"],
        "guest_stop_request_to_worker_stop_observed_ns":
            fresh["stop_request_to_worker_observation_ns"],
        "guest_worker_stop_observed_to_cleanup_ns":
            fresh["worker_observation_to_cleanup_ns"],
        "guest_audout_buffer_return_not_last_audible_sample":True,
        "guest_mailbox_stop_not_physical_DAC_stop":True,
        "guest_monotonic_not_synchronized_with_host_PCM":True,
        "plus_causes_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def read_archive(root:Path)->tuple[tuple,bytes,dict]:
    # This reader already insists that all 8 original guest sources and
    # corresponding receipts are unique, regular and co-located.
    original=read_original_archive(root)
    pairs={}
    for name in (WORKER_FILE,STAGE317):
        found=list(root.rglob(name))
        if len(found)!=1 or found[0].is_symlink() or not found[0].is_file():
            raise TraceError("worker source/Stage317 receipt missing or ambiguous")
        pairs[name]=found[0]
    old_exit=list(root.rglob("audio-exit-timeline-000.csv"))
    if len(old_exit)!=1 or any(p.parent!=old_exit[0].parent for p in pairs.values()):
        raise TraceError("original guest worker marker not co-located with original exit evidence")
    if pairs[WORKER_FILE].stat().st_size>128 or pairs[STAGE317].stat().st_size>16384:
        raise TraceError("unbounded original worker source/receipt")
    current=pairs[WORKER_FILE].parent
    while current!=root:
        if current==current.parent or current.is_symlink():
            raise TraceError("symlink source directory or archive breakout")
        current=current.parent
    return (
        original,pairs[WORKER_FILE].read_bytes(),
        json.loads(pairs[STAGE317].read_text(encoding="utf-8")),
    )


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-run-id",type=int,required=True)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse overwrite original independent receipt")
        originals,raw,receipt=read_archive(args.archive)
        verified=audit_original_worker_stop(
            originals,raw,receipt,args.original_run_id)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(verified,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":verified["result"],
            "original_run":verified["original_neXium_workflow_run_id"],
            "last_page_return_to_worker_stop_guest_ns":
                verified["guest_last_page_return_to_worker_stop_observed_ns"],
            "original_guest_worker_csv_sha256":
                verified["original_guest_worker_stop_csv_sha256"],
            "audible_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as e:
        print(json.dumps({"result":"STAGE318_ORIGINAL_GUEST_WORKER_STOP_REPLAY_NOT_VERIFIED",
                          "error":str(e)},sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
