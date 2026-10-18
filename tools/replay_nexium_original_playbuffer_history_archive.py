#!/usr/bin/env python3
"""Stage323 independently re-audit authentic final 16 guest PlayBuffer calls.

Replay ALL original Stage321 guest-source proof first (exit, last page,
worker stop, final PlayBuffer service call, and CRC optical scene PNG).
Then independently decode the original Stage322 history CSV, compare
the EXACT Stage322 capture receipt, and only then calculate a baseline.
Never reconstruct missing original files from a JSON receipt.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError
from audit_nexium_guest_playbuffer_history import (
    audit_source as audit_history, FILE as SOURCE, VERIFIED as HISTORY_VERIFIED,
)
from replay_nexium_original_last_playbuffer_archive import (
    read_archive as read_stage321_archive,
    independently_replay as replay_stage321,
)

SCHEMA="vh-independent-original-last16-PlayBuffer-guest-source-replay/v1"
VERIFIED="ORIGINAL_LAST16_PLAYBUFFER_CALLS_AND_EXIT_INDEPENDENTLY_REPLAYED"
CAPTURE="guest-playbuffer-history-stage322.json"


def replay_original_history(stage321_inputs:tuple,
                            raw_history:bytes,stage322_receipt:dict,
                            run_id:int)->dict:
    if (not isinstance(stage321_inputs,tuple) or len(stage321_inputs)!=5
            or type(run_id) is not int or run_id<=0
            or not isinstance(raw_history,bytes) or len(raw_history)>2048
            or not isinstance(stage322_receipt,dict)):
        raise TraceError("missing original PlayBuffer history or source identity")
    prev=replay_stage321(*stage321_inputs,run_id)
    if prev["result"]!="ORIGINAL_LAST_PLAYBUFFER_AND_WORKER_STOP_SOURCES_INDEPENDENTLY_REPLAYED":
        raise TraceError("original Stage321 guest service-call source did not replay")
    originals,worker_raw,worker_report,last_call_raw,final=stage321_inputs
    try:
        observed=audit_history(raw_history,final)
    except (ExitTimelineError,ValueError,TypeError,KeyError) as exc:
        raise TraceError("original PlayBuffer history CSV failed independent source audit") from exc
    if observed["result"]!=HISTORY_VERIFIED:
        raise TraceError("no authentic guest rolling PlayBuffer history")
    observed["original_guest_history_source_observed"]=True
    observed["original_guest_history_source_path"]=str(SUBDIR/SOURCE)
    observed["original_guest_history_bytes_preserved"]=True
    if observed!=stage322_receipt:
        raise TraceError("captured Stage322 derived report differs from independent ORIGINAL CSV replay")
    if (observed["original_last_successful_PlayBuffer_source_sha256"]!=
        prev["original_guest_last_playbuffer_source_sha256"]):
        raise TraceError("rolling history is attached to another original last call")
    durations=observed["original_call_rows"]
    prior=observed["prior_successful_call_count_in_window"]
    final_duration=observed["final_call_duration_guest_ns"]
    baseline=observed["prior_successful_duration_lower_median_guest_ns"]
    if prior==0 and baseline is not None:
        raise TraceError("missing prior service calls falsely represented by a duration baseline")
    if prior>0 and (baseline is None or final_duration-baseline!=
                    observed["final_minus_prior_lower_median_guest_ns"]):
        raise TraceError("final duration/baseline arithmetic disagrees with original software source")
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "original_source_workflow_run_id":run_id,
        "original_guest_history_csv_sha256":hashlib.sha256(raw_history).hexdigest(),
        "original_last_successful_PlayBuffer_csv_sha256":
            hashlib.sha256(last_call_raw).hexdigest(),
        "original_guest_worker_stop_csv_sha256":hashlib.sha256(worker_raw).hexdigest(),
        "original_guest_exit_csv_sha256":hashlib.sha256(originals[0]).hexdigest(),
        "original_guest_optical_crc_PNG_sha256":hashlib.sha256(originals[2]).hexdigest(),
        "original_stage307_308_310_313_314_317_320_321_sources_replayed":True,
        "original_stage322_history_CSV_and_receipt_replayed":True,
        "source_call_count":observed["total_original_normal_PlayBuffer_calls"],
        "recent_original_service_call_count":len(durations),
        "recent_original_successful_calls":
            observed["original_recent_success_count"],
        "recent_original_failed_calls":
            observed["original_recent_failed_return_count"],
        "last_successful_original_call_in_window":
            observed["final_successful_call_in_recent_window"],
        "prior_successful_calls_in_window":prior,
        "prior_successful_lower_median_duration_guest_ns":baseline,
        "last_successful_duration_guest_ns":final_duration,
        "last_minus_prior_lower_median_guest_ns":
            observed["final_minus_prior_lower_median_guest_ns"],
        "has_source_verified_prior_call_baseline":prior>0,
        "guest_last_call_overlap_after_main_stop_guest_ns":
            prev["last_successful_PlayBuffer_overlap_after_stop_request_ns"],
        "original_guest_to_host_PCM_clock_fit_verified":False,
        "guest_software_call_is_NOT_DAC_or_speaker_sound":True,
        "plus_caused_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def read_archive(root:Path)->tuple[tuple,bytes,dict]:
    inputs=read_stage321_archive(root)
    if root.is_symlink() or not root.is_dir():
        raise TraceError("invalid source archive root")
    names=(SOURCE,CAPTURE)
    collected=[]
    for name in names:
        matched=list(root.rglob(name))
        if len(matched)!=1 or matched[0].is_symlink() or not matched[0].is_file():
            raise TraceError("missing, ambiguous, or symlinked original Stage322 history")
        collected.append(matched[0])
    original_exit=list(root.rglob("audio-exit-timeline-000.csv"))
    if len(original_exit)!=1 or any(
            p.parent!=original_exit[0].parent for p in collected):
        raise TraceError("guest original history and receipts are not co-located")
    if collected[0].stat().st_size>2048 or collected[1].stat().st_size>16384:
        raise TraceError("guest original history is unexpectedly large")
    current=collected[0].parent
    while current!=root:
        if current==current.parent or current.is_symlink():
            raise TraceError("archive source path contains symlink or breakout")
        current=current.parent
    return inputs,collected[0].read_bytes(),json.loads(
        collected[1].read_text(encoding="utf-8"))


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-run-id",type=int,required=True)
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("never overwrite an independent source receipt")
        result=replay_original_history(*read_archive(args.archive),args.original_run_id)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({"result":result["result"],
                          "prior_source_success_count":
                              result["prior_successful_calls_in_window"],
                          "prior_source_lower_median_guest_ns":
                              result["prior_successful_lower_median_duration_guest_ns"],
                          "last_call_guest_software_ns":
                              result["last_successful_duration_guest_ns"],
                          "audible_speaker_tested":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE323_ORIGINAL_HISTORY_NOT_VERIFIED",
                          "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
