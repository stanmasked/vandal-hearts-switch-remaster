#!/usr/bin/env python3
"""Stage298: exact complement of actually queried 1-in-16 audout calls.

Every API duration >=40ms belongs either to the actually queried phase
or the other 15 unqueried phases of THIS guest session. We know software
call durations on both; we do NOT know service queue counts on those
other 15 phases. Source authentication is rerun against ORIGINAL guest
SD for all four independent sessions, never by relabeling artifacts.
No randomized causal, hardware, DAC or audible outcome is inferred.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from audit_nexium_phase_order_full_call_rates import (
    LABELS, PHASES, source_profile, compare_complete, rate, signed
)

SCHEMA="vh-nexium-four-session-query-complement-exact-duration-rates/v1"
BANDS=("ge40","ge50")


def complement_profile(profile:dict)->dict:
    attempts=profile.get("audout_attempts")
    query=profile.get("sample_count")
    phase=profile.get("phase")
    if (type(phase) is not int or phase not in (0,8)
            or type(attempts) is not int or type(query) is not int
            or attempts<=16 or query<=0 or query>=attempts
            or query!=max(0,(attempts+15-phase)//16)
            or profile.get("source_guest_SD_reread_and_verified") is not True):
        raise CorrelationError("missing source-verified queried/remaining denominators")
    other=attempts-query
    result={
        "phase":phase,
        "all_call_attempts":attempts,
        "actually_queried_attempts":query,
        "other_15_phases_attempts":other,
        "original_guest_slow_source_sha256":profile["original_slow_csv_sha256"],
        "original_guest_query_source_sha256":profile["original_probe_csv_sha256"],
    }
    for band in BANDS:
        total=profile["slow_"+band+"_all_calls"]
        selected=profile["slow_"+band+"_queried"]
        if (type(total) is not int or type(selected) is not int
                or not 0<=selected<=total<=attempts
                or selected>query or total-selected>other):
            raise CorrelationError("slow-call count not conserved across queried/offphase calls")
        unqueried=total-selected
        fullrate=rate(total,attempts)
        selectedrate=rate(selected,query)
        unqueriedrate=rate(unqueried,other)
        if (selectedrate*query+unqueriedrate*other !=
                fullrate*attempts):
            raise CorrelationError("exact weighted source call rates not conserved")
        result[band]={
            "all_call_slow_count":total,
            "queried_slow_count":selected,
            "other_15_phases_slow_count":unqueried,
            "all_call_rate_per_1000":signed(fullrate),
            "queried_call_rate_per_1000":signed(selectedrate),
            "other_15_phases_call_rate_per_1000":signed(unqueriedrate),
            "queried_minus_other_15_phases_rate_per_1000":
                signed(selectedrate-unqueriedrate),
        }
    if (result["ge50"]["all_call_slow_count"]>
            result["ge40"]["all_call_slow_count"]
            or result["ge50"]["queried_slow_count"]>
               result["ge40"]["queried_slow_count"]
            or result["ge50"]["other_15_phases_slow_count"]>
               result["ge40"]["other_15_phases_slow_count"]):
        raise CorrelationError(">=50ms must remain a subset of >=40ms in BOTH partitions")
    return result


def compare_complements(stage296:dict, stage297:dict,
                        profiles:list[dict])->dict:
    regenerated=compare_complete(stage296,profiles)
    if regenerated!=stage297:
        raise CorrelationError("Stage297 original-SD all-call witness is not reproducible")
    if stage297.get("result")!=
            "FOUR_REAL_GUEST_SD_FULL_AUDOUT_VS_QUERIED_RATES_VERIFIED":
        raise CorrelationError("unverified source stage")
    summaries=[complement_profile(profile) for profile in profiles]
    if ([s["phase"] for s in summaries]!=list(PHASES)
            or len(summaries)!=4 or
            stage297.get("DAC_underruns_or_physical_Switch_audio_measured") is not False
            or stage297.get("phase_or_music_switch_causality_proven") is not False
            or stage297.get("no_unqueried_queue_service_counts_imputed") is not True):
        raise CorrelationError("not four original software-only sessions")
    sessions=[
        {"label":label,**s}
        for label,s in zip(LABELS,summaries)
    ]
    contrast={}
    for name,idx0,idx8 in (
        ("first_pair",0,1),("reversed_pair",3,2)):
        pair={}
        for band in BANDS:
            p0=profiles[idx0]
            p8=profiles[idx8]
            all_delta=(rate(p0["slow_"+band+"_all_calls"],
                            p0["audout_attempts"])-
                       rate(p8["slow_"+band+"_all_calls"],
                            p8["audout_attempts"]))
            queried_delta=(rate(p0["slow_"+band+"_queried"],
                                p0["sample_count"])-
                           rate(p8["slow_"+band+"_queried"],
                                p8["sample_count"]))
            remaining_delta=(
                rate(p0["slow_"+band+"_all_calls"]-
                     p0["slow_"+band+"_queried"],
                     p0["audout_attempts"]-p0["sample_count"])-
                rate(p8["slow_"+band+"_all_calls"]-
                     p8["slow_"+band+"_queried"],
                     p8["audout_attempts"]-p8["sample_count"]))
            expected=stage297["pairs"][name][band]
            if (abs(signed(all_delta)-
                    expected["phase0_minus_phase8_per_1000_all_calls"])>
                    0.00000101 or
                abs(signed(queried_delta)-
                    expected["phase0_minus_phase8_per_1000_queried_calls"])>
                    0.00000101):
                raise CorrelationError("new complement diverges from verified stage297")
            pair[band]={
                "phase0_minus_phase8_all_calls_per_1000":signed(all_delta),
                "phase0_minus_phase8_actually_queried_per_1000":
                    signed(queried_delta),
                "phase0_minus_phase8_other_15_phases_per_1000":
                    signed(remaining_delta),
                "queried_minus_other_phase_contrast_gap_per_1000":
                    signed(queried_delta-remaining_delta),
            }
        contrast[name]=pair
    return {
        "schema":SCHEMA,
        "result":"FOUR_ORIGINAL_SD_ACTUAL_VS_OTHER15_SLOW_CALLS_RECONCILED",
        "nro_phase_order":list(PHASES),
        "capture_sequence":list(LABELS),
        "source_git_sha":stage297["source_git_sha"],
        "source_run_id":stage297["source_run_id"],
        "sessions":sessions,
        "phase0_vs_phase8_by_capture_pair":contrast,
        "stage297_fully_recomputed_from_four_original_guest_SD":True,
        "exact_integer_count_partition_and_fraction_weighting":True,
        "offphase_API_call_durations_observed":True,
        "offphase_queue_service_counts_observed":False,
        "offphase_queue_service_values_imputed":False,
        "capture_order_randomized":False,
        "software_call_observations_not_independent_trials":True,
        "causal_audio_effect_proven":False,
        "physical_switch_DAC_or_audible_glitches_measured":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("stage296","stage297","output"):
        p.add_argument("--"+name,required=True,type=Path)
    for label in LABELS:
        p.add_argument("--"+label+"-sd-root",required=True,type=Path)
        p.add_argument("--"+label+"-evidence",required=True,type=Path)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite existing source-bound complement report")
        def read(path:Path)->dict:
            if path.is_symlink() or not path.is_file():
                raise CorrelationError("missing or aliased prerequisite evidence")
            return json.loads(path.read_text(encoding="utf-8"))
        stage296=read(args.stage296)
        stage297=read(args.stage297)
        profiles=[
            source_profile(
                sd_root=getattr(args,label+"_sd_root"),
                evidence=getattr(args,label+"_evidence"),
                phase=phase,verified_row=verified_row)
            for label,phase,verified_row in zip(
                LABELS,PHASES,stage296["session_records"])
        ]
        report=compare_complements(stage296,stage297,profiles)
        args.output.write_text(
            json.dumps(report,sort_keys=True,indent=2)+"\n",
            encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "per_session_ge40":{
                r["label"]:{
                    "queried":r["ge40"]["queried_slow_count"],
                    "other15":r["ge40"]["other_15_phases_slow_count"],
                    "all":r["ge40"]["all_call_slow_count"],
                } for r in report["sessions"]},
            "pair_contrasts":report["phase0_vs_phase8_by_capture_pair"],
            "hardware_audio_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError,KeyError) as exc:
        print(json.dumps({
            "result":"FOUR_ORIGINAL_SD_CALL_COMPLEMENTS_NOT_VERIFIED",
            "error":str(exc)
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
