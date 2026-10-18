#!/usr/bin/env python3
"""Stage291: exact 16-offset sensitivity of deterministic audout probes.

The old 1-in-16 queue-count probe observed ONLY attempts 1,17,...
Other phases have independently recorded >=40ms call durations in
the full original-guest-SD slow-call trace, but NO queue observations.
Never impute an unmeasured queue count, audio DAC state, or cause.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_audout_idle_control import original_and_copy
from audit_nexium_audout_queue import parse_telemetry
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import CorrelationError,parse_clock
from audit_nexium_audout_slow_calls import parse_slow

PHASES=16
SCHEMA="vh-nexium-systematic-slow-call-phase-sensitivity/v1"
MAPPING=(
    ("queue","audio-audout-queue-*.csv","soak-audout-sd-unverified.csv",
     "soak-audout-sd-locations.txt","soak-audout-export-result.txt"),
    ("clock","audio-audout-clock-*.csv","soak-audout-clock-unverified.csv",
     "soak-audout-clock-locations.txt","soak-audout-clock-export-result.txt"),
    ("latency","audio-audout-latency-*.csv","soak-audout-latency-unverified.csv",
     "soak-audout-latency-locations.txt","soak-audout-latency-export-result.txt"),
    ("slow","audio-audout-slow-*.csv","soak-audout-slow-unverified.csv",
     "soak-audout-slow-locations.txt","soak-audout-slow-export-result.txt"),
)


def phase_table(attempts:int, slow:list[dict], actual_probes:dict)->list[dict]:
    if type(attempts) is not int or attempts<PHASES:
        raise CorrelationError("missing complete 16 phase sampling domain")
    counts40=[0]*PHASES
    counts50=[0]*PHASES
    seen=set()
    for call in slow:
        number=call.get("attempt")
        duration=call.get("duration_ns")
        if (type(number) is not int or not 1<=number<=attempts
                or number in seen or type(duration) is not int
                or duration<40_000_000 or
                call.get("returned") is not True):
            raise CorrelationError("invalid exact historical slow call")
        seen.add(number)
        phase=(number-1)%PHASES
        counts40[phase]+=1
        if duration>=50_000_000: counts50[phase]+=1
    if not isinstance(actual_probes,dict):
        raise CorrelationError("missing current-workflow verified queue probe")
    denominators=[
        (attempts-(phase+1))//PHASES+1 for phase in range(PHASES)
    ]
    if sum(denominators)!=attempts or (
            actual_probes["sample_count"]!=denominators[0]
            or actual_probes["audout_attempts"]!=attempts
            or actual_probes["slow_call_sampled_ge40"]!=counts40[0]
            or actual_probes["slow_call_sampled_ge50"]!=counts50[0]):
        raise CorrelationError("actual 1-in-16 probe does not match exact source calls")
    result=[]
    for phase,(den,c40,c50) in enumerate(zip(
            denominators,counts40,counts50)):
        if den<=0 or not 0<=c50<=c40<=den:
            raise CorrelationError("invalid phase numerator/denominator")
        result.append({
            "phase_offset_zero_based":phase,
            "attempts_starting_at":phase+1,
            "sampled_attempts_for_this_phase":den,
            "source_slow_ge40":c40,
            "source_slow_40to50":c40-c50,
            "source_slow_ge50":c50,
            "ge40_rate_per_1000":round(float(Fraction(1000*c40,den)),6),
            "ge50_rate_per_1000":round(float(Fraction(1000*c50,den)),6),
            "queue_service_count_actually_observed":phase==0,
            "hypothetical_phase_is_NOT_queue_data":phase!=0,
        })
    if sum(r["source_slow_ge40"] for r in result)!=len(slow):
        raise CorrelationError("lost or repeated full-call slow evidence")
    return result


def audit_mode(*,sd_root:Path,evidence:Path,
               expected_attempts:int,expected_slow:int,
               expected_ge50:int,expected_slow_sha:str,
               actual_probes:dict)->dict:
    if sd_root.is_symlink():
        raise CorrelationError("alias of original guest data root")
    folder=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if folder.is_symlink() or not folder.is_dir():
        raise CorrelationError("missing independent original guest SD")
    sources={}
    for label,pattern,name,locations,receipt in MAPPING:
        sources[label]=original_and_copy(
            folder,evidence,pattern,name,locations,receipt)
    if hashlib.sha256(sources["slow"]).hexdigest()!=expected_slow_sha:
        raise CorrelationError("source is not independently audited original slow calls")
    clock=parse_clock(sources["clock"])
    queue=parse_telemetry(sources["queue"])
    latency=parse_latency(sources["latency"])
    slow=parse_slow(sources["slow"],clock["origin_ns"],latency)
    if (queue["attempts"]!=expected_attempts
            or clock["attempts"]!=expected_attempts
            or latency["attempts"]!=expected_attempts
            or len(slow)!=expected_slow
            or len(slow)!=latency["from40to50ms_calls"]+
                             latency["ge50ms_calls"]
            or sum(c["duration_ns"]>=50_000_000 for c in slow)!=expected_ge50
            or queue["queue_probes_ok"]+queue["queue_probes_failed"]!=
               actual_probes["sample_count"]):
        raise CorrelationError("phase trace does not reconcile current original-SD counts")
    table=phase_table(expected_attempts,slow,actual_probes)
    return {
        "attempts":expected_attempts,
        "slow_ge40":len(slow),
        "slow_ge50":expected_ge50,
        "original_guest_sd_slow_sha256":expected_slow_sha,
        "phase_table":table,
        "phase_zero_matches_exact_measured_probe_attempts":True,
        "full_source_call_count_conserved":True,
    }


def compare_phase_sensitivity(switch:dict,idle:dict,
                              same_nro:dict,
                              switch_slow:dict,idle_verdict:dict)->dict:
    if (same_nro.get("result")!=
            "SAME_NRO_ORIGINAL_SD_TWO_MODE_PROBE_COMPARISON_RECONCILED"
            or same_nro.get("both_original_guest_sd_audited_this_workflow") is not True
            or same_nro.get("sampled_on_exact_every_sixteenth_call") is not True
            or same_nro.get("sampling_randomized") is not False
            or same_nro.get("scene_switch_causality_proven") is not False
            or same_nro.get("physical_console_audio_measured") is not False
            or same_nro.get("nro_sha256")!=idle_verdict.get("nro_sha256")
            or same_nro.get("nro_sha256")!=switch_slow.get("nro_sha256")
            or switch_slow.get("result")!=
               "GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED"
            or idle_verdict.get("result")!=
               "ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED"):
        raise CorrelationError("Stage290 same-build source integrity is not established")
    for label,source in (("switching",switch),("idle",idle)):
        if (source["attempts"]!=same_nro[label]["audout_attempts"]
                or source["slow_ge40"]<
                   same_nro[label]["slow_call_sampled_ge40"]
                or source["slow_ge50"]<
                   same_nro[label]["slow_call_sampled_ge50"]
                or len(source["phase_table"])!=PHASES):
            raise CorrelationError("full-source phase sensitivity is not matched")
    between=[]
    positive=negative=ties=0
    for i in range(PHASES):
        a=switch["phase_table"][i]
        b=idle["phase_table"][i]
        rate=(Fraction(1000*a["source_slow_ge40"],
                       a["sampled_attempts_for_this_phase"])-
              Fraction(1000*b["source_slow_ge40"],
                       b["sampled_attempts_for_this_phase"]))
        between.append({
            "phase_offset_zero_based":i,
            "switch_minus_idle_ge40_per_1000":round(float(rate),6),
            "positive":rate>0,
            "negative":rate<0,
            "exact_tie":rate==0,
        })
        positive+=rate>0
        negative+=rate<0
        ties+=rate==0
    if positive+negative+ties!=PHASES:
        raise CorrelationError("not exactly 16 original slow-call sampling offsets")
    return {
        "schema":SCHEMA,
        "result":"ORIGINAL_SD_ALL_16_DETERMINISTIC_SAMPLE_PHASES_RECONCILED",
        "nro_sha256":same_nro["nro_sha256"],
        "switching":switch,
        "idle":idle,
        "same_phase_comparisons":between,
        "phase_positive_count":positive,
        "phase_negative_count":negative,
        "phase_exact_tie_count":ties,
        "observed_real_queue_query_phase":0,
        "other_phase_queue_counts_are_NOT_measured":True,
        "full_slow_call_histogram_exactly_partitioned":True,
        "both_original_guest_sd_reopened_this_workflow":True,
        "music_switch_session_always_preceded_idle":True,
        "phase_offset_exploration_not_independent_experiments":True,
        "hypothetical_phase_slow_durations_only":True,
        "audio_scheduler_DAC_or_audible_underruns_measured":False,
        "scene_causality_proven":False,
        "physical_switch_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in (
        "switch-sd-root","idle-sd-root","switch-evidence","idle-evidence",
        "stage290-report","switch-slow-report","idle-verdict","output"
    ):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refuse overwriting previously verified phase report")
        def read(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        verified=read(a.stage290_report)
        slow=read(a.switch_slow_report)
        idle_verdict=read(a.idle_verdict)
        switch=audit_mode(
            sd_root=a.switch_sd_root,evidence=a.switch_evidence,
            expected_attempts=slow["audout_attempts"],
            expected_slow=slow["slow_calls_captured"],
            expected_ge50=slow["slow_ge50ms_count"],
            expected_slow_sha=slow["guest_sd_slow_sha256"],
            actual_probes=verified["switching"])
        idle=audit_mode(
            sd_root=a.idle_sd_root,evidence=a.idle_evidence,
            expected_attempts=idle_verdict["guest_audout_attempts"],
            expected_slow=idle_verdict["slow_ge40ms_calls"],
            expected_ge50=idle_verdict["slow_ge50ms_calls"],
            expected_slow_sha=idle_verdict["idle_guest_sd_sha256"]["slow"],
            actual_probes=verified["idle"])
        result=compare_phase_sensitivity(
            switch,idle,verified,slow,idle_verdict)
        a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "positive_phases":result["phase_positive_count"],
            "negative_phases":result["phase_negative_count"],
            "actual_phase_zero_delta":
                result["same_phase_comparisons"][0]["switch_minus_idle_ge40_per_1000"],
            "range_across_16_original_call_duration_phases":[
                min(v["switch_minus_idle_ge40_per_1000"] for v in
                    result["same_phase_comparisons"]),
                max(v["switch_minus_idle_ge40_per_1000"] for v in
                    result["same_phase_comparisons"])],
            "other_phase_queue_counts_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError) as exc:
        print(json.dumps({"result":"PHASE_SENSITIVITY_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
