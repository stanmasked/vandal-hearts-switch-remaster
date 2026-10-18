#!/usr/bin/env python3
"""Stage290: current-NRO original-SD-bound idle/switch audout probe comparison.

Every recorded queue count is a PRE-SUBMIT audio service snapshot.
The 1-in-16 sampling is deterministic, NOT random. Neither zeros
nor associations with >=40ms calls prove scheduler/DAC/underrun behavior.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_audout_idle_control import (
    original_and_copy,parse_idle_scene
)
from audit_nexium_audout_queue import parse_telemetry
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock
)
from audit_nexium_audout_slow_calls import parse_slow
from audit_nexium_audout_service_probes import parse_probes

SCHEMA="vh-nexium-idle-switch-same-nro-service-probes/v1"


def _verified_observations(report:dict, *, source_mode:str)->dict:
    if (report.get("result")!="GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED"
            or report.get("queue_probe_dropped")!=0
            or report.get("scheduler_or_DAC_state_measured") is not False
            or report.get("physical_switch_tested") is not False
            or report.get("audible_underruns_measured") is not False
            or report.get("pre_submit_queue_service_snapshot_only") is not True):
        raise CorrelationError("not a complete original-SD verified service probe trace")
    samples=report.get("sample_records")
    slows=report.get("probed_slow_calls")
    if (not isinstance(samples,list) or not samples
            or not isinstance(slows,list)
            or report["queue_probe_samples"]!=len(samples)
            or report["queue_probe_successes"]+
               report["queue_probe_failures"]!=len(samples)
            or (report["audout_attempts"]+15)//16!=len(samples)):
        raise CorrelationError("incomplete or inconsistent sampled service cohort")
    indexes=set()
    succeeded=0
    failed=0
    observed_counts=Counter()
    for index,entry in enumerate(samples):
        if (entry["index"]!=index or
                entry["attempt"]!=1+16*index or
                entry["attempt"] in indexes or
                type(entry["submit_begin_ns"]) is not int or
                entry["submit_begin_ns"]<=0):
            raise CorrelationError("noncanonical sampled service attempt identity")
        indexes.add(entry["attempt"])
        if entry["query_succeeded"] is True:
            count=entry["pre_submit_queue_count"]
            if type(count) is not int or count<0:
                raise CorrelationError("invalid service pre-submit buffer count")
            observed_counts[count]+=1
            succeeded+=1
        elif entry["query_succeeded"] is False and (
                entry["pre_submit_queue_count"] is None):
            failed+=1
        else:
            raise CorrelationError("service count lacks valid query result")
    if (succeeded!=report["queue_probe_successes"]
            or failed!=report["queue_probe_failures"]):
        raise CorrelationError("recorded query outcomes fail summary")
    slow_ids=set()
    durations=[]
    for row in slows:
        attempt=row["attempt"]
        if (attempt not in indexes or attempt in slow_ids
                or type(row["duration_ns"]) is not int
                or row["duration_ns"]<40_000_000):
            raise CorrelationError("unverified slow call on sampled service attempt")
        original=next(x for x in samples if x["attempt"]==attempt)
        if any(row[k]!=original[k] for k in (
                "index","submit_begin_ns","audio_second",
                "query_succeeded","pre_submit_queue_count")):
            raise CorrelationError("sampled slow call does not match probe timestamp")
        slow_ids.add(attempt)
        durations.append(row["duration_ns"])
    return {
        "source_mode":source_mode,
        "audout_attempts":report["audout_attempts"],
        "sample_count":len(samples),
        "query_success_count":succeeded,
        "query_failure_count":failed,
        "pre_submit_service_count_histogram":{
            str(k):v for k,v in sorted(observed_counts.items())
        },
        "zero_queue_service_count_samples":observed_counts[0],
        "slow_call_sampled_ge40":len(durations),
        "slow_call_sampled_40to50":sum(
            40_000_000<=d<50_000_000 for d in durations),
        "slow_call_sampled_ge50":sum(d>=50_000_000 for d in durations),
        "slow_call_sample_rate_ge40_per_1000":round(
            1000*len(durations)/len(samples),6),
        "deterministic_one_in_16_not_random_sampling":True,
    }


def verify_idle_probes(*,sd_root:Path, evidence:Path,
                       historical_verdict:dict)->dict:
    if (historical_verdict.get("result")!="ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED"
            or historical_verdict.get("original_sd_verified_during_run") is not True
            or historical_verdict.get("guest_scene_change_inputs")!=0
            or historical_verdict.get("physical_switch_tested") is not False):
        raise CorrelationError("current-run idle control itself not SD verified")
    folder=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if (not sd_root.is_dir() or sd_root.is_symlink()
            or not folder.is_dir() or folder.is_symlink()):
        raise CorrelationError("missing separate original idle guest SD")
    descriptors={
        "scene":("audio-scene-trace-*.csv","soak-sd-unverified.csv",
                 "soak-sd-locations.txt",None),
        "queue":("audio-audout-queue-*.csv","soak-audout-sd-unverified.csv",
                 "soak-audout-sd-locations.txt","soak-audout-export-result.txt"),
        "latency":("audio-audout-latency-*.csv","soak-audout-latency-unverified.csv",
                   "soak-audout-latency-locations.txt",
                   "soak-audout-latency-export-result.txt"),
        "clock":("audio-audout-clock-*.csv","soak-audout-clock-unverified.csv",
                 "soak-audout-clock-locations.txt",
                 "soak-audout-clock-export-result.txt"),
        "slow":("audio-audout-slow-*.csv","soak-audout-slow-unverified.csv",
                "soak-audout-slow-locations.txt",
                "soak-audout-slow-export-result.txt"),
        "probe":("audio-audout-probe-*.csv","soak-audout-probe-unverified.csv",
                 "soak-audout-probe-locations.txt",
                 "soak-audout-probe-export-result.txt"),
    }
    sources={}
    for label,(pattern,copy,locations,receipt) in descriptors.items():
        sources[label]=original_and_copy(
            folder,evidence,pattern,copy,locations,receipt)
        if label!="probe" and (
            hashlib.sha256(sources[label]).hexdigest()!=
            historical_verdict["idle_guest_sd_sha256"][label]):
            raise CorrelationError("idle source differs from independently audited original")
    clock=parse_clock(sources["clock"])
    queue=parse_telemetry(sources["queue"])
    latency=parse_latency(sources["latency"])
    slow=parse_slow(sources["slow"],clock["origin_ns"],latency)
    parse_idle_scene(sources["scene"],clock["origin_ns"])
    if (queue["attempts"]!=historical_verdict["guest_audout_attempts"]
            or latency["attempts"]!=queue["attempts"]
            or len(slow)!=historical_verdict["slow_ge40ms_calls"]
            or sum(x["duration_ns"]>=50_000_000 for x in slow)!=
                  historical_verdict["slow_ge50ms_calls"]):
        raise CorrelationError("idle original guest slow calls do not reconcile")
    result=parse_probes(sources["probe"],clock,queue,latency,slow)
    result.update({
        "scene_input_count":0,
        "probe_original_sd_sha256":hashlib.sha256(sources["probe"]).hexdigest(),
        "idle_original_sd_reverified_current_run":True,
        "idle_scene_stable_not_just_no_key_events":True,
    })
    return result


def compare_modes(switch_report:dict,idle_report:dict,
                  switch_slow:dict,idle_verdict:dict)->dict:
    if (idle_report.get("idle_original_sd_reverified_current_run") is not True
            or idle_report.get("scene_input_count")!=0
            or switch_report.get("original_guest_sd_opened_in_current_workflow") is not True
            or switch_report.get("scene_input_count")!=10
            or switch_report.get("guest_original_probe_sha256")!=
               switch_report.get("copied_probe_sha256")
            or switch_report.get("result")!="GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED"
            or switch_slow.get("result")!="GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED"
            or idle_verdict.get("result")!="ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED"
            or idle_verdict.get("nro_sha256")!=switch_slow.get("nro_sha256")
            or idle_verdict.get("physical_switch_tested") is not False):
        raise CorrelationError("two original-SD modes do not bind to one current NRO")
    switch=_verified_observations(switch_report,source_mode="ten_scene_INPUTs")
    idle=_verified_observations(idle_report,source_mode="zero_scene_INPUTs")
    if (switch["audout_attempts"]!=switch_slow["audout_attempts"]
            or idle["audout_attempts"]!=idle_verdict["guest_audout_attempts"]
            or switch["slow_call_sampled_ge40"]>
                switch_slow["slow_calls_captured"]
            or idle["slow_call_sampled_ge40"]>
                idle_verdict["slow_ge40ms_calls"]
            or switch["slow_call_sampled_ge50"]>
                switch_slow["slow_ge50ms_count"]
            or idle["slow_call_sampled_ge50"]>
                idle_verdict["slow_ge50ms_calls"]):
        raise CorrelationError("sampled slow calls cannot be linked to full traces")
    return {
        "schema":SCHEMA,
        "result":"SAME_NRO_ORIGINAL_SD_TWO_MODE_PROBE_COMPARISON_RECONCILED",
        "nro_sha256":switch_slow["nro_sha256"],
        "switching":switch,
        "idle":idle,
        "switch_guest_scene_inputs":10,
        "idle_guest_scene_inputs":0,
        "switch_pre_submit_probe_near_scene_input_count":
            switch_report["probe_samples_begin_within_500ms_of_input"],
        "both_original_guest_sd_audited_this_workflow":True,
        "capture_order":"switch_first_then_idle",
        "sampled_on_exact_every_sixteenth_call":True,
        "sampling_randomized":False,
        "queue_service_pre_submit_only":True,
        "queue_zero_is_NOT_DAC_underrun_proof":True,
        "operating_system_scheduler_events_measured":False,
        "physical_console_audio_measured":False,
        "scene_switch_causality_proven":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("switch-probe-report","switch-slow-report","idle-report",
                "idle-sd-root","idle-evidence","output"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refuse overwrite of original-SD mode comparison")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        previous=load(a.idle_report)
        idle=verify_idle_probes(
            sd_root=a.idle_sd_root,evidence=a.idle_evidence,
            historical_verdict=previous)
        result=compare_modes(load(a.switch_probe_report),idle,
                             load(a.switch_slow_report),previous)
        a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "switch_probes":result["switching"]["sample_count"],
            "idle_probes":result["idle"]["sample_count"],
            "switch_sampled_slow_ge40":result["switching"]["slow_call_sampled_ge40"],
            "idle_sampled_slow_ge40":result["idle"]["slow_call_sampled_ge40"],
            "switch_service_hist":result["switching"]["pre_submit_service_count_histogram"],
            "idle_service_hist":result["idle"]["pre_submit_service_count_histogram"],
            "hardware_measured":False,
        },sort_keys=True))
        return 0
    except (ValueError,OSError,UnicodeError,TypeError) as exc:
        print(json.dumps({"result":"TWO_MODE_SERVICE_PROBE_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
