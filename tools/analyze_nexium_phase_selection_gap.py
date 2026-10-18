#!/usr/bin/env python3
"""Stage292: exact deterministic probe-phase versus whole-stream rate gap.

No missing audio-service queue counts are inferred for phases 1..15.
All slow-call counts and denominators come from the SAME original-
guest-SD-backed stage291 report, regenerated from guest SD in this job.
Any "bias" below is descriptive phase selection discrepancy, not a
statistical estimator bias, DAC underrun, causation or hardware result.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from analyze_nexium_probe_phase_sensitivity import (
    PHASES, audit_mode, compare_phase_sensitivity
)
from audit_nexium_audout_scene_correlation import CorrelationError

SCHEMA="vh-nexium-deterministic-slow-call-phase-selection-gap/v1"
BANDS=("ge40","between40and50","ge50")
MODES=("switching","idle")
COUNTER={
    "ge40":"source_slow_ge40",
    "between40and50":"source_slow_40to50",
    "ge50":"source_slow_ge50",
}


def _rate(count:int,attempts:int)->Fraction:
    if (type(count) is not int or type(attempts) is not int
            or attempts<=0 or not 0<=count<=attempts):
        raise CorrelationError("invalid exact slow-call rate fraction")
    return Fraction(1000*count,attempts)


def _out(value:Fraction)->float:
    return round(float(value),6)


def _mode_phase_rates(record:dict)->dict:
    source=record["phase_table"]
    attempts=record["attempts"]
    if (type(attempts) is not int or attempts<PHASES
            or not isinstance(source,list) or len(source)!=PHASES):
        raise CorrelationError("missing source all-attempt 16-offset phase table")
    tallies={}
    phase_ratios={}
    for band in BANDS:
        counts=[]
        denominators=[]
        rates=[]
        for i,item in enumerate(source):
            size=item["sampled_attempts_for_this_phase"]
            if (item["phase_offset_zero_based"]!=i
                    or item["attempts_starting_at"]!=i+1
                    or size!=(attempts-i-1)//PHASES+1
                    or item["queue_service_count_actually_observed"] is not (i==0)
                    or item["hypothetical_phase_is_NOT_queue_data"] is not (i!=0)):
                raise CorrelationError("noncanonical actual service sampled phase identity")
            val=item[COUNTER[band]]
            if (item["source_slow_ge40"]!=
                    item["source_slow_40to50"]+item["source_slow_ge50"]):
                raise CorrelationError("overlapping slow duration classes")
            rate=_rate(val,size)
            if band=="ge40" and _out(rate)!=item["ge40_rate_per_1000"]:
                raise CorrelationError("phase ge40 normalized rate altered")
            if band=="ge50" and _out(rate)!=item["ge50_rate_per_1000"]:
                raise CorrelationError("phase ge50 normalized rate altered")
            counts.append(val)
            denominators.append(size)
            rates.append(rate)
        total=sum(counts)
        if (sum(denominators)!=attempts
                or total !=record[
                    "slow_ge40" if band=="ge40" else
                    "slow_ge50" if band=="ge50" else "slow_ge40"
                ] - (record["slow_ge50"] if band=="between40and50" else 0)):
            raise CorrelationError("full-source slow-call conservation is broken")
        full=_rate(total,attempts)
        actual=rates[0]
        if sum((rates[i]*denominators[i] for i in range(PHASES)),
               Fraction(0))!=full*attempts:
            raise CorrelationError("all 16 phase rates fail exact weighted pooling")
        tallies[band]={
            "full_session_attempts":attempts,
            "full_session_slow_call_count":total,
            "actual_phase0_attempts":denominators[0],
            "actual_phase0_slow_call_count":counts[0],
            "actual_phase0_rate_per_1000":_out(actual),
            "all_calls_rate_per_1000":_out(full),
            "phase0_minus_all_calls_per_1000":_out(actual-full),
            "min_phase_rate_per_1000":_out(min(rates)),
            "max_phase_rate_per_1000":_out(max(rates)),
            "min_max_are_across_overlapping_source_call_residues":True,
        }
        phase_ratios[band]={"all":full,"actual":actual,
                            "per_phase":rates}
    for key in ("all","actual"):
        if (phase_ratios["ge40"][key]!=
                phase_ratios["between40and50"][key]+phase_ratios["ge50"][key]):
            raise CorrelationError("disjoint band identity lost in source rate")
    return {"rates":phase_ratios,"stats":tallies}


def analyse_selection_gap(stage291:dict,stage290:dict)->dict:
    if (stage291.get("result")!=
            "ORIGINAL_SD_ALL_16_DETERMINISTIC_SAMPLE_PHASES_RECONCILED"
            or stage291.get("both_original_guest_sd_reopened_this_workflow") is not True
            or stage291.get("observed_real_queue_query_phase")!=0
            or stage291.get("other_phase_queue_counts_are_NOT_measured") is not True
            or stage291.get("audio_scheduler_DAC_or_audible_underruns_measured") is not False
            or stage291.get("scene_causality_proven") is not False
            or stage290.get("result")!=
                "SAME_NRO_ORIGINAL_SD_TWO_MODE_PROBE_COMPARISON_RECONCILED"
            or stage291.get("nro_sha256")!=stage290.get("nro_sha256")
            or stage290.get("sampled_on_exact_every_sixteenth_call") is not True
            or stage290.get("sampling_randomized") is not False):
        raise CorrelationError("source original-SD phase report not eligible")
    mode_data={}
    for name in MODES:
        mode=stage291[name]
        witness=stage290[name]
        if (mode["attempts"]!=witness["audout_attempts"]
                or mode["phase_table"][0]["sampled_attempts_for_this_phase"]!=
                   witness["sample_count"]
                or mode["phase_table"][0]["source_slow_ge40"]!=
                   witness["slow_call_sampled_ge40"]
                or mode["phase_table"][0]["source_slow_ge50"]!=
                   witness["slow_call_sampled_ge50"]):
            raise CorrelationError("actual queue probe and complete slow calls disagree")
        mode_data[name]=_mode_phase_rates(mode)

    results={}
    for band in BANDS:
        sw=mode_data["switching"]["rates"][band]
        idle=mode_data["idle"]["rates"][band]
        actual=sw["actual"]-idle["actual"]
        pooled=sw["all"]-idle["all"]
        phase_deltas=[
            sw["per_phase"][i]-idle["per_phase"][i]
            for i in range(PHASES)
        ]
        for i,reference in enumerate(stage291["same_phase_comparisons"]):
            if (reference["phase_offset_zero_based"]!=i
                    or (band=="ge40" and
                        (reference["switch_minus_idle_ge40_per_1000"]
                         !=_out(phase_deltas[i]) or
                         reference["positive"] is not (phase_deltas[i]>0) or
                         reference["negative"] is not (phase_deltas[i]<0) or
                         reference["exact_tie"] is not (phase_deltas[i]==0)))):
                raise CorrelationError("Stage291 original phase comparison altered")
        results[band]={
            "actual_phase0_switch_minus_idle_per_1000":_out(actual),
            "all_calls_switch_minus_idle_per_1000":_out(pooled),
            "phase0_minus_all_calls_contrast_per_1000":_out(actual-pooled),
            "across_16_phases_min_contrast_per_1000":_out(min(phase_deltas)),
            "across_16_phases_max_contrast_per_1000":_out(max(phase_deltas)),
            "phases_above_zero":sum(x>0 for x in phase_deltas),
            "phases_below_zero":sum(x<0 for x in phase_deltas),
            "phases_exactly_zero":sum(x==0 for x in phase_deltas),
            "phase0_is_directly_measured_queue_phase":True,
            "other_phases_include_only_independent_slow_call_durations":True,
        }

    for field in (
        "actual_phase0_switch_minus_idle_per_1000",
        "all_calls_switch_minus_idle_per_1000",
        "phase0_minus_all_calls_contrast_per_1000",
    ):
        if abs(results["ge40"][field]-
               results["between40and50"][field]-
               results["ge50"][field])>0.000001000001:
            raise CorrelationError("rounded reported duration bands do not close")

    return {
        "schema":SCHEMA,
        "result":"MEASURED_PHASE_ZERO_VS_ALL_AUDOUT_CALLS_RECONCILED",
        "nro_sha256":stage291["nro_sha256"],
        "measured_pre_submit_queue_phase_zero_only":True,
        "modes":{m:mode_data[m]["stats"] for m in MODES},
        "bands":results,
        "source_original_SD_stage291_recomputed_in_current_workflow":True,
        "exact_fraction_weighted_phase_identity":True,
        "other_phase_queue_counts_imputed":False,
        "sample_selection_gap_not_statistical_estimator_bias":True,
        "session_switching_preceded_idle":True,
        "randomized_significance_test":False,
        "scheduler_DAC_audible_underruns_measured":False,
        "music_scene_switch_causality_proven":False,
        "physical_switch_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for field in (
        "switch-sd-root","idle-sd-root","switch-evidence","idle-evidence",
        "stage290-report","stage291-report","switch-slow-report",
        "idle-verdict","output"
    ):
        p.add_argument("--"+field,type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse replace of existing phase-selection report")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        same_nro=load(args.stage290_report)
        prior=load(args.stage291_report)
        slow=load(args.switch_slow_report)
        idle_verdict=load(args.idle_verdict)
        switch=audit_mode(
            sd_root=args.switch_sd_root,evidence=args.switch_evidence,
            expected_attempts=slow["audout_attempts"],
            expected_slow=slow["slow_calls_captured"],
            expected_ge50=slow["slow_ge50ms_count"],
            expected_slow_sha=slow["guest_sd_slow_sha256"],
            actual_probes=same_nro["switching"])
        idle=audit_mode(
            sd_root=args.idle_sd_root,evidence=args.idle_evidence,
            expected_attempts=idle_verdict["guest_audout_attempts"],
            expected_slow=idle_verdict["slow_ge40ms_calls"],
            expected_ge50=idle_verdict["slow_ge50ms_calls"],
            expected_slow_sha=idle_verdict["idle_guest_sd_sha256"]["slow"],
            actual_probes=same_nro["idle"])
        validated=compare_phase_sensitivity(
            switch,idle,same_nro,slow,idle_verdict)
        if validated!=prior:
            raise CorrelationError("Stage291 report altered since original-SD audit")
        report=analyse_selection_gap(validated,same_nro)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "ge40":report["bands"]["ge40"],
            "ge50":report["bands"]["ge50"],
            "between40and50":report["bands"]["between40and50"],
            "physical_hardware_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"PHASE_SELECTION_GAP_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
