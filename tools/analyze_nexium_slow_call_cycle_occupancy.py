#!/usr/bin/env python3
"""Stage293: original guest SD 16-call audout latency-cluster accounting.

Each cycle is a consecutive block of at most 16 submitted audout calls.
Only phase zero had a pre-submit SERVICE queue-count query. All ≥40 ms
software call durations were captured separately, so this analysis
can locate slow calls *outside* that deterministic query sample.
No queue values for unqueried attempts, OS scheduler events or DAC
underruns are inferred.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_probe_phase_sensitivity import (
    audit_mode, compare_phase_sensitivity, phase_table
)
from analyze_nexium_phase_selection_gap import analyse_selection_gap
from audit_nexium_audout_idle_control import original_and_copy
from audit_nexium_audout_scene_correlation import CorrelationError, parse_clock
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_slow_calls import parse_slow

SCHEMA="vh-nexium-audout-deterministic-16-call-cycle-occupancy/v1"
CYCLE_WIDTH=16


def cycle_profile(attempts:int, calls:list[dict], verified_mode:dict,
                  actual_probes:dict)->dict:
    if (type(attempts) is not int or attempts<CYCLE_WIDTH
            or verified_mode.get("attempts")!=attempts
            or not isinstance(calls,list)):
        raise CorrelationError("unbound original audout attempt sequence")
    if phase_table(attempts,calls,actual_probes)!=verified_mode.get("phase_table"):
        raise CorrelationError("slow-call phase counters disagree with original SD")
    count=(attempts+CYCLE_WIDTH-1)//CYCLE_WIDTH
    cycles=[]
    for index in range(count):
        first=index*CYCLE_WIDTH+1
        last=min((index+1)*CYCLE_WIDTH,attempts)
        cycles.append({
            "cycle_index_zero_based":index,
            "first_attempt":first,
            "last_attempt":last,
            "attempts_in_cycle":last-first+1,
            "slow_ge40":0,
            "slow_40to50":0,
            "slow_ge50":0,
            "slow_at_actual_queue_probe_phase0":0,
            "slow_on_unqueried_phases_1_to_15":0,
        })
    prev_attempt=0
    prev_ns=-1
    consecutive_slow=0
    separated_by_16=0
    for call in calls:
        n=call.get("attempt")
        begin=call.get("begin_ns")
        duration=call.get("duration_ns")
        # Stage291 itself demands returned=True; the call-begin time
        # comes from the original, audited guest slow-call CSV.
        if (type(n) is not int or not 1<=n<=attempts
                or n<=prev_attempt or type(duration) is not int
                or duration<40_000_000 or call.get("returned") is not True
                or type(begin) is not int or begin<=prev_ns):
            raise CorrelationError("nonmonotone/failed slow-call source row")
        if prev_attempt:
            consecutive_slow+=n-prev_attempt==1
            separated_by_16+=n-prev_attempt==16
        row=cycles[(n-1)//CYCLE_WIDTH]
        row["slow_ge40"]+=1
        row["slow_ge50"]+=duration>=50_000_000
        row["slow_40to50"]+=duration<50_000_000
        if (n-1)%CYCLE_WIDTH==0:
            row["slow_at_actual_queue_probe_phase0"]+=1
        else:
            row["slow_on_unqueried_phases_1_to_15"]+=1
        prev_attempt=n
        prev_ns=begin

    if (sum(x["attempts_in_cycle"] for x in cycles)!=attempts
            or sum(x["slow_ge40"] for x in cycles)!=verified_mode["slow_ge40"]
            or sum(x["slow_ge50"] for x in cycles)!=verified_mode["slow_ge50"]
            or sum(x["slow_at_actual_queue_probe_phase0"] for x in cycles)!=
                actual_probes["slow_call_sampled_ge40"]):
        raise CorrelationError("original source slow calls not conserved in 16-call cycles")

    streak=longest=0
    for row in cycles:
        if (not 0<=row["slow_ge50"]<=row["slow_ge40"]<=row["attempts_in_cycle"]
                or row["slow_ge40"]!=row["slow_40to50"]+row["slow_ge50"]
                or row["slow_ge40"]!=row["slow_at_actual_queue_probe_phase0"]+
                     row["slow_on_unqueried_phases_1_to_15"]
                or row["slow_at_actual_queue_probe_phase0"]>1):
            raise CorrelationError("invalid call-index cycle duration partition")
        streak=streak+1 if row["slow_ge40"] else 0
        longest=max(longest,streak)

    populated=sum(row["slow_ge40"]>0 for row in cycles)
    phase0_populated=sum(row["slow_at_actual_queue_probe_phase0"]>0
                         for row in cycles)
    unseen=sum(row["slow_ge40"]>0 and
               row["slow_at_actual_queue_probe_phase0"]==0 for row in cycles)
    if populated!=phase0_populated+unseen:
        raise CorrelationError("slow-cycle phase-zero coverage is inconsistent")
    return {
        "audout_attempts":attempts,
        "cycle_width_attempts":CYCLE_WIDTH,
        "total_cycles":count,
        "full_cycles":attempts//CYCLE_WIDTH,
        "final_partial_cycle_attempts":attempts%CYCLE_WIDTH,
        "cycles_with_any_ge40":populated,
        "cycles_with_multiple_ge40":sum(row["slow_ge40"]>=2 for row in cycles),
        "cycles_with_ge50":sum(row["slow_ge50"]>0 for row in cycles),
        "cycles_with_slow_at_actual_phase0":phase0_populated,
        "cycles_with_slow_only_off_actual_phase0":unseen,
        "slow_calls_at_actual_phase0":sum(
            row["slow_at_actual_queue_probe_phase0"] for row in cycles),
        "slow_calls_on_unqueried_phases":sum(
            row["slow_on_unqueried_phases_1_to_15"] for row in cycles),
        "max_ge40_in_one_cycle":max(row["slow_ge40"] for row in cycles),
        "longest_run_of_cycles_with_ge40":longest,
        "adjacent_slow_call_attempt_pairs":consecutive_slow,
        "slow_call_pairs_exactly_16_attempts_apart":separated_by_16,
        "cycles":cycles,
        "phase0_queue_query_values_available":True,
        "other_phases_queue_values_available":False,
    }


def analyse_cycle_occupancy(stage291:dict,stage290:dict,stage292:dict,
                            switching_calls:list[dict],idle_calls:list[dict])->dict:
    expected=analyse_selection_gap(stage291,stage290)
    if stage292!=expected:
        raise CorrelationError("Stage292 source witness does not reproduce")
    if (stage291.get("result") !=
            "ORIGINAL_SD_ALL_16_DETERMINISTIC_SAMPLE_PHASES_RECONCILED"):
        raise CorrelationError("missing verified guest service sample phases")
    inputs={"switching":switching_calls,"idle":idle_calls}
    modes={}
    for mode in ("switching","idle"):
        modes[mode]=cycle_profile(
            stage291[mode]["attempts"],inputs[mode],
            stage291[mode],stage290[mode])
        if (modes[mode]["slow_calls_at_actual_phase0"]!=
                stage292["modes"][mode]["ge40"]["actual_phase0_slow_call_count"]
                or modes[mode]["slow_calls_on_unqueried_phases"]+
                   modes[mode]["slow_calls_at_actual_phase0"]!=
                   stage292["modes"][mode]["ge40"]["full_session_slow_call_count"]):
            raise CorrelationError("cycle distribution differs from Stage292")
    rate=(
        Fraction(1000*modes["switching"]["cycles_with_any_ge40"],
                 modes["switching"]["total_cycles"])-
        Fraction(1000*modes["idle"]["cycles_with_any_ge40"],
                 modes["idle"]["total_cycles"])
    )
    return {
        "schema":SCHEMA,
        "result":"SOURCE_ORIGINAL_SD_16_CALL_LATENCY_CYCLES_RECONCILED",
        "nro_sha256":stage291["nro_sha256"],
        "switching":modes["switching"],
        "idle":modes["idle"],
        "switch_minus_idle_nonempty_cycle_rate_per_1000_cycles":
            round(float(rate),6),
        "stage292_exactly_recomputed_from_current_original_SD":True,
        "phase0_measures_queue_pre_submit_not_during_blocking":True,
        "unqueried_phase_queue_values_imputed":False,
        "cycle_occupancy_not_scheduler_execution_timing":True,
        "cycle_groups_not_independent_randomized_experiments":True,
        "switching_capture_preceded_idle":True,
        "physical_console_playback_verified":False,
        "OS_scheduler_events_or_DAC_underruns_measured":False,
        "musical_scene_switch_causality_proven":False,
    }


def _read_calls(sd_root:Path,evidence:Path,verified_mode:dict)->list[dict]:
    directory=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if (sd_root.is_symlink() or directory.is_symlink()
            or not directory.is_dir()):
        raise CorrelationError("source SD aliases or is absent")
    sources={}
    for label,pattern,name,locations,receipt in (
        ("clock","audio-audout-clock-*.csv","soak-audout-clock-unverified.csv",
         "soak-audout-clock-locations.txt","soak-audout-clock-export-result.txt"),
        ("latency","audio-audout-latency-*.csv","soak-audout-latency-unverified.csv",
         "soak-audout-latency-locations.txt","soak-audout-latency-export-result.txt"),
        ("slow","audio-audout-slow-*.csv","soak-audout-slow-unverified.csv",
         "soak-audout-slow-locations.txt","soak-audout-slow-export-result.txt"),
    ):
        sources[label]=original_and_copy(
            directory,evidence,pattern,name,locations,receipt)
    if hashlib.sha256(sources["slow"]).hexdigest()!=(
            verified_mode["original_guest_sd_slow_sha256"]):
        raise CorrelationError("source original-SD slow trace hash differs")
    clock=parse_clock(sources["clock"])
    latency=parse_latency(sources["latency"])
    calls=parse_slow(sources["slow"],clock["origin_ns"],latency)
    if (latency["attempts"]!=verified_mode["attempts"]
            or len(calls)!=verified_mode["slow_ge40"]):
        raise CorrelationError("slow calls differ from guest-original Stage291 report")
    return calls


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("switch-sd-root","idle-sd-root","switch-evidence","idle-evidence",
                 "stage290-report","stage291-report","stage292-report",
                 "switch-slow-report","idle-verdict","output"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse to overwrite 16-call latency report")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        stage290=load(args.stage290_report)
        prior291=load(args.stage291_report)
        slow=load(args.switch_slow_report)
        idle=load(args.idle_verdict)
        switch_mode=audit_mode(
            sd_root=args.switch_sd_root,evidence=args.switch_evidence,
            expected_attempts=slow["audout_attempts"],
            expected_slow=slow["slow_calls_captured"],
            expected_ge50=slow["slow_ge50ms_count"],
            expected_slow_sha=slow["guest_sd_slow_sha256"],
            actual_probes=stage290["switching"])
        idle_mode=audit_mode(
            sd_root=args.idle_sd_root,evidence=args.idle_evidence,
            expected_attempts=idle["guest_audout_attempts"],
            expected_slow=idle["slow_ge40ms_calls"],
            expected_ge50=idle["slow_ge50ms_calls"],
            expected_slow_sha=idle["idle_guest_sd_sha256"]["slow"],
            actual_probes=stage290["idle"])
        verified291=compare_phase_sensitivity(
            switch_mode,idle_mode,stage290,slow,idle)
        if verified291!=prior291:
            raise CorrelationError("Stage291 audit not reproducible from original SD")
        result=analyse_cycle_occupancy(
            verified291,stage290,load(args.stage292_report),
            _read_calls(args.switch_sd_root,args.switch_evidence,switch_mode),
            _read_calls(args.idle_sd_root,args.idle_evidence,idle_mode))
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "switch_cycles_with_slow":result["switching"]["cycles_with_any_ge40"],
            "idle_cycles_with_slow":result["idle"]["cycles_with_any_ge40"],
            "switch_cycles_with_slow_not_at_phase0":
                result["switching"]["cycles_with_slow_only_off_actual_phase0"],
            "idle_cycles_with_slow_not_at_phase0":
                result["idle"]["cycles_with_slow_only_off_actual_phase0"],
            "hardware_audio_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"16_CALL_SLOW_CYCLE_ORIGINAL_SD_NOT_VERIFIED",
            "error":str(exc)
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
