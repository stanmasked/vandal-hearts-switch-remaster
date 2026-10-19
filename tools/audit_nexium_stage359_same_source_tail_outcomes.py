#!/usr/bin/env python3
"""Stage359: compare authenticated real wait timeout / return on SAME worker blob.

Re-download both ORIGINAL NeXium archives, re-audit their original
Stage313/348/351/357 sources & receipts; do not manufacture a matched
experiment, event queue depth, DAC behavior, or acoustic outcome.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_stage350_original_tail_vs_lease import safe_file
from audit_nexium_stage352_three_original_tail_sources import (
    reaudited_archive, VERIFIED as TRIPLE_VERIFIED,
)
from audit_nexium_guest_tail_wait_result_stage357 import (
    parse_source as reaudited_wait, VERIFIED as WAIT_VERIFIED,
)
from audit_nexium_stage358_original_kernel_timeout import STAGE357_FIELDS

FAIL_RUN=39325440778
OK_RUN=39326719578
AUDIO_BLOB="12c02352ac8b34e6357e68cac31e20e9a4630520"
WAIT_NS=12000000
PINS={
    FAIL_RUN:{
        "tail":"6ae164f7e6b2435c9ebb0126f56e74bc7ef87faa19277a198ce9af2009158ea2",
        "lease":"48bef5d972d87aa4c43b71470dc637b6b0f32e0de6d819b9a3723ebf11850a41",
        "reason":"118d734cf6739d9b053a78b8f4fc0b285c6df84461195a1705e25fe14cf8101e",
        "wait":"a1694b18ba05fa9715ae29c08a1fdc8f2836001264fe449bbc5ca2b834e8b57a",
    },
    OK_RUN:{
        "tail":"0c5a0dfb62d8538aa735ccb1824a2e871eb5729f9fbcf9d4c656c120b44bdb6c",
        "lease":"291a4ce56aff57b230649779ff9f53b170b5a4ee0c5465f14a2ac34cb882f3d1",
        "reason":"cec14c65148460c1424090562ce5890e476cfbd8367932d65f047ab2de6cb457",
        "wait":"298997cc46abb7377d106397651b4ed01cd6304690fa6b45b8900231c350d6e0",
    },
}
NAMES={
    "tail":"audio-exit-output-000.csv",
    "lease":"audio-lease-reconciliation-000.csv",
    "reason":"audio-exit-tail-reason-000.csv",
    "wait":"audio-exit-tail-wait-result-000.csv",
    "stage313":"guest-last-audout-release-stage313.json",
    "stage314":"guest-original-audout-last-page-stage314.json",
    "stage348":"guest-lease-reconciliation-stage348.json",
    "stage351":"guest-exit-tail-reason-stage351.json",
    "stage357":"guest-exit-tail-wait-result-stage357.json",
}
VERIFIED="TWO_ORIGINAL_NEIXUM_TAIL_RESULTS_ON_IDENTICAL_12MS_WORKER_REAUDITED"

def exact_file(root:Path,name:str)->Path:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("original evidence root is absent or linked")
    matches=list(root.rglob(name))
    if len(matches)!=1:
        raise ValueError("missing or ambiguous original source "+name)
    safe_file(matches[0])
    return matches[0]

def tail_elapsed(raw:bytes)->int|None:
    # Stage352 has *already* verified this original canonical Stage313 CSV
    # and its SHA against Stage313/314 receipts; these are only derived
    # software-monotonic observations, never a DAC/audout queue metric.
    rows=raw.decode("ascii").splitlines()
    if not rows or rows[0]!="event,value":
        raise ValueError("Stage313 original chronology missing")
    fields={}
    for row in rows[1:]:
        label,number=row.split(",")
        if (label in fields or not number.isdecimal()
            or (len(number)>1 and number[0]=="0")):
            raise ValueError("Stage313 numeric chronology invalid")
        fields[label]=int(number)
    begin=fields["tail_attempt_guest_ns"]
    done=fields["tail_success_return_guest_ns"]
    if begin<=0 or (done>0 and done<begin):
        raise ValueError("Stage313 actual attempt chronology invalid")
    return done-begin if done else None

def replay(root:Path,run:int)->dict:
    if run not in (FAIL_RUN,OK_RUN):
        raise ValueError("unknown pinned real NeXium archive")
    paths={key:exact_file(root,name) for key,name in NAMES.items()}
    pins=PINS[run]
    for key in ("tail","lease","reason","wait"):
        if hashlib.sha256(paths[key].read_bytes()).hexdigest()!=pins[key]:
            raise ValueError("different original guest bytes for "+key)
    triple=reaudited_archive(
        {k:paths[k] for k in ("tail","lease","reason","stage313",
                              "stage314","stage348","stage351")},
        {k:pins[k] for k in ("tail","lease","reason")},run)
    if (triple.get("result")!=TRIPLE_VERIFIED
        or triple.get("original_neXium_run_id")!=run):
        raise ValueError("real original Stage352 source proof not recovered")
    old351=json.loads(paths["stage351"].read_text(encoding="utf-8"))
    stamped=json.loads(paths["stage357"].read_text(encoding="utf-8"))
    source=paths["wait"].read_bytes()
    observed=reaudited_wait(source,old351)
    observed["original_guest_source_relative_path"]=(
        "sdmc/switch/vandal-hearts-remake/audio-exit-tail-wait-result-000.csv")
    for field in STAGE357_FIELDS:
        if (field not in observed
            or type(stamped.get(field)) is not type(observed[field])
            or stamped[field]!=observed[field]):
            raise ValueError("Stage357 original receipt differs from re-audited bytes")
    if (observed["original_guest_wait_result_csv_sha256"]!=pins["wait"]
        or observed["original_stage351_source_sha256"]!=pins["reason"]
        or observed["stage351_reason_code"]!=triple["tail_reason_code"]
        or observed["raw_result_is_software_service_status_only"] is not True
        or observed["physical_Nintendo_Switch_audio_tested"] is not False):
        raise ValueError("Stage357 source is not bound to its original Stage351")
    return {
        "run_id":run,
        "source_sha256":dict(pins),
        "code":triple["tail_reason_code"],
        "reason":triple["tail_reason_name"],
        "raw_result":observed["audout_wait_result_raw"],
        "wait_observed":observed["wait_result_observed"],
        "tail_return_confirmed":triple["tail_descriptor_return_confirmed"],
        "acquired":triple["lease_pages_acquired"],
        "released":triple["lease_pages_released"],
        "abandoned":triple["abandoned_sessions"],
        "software_tail_attempt_to_return_ns":
            tail_elapsed(paths["tail"].read_bytes()),
        "all_original_guest_sources_reaudited":True,
        "hardware_audio_verified":False,
    }

def compare(failed:dict,success:dict,blob1:str,blob2:str)->dict:
    if (blob1!=AUDIO_BLOB or blob2!=AUDIO_BLOB
        or not re.fullmatch("[a-f0-9]{40}",blob1)):
        raise ValueError("different or unauthenticated original audio worker blobs")
    for p,run,code,raw,a,r,z,name,confirmed in (
        (failed,FAIL_RUN,4,59905,1414,1413,1,"wait_failed",False),
        (success,OK_RUN,7,0,1366,1366,0,"return_confirmed",True),
    ):
        if (type(p.get("run_id")) is not int or p["run_id"]!=run
            or p.get("source_sha256")!=PINS[run]
            or type(p.get("code")) is not int or p["code"]!=code
            or p.get("reason")!=name
            or type(p.get("raw_result")) is not int or p["raw_result"]!=raw
            or type(p.get("acquired")) is not int or p["acquired"]!=a
            or type(p.get("released")) is not int or p["released"]!=r
            or type(p.get("abandoned")) is not int or p["abandoned"]!=z
            or p.get("wait_observed") is not True
            or p.get("tail_return_confirmed") is not confirmed
            or p.get("all_original_guest_sources_reaudited") is not True
            or p.get("hardware_audio_verified") is not False):
            raise ValueError("unverified or mismatched real guest software cohort")
    if failed.get("software_tail_attempt_to_return_ns") is not None:
        raise ValueError("failed tail must not fabricate successful release timestamp")
    measured=success.get("software_tail_attempt_to_return_ns")
    if type(measured) is not int or measured<0:
        raise ValueError("successful original tail requires monotonic release")
    return {
        "schema":"vh-stage359-same-audio-source-two-original-tail-outcomes/v1",
        "result":VERIFIED,
        "original_failed":failed,
        "original_succeeded":success,
        "first_source_commit":"3ecf5933d913b449148edd510f21e7bde7af4e90",
        "second_source_commit":"95b40a11d4dd98bbbe8c0f73e11486d7dd57ef69",
        "both_original_audio_worker_git_blob":AUDIO_BLOB,
        "both_original_tail_wait_bound_ns":WAIT_NS,
        "different_original_software_PCM_page_counts":True,
        "same_audio_worker_source_not_matched_queue_or_scheduler_state":True,
        "failed_tail_actual_return_timestamp_observed":False,
        "failed_wait_kernel_timeout_result_verified":True,
        "success_wait_zero_result_verified":True,
        "causal_scheduler_explanation_proven":False,
        "matched_controlled_experiment_completed":False,
        "DAC_or_speaker_playback_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--failure-root",type=Path,required=True)
    p.add_argument("--success-root",type=Path,required=True)
    p.add_argument("--first-worker-blob",required=True)
    p.add_argument("--second-worker-blob",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("Stage359 receipt is exclusive")
        failed=replay(a.failure_root,FAIL_RUN)
        succeeded=replay(a.success_root,OK_RUN)
        doc=compare(failed,succeeded,a.first_worker_blob,a.second_worker_blob)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(x.is_symlink() for x in (a.output,*a.output.parents)):
            raise ValueError("Stage359 receipt parent is linked")
        with a.output.open("x",encoding="utf-8") as dst:
            json.dump(doc,dst,indent=2,sort_keys=True)
            dst.write("\n")
        print(json.dumps({
            "result":VERIFIED,
            "first_raw_result":failed["raw_result"],
            "second_raw_result":succeeded["raw_result"],
            "same_audio_worker_source":True,
            "failure_cause_scheduler_proven":False,
            "physical_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"ORIGINAL_STAGE359_COHORTS_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_tested":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
