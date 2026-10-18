#!/usr/bin/env python3
"""Stage328: compare two independently successful ORIGINAL NeXium PlayBuffer histories.

Each cohort is source-bound to its *original* guest CSV, original Stage320
last-call summary and original Stage322 16-call summary. This rechecks the
bounded software call history, not original PS1 audio, host time, speakers,
Switch hardware or an inferred cause of shutdown.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_guest_playbuffer_history import (
    FILE as HISTORY_FILE, SCHEMA as HISTORY_SCHEMA,
    VERIFIED as HISTORY_VERIFIED, audit_source,
)
from audit_nexium_guest_last_playbuffer import (
    FILE as LAST_FILE, SCHEMA as LAST_SCHEMA,
    VERIFIED as LAST_VERIFIED,
)
from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError

SCHEMA="vh-stage328-two-original-guest-playbuffer-histories/v1"
VERIFIED="TWO_ORIGINAL_GUEST_PLAYBUFFER_HISTORY_COHORTS_SOURCE_REPLAYED"
MAX_JSON=64_000
MAX_CSV=2048
SHA=re.compile(r"[0-9a-f]{64}\Z")

FILES={
    "last_csv":"audio-last-playbuffer-000.csv",
    "history_csv":"audio-playbuffer-history-000.csv",
    "stage320":"guest-last-playbuffer-stage320.json",
    "stage322":"guest-playbuffer-history-stage322.json",
}


def load(root:Path)->dict:
    if not root.is_dir() or root.is_symlink():
        raise ExitTimelineError("missing or symlinked original NeXium archive root")
    result={}
    for key,name in FILES.items():
        all_=list(root.rglob(name))
        safe=[p for p in all_ if p.is_file() and not p.is_symlink()
              and all(not q.is_symlink() for q in p.relative_to(root).parents)]
        if len(all_)!=1 or len(safe)!=1:
            raise ExitTimelineError("missing or ambiguous original NeXium audio source")
        p=safe[0]
        size=p.stat().st_size
        if size<=0 or size>(MAX_CSV if key.endswith("csv") else MAX_JSON):
            raise ExitTimelineError("oversized or empty original PlayBuffer evidence")
        result[key]=(p.read_bytes() if key.endswith("csv") else
                     json.loads(p.read_text(encoding="utf-8")))
    return result


def verify(source:dict,expected_history_sha:str)->dict:
    if not isinstance(expected_history_sha,str) or not SHA.fullmatch(expected_history_sha):
        raise ExitTimelineError("malformed original PlayBuffer source pin")
    history=source["history_csv"]
    last=source["last_csv"]
    stage320=source["stage320"]
    stage322=source["stage322"]
    if not isinstance(history,bytes) or not isinstance(last,bytes):
        raise ExitTimelineError("original source bytes missing")
    if hashlib.sha256(history).hexdigest()!=expected_history_sha:
        raise ExitTimelineError("original guest history SHA-256 differs from pinned capture")
    if (not isinstance(stage320,dict) or not isinstance(stage322,dict)
            or stage320.get("schema")!=LAST_SCHEMA
            or stage320.get("result")!=LAST_VERIFIED
            or stage320.get("original_source_bytes_preserved") is not True
            or stage320.get("original_guest_playbuffer_source_observed") is not True
            or stage320.get("audout_PlayBuffer_return_not_audible_speaker_or_DAC") is not True
            or stage320.get("one_call_does_not_explain_entire_stop_delay_automatically") is not True
            or stage320.get("physical_Nintendo_Switch_audio_tested") is not False
            or stage320.get("audible_dropout_verified") is not False
            or stage322.get("schema")!=HISTORY_SCHEMA
            or stage322.get("result")!=HISTORY_VERIFIED
            or stage322.get("original_guest_history_source_observed") is not True
            or stage322.get("original_guest_history_bytes_preserved") is not True
            or stage322.get("original_guest_history_source_path")!=str(SUBDIR/HISTORY_FILE)
            or stage322.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("original Stage320/322 provenance or evidence scope missing")
    if (hashlib.sha256(last).hexdigest()!=stage320.get("original_last_playbuffer_csv_sha256")
            or stage322.get("original_guest_history_csv_sha256")!=expected_history_sha):
        raise ExitTimelineError("original successful PlayBuffer sources not identity-bound")
    # The original Stage320 source was independently audited inside NeXium;
    # its CSV hash is pinned here, not all upstream stage307/310/313/317 bytes replayed.
    # Stage322's pure source audit is *re-run* against the pinned original CSV.
    reproduced=audit_source(history,stage320)
    reported={k:v for k,v in stage322.items()
              if k not in ("original_guest_history_source_observed",
                           "original_guest_history_bytes_preserved",
                           "original_guest_history_source_path")}
    if reproduced!=reported:
        raise ExitTimelineError("original Stage322 receipt differs from independently replayed CSV")
    if (reproduced["prior_successful_call_count_in_window"]!=15
            or reproduced["original_recent_call_count"]!=16
            or reproduced["original_recent_failed_return_count"]!=0
            or reproduced["final_successful_call_in_recent_window"] is not True
            or reproduced["prior_successful_duration_lower_median_guest_ns"] is None):
        raise ExitTimelineError("cannot compare two complete successful 16-call cohorts")
    if reproduced["final_call_duration_guest_ns"]>=reproduced[
            "prior_successful_duration_lower_median_guest_ns"]:
        raise ExitTimelineError("final call not shorter than original prior median")
    return reproduced


def compare(a:dict,b:dict,first_sha:str,second_sha:str)->dict:
    if first_sha==second_sha:
        raise ExitTimelineError("original guest history cohorts are not distinct")
    first=verify(a,first_sha)
    second=verify(b,second_sha)
    intervals=[]
    for label,doc in (("first",first),("second",second)):
        intervals.append({
            "cohort":label,
            "original_history_sha256":doc["original_guest_history_csv_sha256"],
            "original_last_success_sha256":doc["original_last_successful_PlayBuffer_source_sha256"],
            "normal_calls_retained":doc["original_recent_call_count"],
            "previous_success_count":doc["prior_successful_call_count_in_window"],
            "previous_lower_median_software_ns":doc[
                "prior_successful_duration_lower_median_guest_ns"],
            "last_software_ns":doc["final_call_duration_guest_ns"],
            "last_minus_previous_lower_median_ns":doc[
                "final_minus_prior_lower_median_guest_ns"],
            "last_software_is_shorter_than_prior_median":True,
        })
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "cohorts":intervals,
        "second_minus_first_last_software_ns":
            second["final_call_duration_guest_ns"]-first["final_call_duration_guest_ns"],
        "second_minus_first_prior_median_software_ns":
            second["prior_successful_duration_lower_median_guest_ns"]-
            first["prior_successful_duration_lower_median_guest_ns"],
        "each_original_stage322_receipt_recomputed_from_exact_csv":True,
        "original_stage320_summary_identity_bound_but_full_upstream_not_rerun":True,
        "each_history_is_bounded_last_16_not_full_session":True,
        "no_guest_to_host_PCM_clock_alignment":True,
        "speaker_audio_or_original_soundtrack_verified":False,
        "plus_caused_audio_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-root",required=True,type=Path)
    p.add_argument("--second-root",required=True,type=Path)
    p.add_argument("--first-history-sha256",required=True)
    p.add_argument("--second-history-sha256",required=True)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.first_root.resolve()==a.second_root.resolve():
            raise ExitTimelineError("original guest source cohort roots must be distinct")
        if a.output.is_symlink() or a.output.exists():
            raise ExitTimelineError("refuse overwrite original replay")
        result=compare(load(a.first_root),load(a.second_root),
                       a.first_history_sha256,a.second_history_sha256)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":result["result"],
            "cohorts":result["cohorts"],
            "speaker_audio_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE328_INDEPENDENT_GUEST_HISTORY_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "speaker_audio_verified":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
