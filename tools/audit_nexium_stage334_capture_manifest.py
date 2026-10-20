#!/usr/bin/env python3
"""Stage334 per-capture original guest software and host clock source manifest.

Make a NEW source-bound evidence receipt for each actual NeXium run. The
guest software timer and host PCM recorder clocks are separate; do not
synchronize, subtract or convert between them. No source PCM is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_guest_playbuffer_history import (
    audit_source,SCHEMA as HISTORY_SCHEMA,VERIFIED as HISTORY_VERIFIED,
)
from audit_nexium_guest_last_playbuffer import (
    SCHEMA as LAST_SCHEMA,VERIFIED as LAST_VERIFIED,
)
from audit_nexium_host_clock_pairs import (
    audit as audit_host,SCHEMA as HOST_SCHEMA,
    ClockPairError,
)
from audit_nexium_pcm_exit_controls import control_events

SCHEMA="vh-stage334-single-real-NeXium-guest-and-host-original-source-manifest/v1"
RESULT="ORIGINAL_GUEST_SOFTWARE_AND_HOST_CLOCK_SOURCES_INDEPENDENTLY_REPLAYED"

FILES={
    "history_csv":"audio-playbuffer-history-000.csv",
    "last_csv":"audio-last-playbuffer-000.csv",
    "stage320":"guest-last-playbuffer-stage320.json",
    "stage322":"guest-playbuffer-history-stage322.json",
    "legacy_csv":"scene-exit-controls.csv",
    "monotonic_csv":"scene-exit-controls-monotonic.csv",
    "stage325":"host-dual-clock-stage325.json",
    "stage304":"pcm-exit-controls-stage304.json",
    "stage305":"pcm-plus-onset-fence-stage305.json",
}


def load(root:Path)->dict:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("original NeXium runtime evidence directory missing")
    result={}
    for field,filename in FILES.items():
        path=root/filename
        if path.is_symlink() or not path.is_file():
            raise ExitTimelineError("source original evidence absent or symlink")
        cap=4096 if field.endswith("_csv") else 1_000_000
        if not 0<path.stat().st_size<=cap:
            raise ExitTimelineError("source original evidence file empty or oversized")
        result[field]=path.read_bytes() if field.endswith("_csv") else json.loads(
            path.read_text(encoding="utf-8"))
    return result


def audit_original_capture(source:dict)->dict:
    history=source["history_csv"]
    last=source["last_csv"]
    original320=source["stage320"]
    original322=source["stage322"]
    legacy=source["legacy_csv"]
    dual=source["monotonic_csv"]
    stage304=source["stage304"]
    stage305=source["stage305"]
    if (not isinstance(original320,dict) or not isinstance(original322,dict)
            or not isinstance(stage304,dict) or not isinstance(stage305,dict)):
        raise ExitTimelineError("original successful source receipts absent")
    if (original320.get("schema")!=LAST_SCHEMA
            or original320.get("result")!=LAST_VERIFIED
            or original320.get("original_source_bytes_preserved") is not True
            or original320.get("original_guest_playbuffer_source_observed") is not True
            or original320.get("physical_Nintendo_Switch_audio_tested") is not False
            or original320.get("audible_dropout_verified") is not False
            or original322.get("schema")!=HISTORY_SCHEMA
            or original322.get("result")!=HISTORY_VERIFIED
            or original322.get("original_guest_history_bytes_preserved") is not True
            or original322.get("original_guest_history_source_observed") is not True
            or original322.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("guest software source receipts not authentic")
    original_history_sha=hashlib.sha256(history).hexdigest()
    original_last_sha=hashlib.sha256(last).hexdigest()
    if (original322.get("original_guest_history_csv_sha256")!=original_history_sha
            or original320.get("original_last_playbuffer_csv_sha256")!=original_last_sha):
        raise ExitTimelineError("original guest source bytes differ from receipt")
    replay=audit_source(history,original320)
    stripped={k:v for k,v in original322.items()
              if k not in ("original_guest_history_source_observed",
                           "original_guest_history_bytes_preserved",
                           "original_guest_history_source_path")}
    if replay!=stripped:
        raise ExitTimelineError("original guest software Stage322 source receipt mismatched")
    host=audit_host(legacy,dual)
    if (host!=source["stage325"] or host["schema"]!=HOST_SCHEMA
            or host["wall_epoch_backwards_pair_count"]!=0
            or host["wall_epoch_equal_pair_count"]!=0
            or host["pcm_size_regression_pair_count"]!=0):
        raise ClockPairError("original Stage325 host clock source does not reconcile")
    controls=control_events(legacy)
    snapshots=stage304.get("exit_control_snapshots")
    if (stage304.get("result")!="SOURCE_BOUND_BUFFERED_EXIT_CONTROL_TIMELINE_RECONCILED"
            or stage304.get("all_original_source_witnesses_replayed") is not True
            or stage304.get("physical_Nintendo_Switch_audio_tested") is not False
            or not isinstance(snapshots,list) or len(snapshots)!=len(controls)):
        raise ExitTimelineError("strict original Stage304 source verdict missing")
    for parsed,reported in zip(controls,snapshots):
        if any(parsed[k]!=reported.get(k) for k in
               ("event","pcm_bytes","host_epoch_ms")):
            raise ExitTimelineError("original host strict Stage304 controls changed")
    if (stage305.get("result")!="SOURCE_BOUND_PLUS_BUFFERED_ZERO_RUN_ONSET_FENCED"
            or stage305.get("all_original_stage299_through_stage304_evidence_replayed") is not True
            or stage305.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("strict Stage305 original PCM source verdict missing")
    last_duration=replay["final_call_duration_guest_ns"]
    prior=[x["duration_guest_ns"] for x in replay["original_call_rows"]
           if x["lease_returned"] and
           x["sequence"]<original320["last_successful_PlayBuffer_attempt_index"]]
    # A new independent sample is not required to reproduce the old ordering.
    # A failed / absent prior-call baseline must be reported, not fabricated.
    last_in_window=replay["final_successful_call_in_recent_window"]
    baseline=replay["prior_successful_duration_lower_median_guest_ns"]
    if last_in_window and prior:
        if baseline!=median_low(prior):
            raise ExitTimelineError("original guest earlier-call baseline not reproduced")
        faster=sum(d<last_duration for d in prior)
        equal=sum(d==last_duration for d in prior)
        slower=sum(d>last_duration for d in prior)
        if faster+equal+slower!=len(prior):
            raise ExitTimelineError("guest source earlier-call counts inconsistent")
        rank=1+faster
        margin=baseline-last_duration
    else:
        faster=equal=slower=rank=margin=None
        if baseline is not None:
            raise ExitTimelineError("original receipt fabricated prior baseline")
    gaps=host["adjacent_host_clock_deltas"]
    if len(gaps)!=2:
        raise ClockPairError("original host control event pair count unexpected")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "original_guest_history_csv_sha256":original_history_sha,
        "original_guest_last_call_csv_sha256":original_last_sha,
        "original_host_legacy_csv_sha256":host["legacy_csv_sha256"],
        "original_host_monotonic_csv_sha256":host["paired_clock_csv_sha256"],
        "original_guest_normal_call_count":replay["total_original_normal_PlayBuffer_calls"],
        "original_guest_retained_call_count":replay["original_recent_call_count"],
        "original_guest_previous_successful_calls_in_window":len(prior) if last_in_window else 0,
        "original_guest_last_success_is_in_retained_window":last_in_window,
        "original_guest_last_call_duration_software_ns":last_duration,
        "original_guest_prior_lower_median_software_ns":baseline,
        "original_guest_prior_median_minus_last_software_ns":margin,
        "original_guest_prior_faster_equal_slower_counts":
            [faster,equal,slower] if rank is not None else None,
        "original_guest_last_call_first_possible_rank":rank,
        "original_host_control_deltas":[{
            "first_event":g["first_event"],
            "second_event":g["second_event"],
            "host_wall_delta_ms":g["host_wall_delta_ms"],
            "host_monotonic_delta_ns":g["host_monotonic_delta_ns"],
            "host_pcm_file_size_delta_bytes":g["pcm_file_size_delta_bytes"],
        } for g in gaps],
        "original_stage320_322_325_receipts_recomputed_from_exact_sources":True,
        "original_stage304_305_strict_success_receipts_checked":True,
        "guest_software_clock_cannot_be_subtracted_from_host_times":True,
        "host_PCM_file_length_not_sample_exact_playback":True,
        "no_absolute_guest_or_host_epochs_published":True,
        "no_guest_to_host_clock_alignment_proven":True,
        "original_soundtrack_or_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.is_symlink() or a.output.exists():
            raise ExitTimelineError("cannot overwrite original capture manifest")
        report=audit_original_capture(load(a.evidence_root))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as output:
            json.dump(report,output,sort_keys=True,indent=2)
            output.write("\n")
        print(json.dumps({"result":report["result"],
                          "guest_call_software_ns":
                              report["original_guest_last_call_duration_software_ns"],
                          "prior_median_software_ns":
                              report["original_guest_prior_lower_median_software_ns"],
                          "host_control_deltas":report["original_host_control_deltas"],
                          "hardware_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE334_ORIGINAL_GUEST_HOST_SOURCE_MANIFEST_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "hardware_audio_verified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
