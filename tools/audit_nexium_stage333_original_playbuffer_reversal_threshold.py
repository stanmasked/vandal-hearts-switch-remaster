#!/usr/bin/env python3
"""Stage333: exact finite-sample reversal threshold of real guest PlayBuffer tails.

Enumerate all 0..5 deletions from 15 original preceding successful normal
guest-software audoutPlayBuffer calls. Determine first k for which at least
one surviving previous-call lower median is <= the untouched final call.
A direct min-vs-last proof covers *all* nonempty previous-call subsets when
the final call is strictly shorter than every earlier call. Never extrapolate
this descriptive finite-sample threshold to population latency or speakers.
"""
from __future__ import annotations

import argparse
from itertools import combinations
import json
from math import comb
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage332_original_playbuffer_frontier import compare_frontiers
from compare_nexium_stage328_original_playbuffer_histories import load,verify

SCHEMA="vh-stage333-original-guest-PlayBuffer-first-median-reversal-threshold/v1"
RESULT="TWO_PINNED_ORIGINAL_PLAYBUFFER_FINITE_SAMPLE_REVERSAL_THRESHOLDS_VERIFIED"
MAX_CHECKED_K=5


def source_threshold(source:dict,history_sha:str,last_sha:str)->dict:
    d=verify(source,history_sha,last_sha)
    calls=d["original_call_rows"]
    if len(calls)!=16 or any(c["lease_returned"] is not True for c in calls):
        raise ExitTimelineError("incomplete original normal successful guest software-call tail")
    previous=[c["duration_guest_ns"] for c in calls[:15]]
    final=calls[-1]["duration_guest_ns"]
    if (len(previous)!=15 or type(final) is not int or final<0 or
            any(type(x) is not int or x<0 for x in previous)):
        raise ExitTimelineError("invalid retained software-call guest source durations")
    less=sum(v<final for v in previous)
    equal=sum(v==final for v in previous)
    more=sum(v>final for v in previous)
    if less+equal+more!=15:
        raise ExitTimelineError("previous guest software source outcomes not conserved")

    levels=[]
    for k in range(MAX_CHECKED_K+1):
        below=equal_to=above=0
        minmargin=None
        maxmargin=None
        for excluded in combinations(range(15),k):
            removed=set(excluded)
            kept=[v for i,v in enumerate(previous) if i not in removed]
            if len(kept)!=15-k or not kept:
                raise ExitTimelineError("original guest software-call deletion removed wrong count")
            margin=median_low(kept)-final
            minmargin=margin if minmargin is None else min(minmargin,margin)
            maxmargin=margin if maxmargin is None else max(maxmargin,margin)
            below+=margin>0
            equal_to+=margin==0
            above+=margin<0
        n=comb(15,k)
        if below+equal_to+above!=n or minmargin is None or maxmargin is None:
            raise ExitTimelineError("lost original source deletion subset or result")
        levels.append({
            "excluded_previous_calls":k,
            "retained_previous_calls_per_subset":15-k,
            "subset_count":n,
            "original_guest_software_median_minus_final_min_ns":minmargin,
            "original_guest_software_median_minus_final_max_ns":maxmargin,
            "subsets_with_final_strictly_shorter_than_median":below,
            "subsets_with_final_equal_to_median":equal_to,
            "subsets_with_final_longer_than_median":above,
            "all_subsets_keep_final_strictly_shorter":below==n,
        })
    first_reversal=next((x["excluded_previous_calls"] for x in levels
                        if not x["all_subsets_keep_final_strictly_shorter"]),None)
    # This is a rigorous finite-set implication, not an inference about
    # unseen runs: if final < min(previous), every nonempty earlier-call
    # subset has median >= min(previous) > final.
    guaranteed_all_nonempty=(less==0 and equal==0)
    if guaranteed_all_nonempty and first_reversal is not None:
        raise ExitTimelineError("contradiction in source min-versus-last proof")
    return {
        "original_guest_history_sha256":history_sha,
        "original_last_success_sha256":last_sha,
        "retained_prior_success_count":15,
        "last_original_guest_software_call_ns":final,
        "prior_calls_shorter_equal_longer_than_last":[less,equal,more],
        "deletion_levels":levels,
        "first_checked_deletion_k_with_final_not_strictly_below_median":first_reversal,
        "no_checked_reversal_with_zero_through_five_omissions":first_reversal is None,
        "proof_final_shorter_than_all_nonempty_subsets_of_original_prior_calls":
            guaranteed_all_nonempty,
        "proof_does_not_cover_original_calls_not_in_retained_history":True,
        "no_population_confidence_interval_or_hardware_latency_claim":True,
    }


def compare_thresholds(first:dict,second:dict,
                       first_history_sha:str,second_history_sha:str,
                       first_last_sha:str,second_last_sha:str)->dict:
    prior=compare_frontiers(first,second,first_history_sha,second_history_sha,
                            first_last_sha,second_last_sha)
    if (prior.get("result")!=
            "TWO_ORIGINAL_GUEST_PLAYBUFFER_SOURCE_DELETION_FRONTIERS_VERIFIED"
            or prior.get("four_original_guest_CSV_SHA256_pins_verified") is not True
            or prior.get("physical_Nintendo_Switch_audio_measured") is not False):
        raise ExitTimelineError("original Stage332 multi-source replay not confirmed")
    rows=[]
    for index,(name,source,h,l) in enumerate((
            ("first",first,first_history_sha,first_last_sha),
            ("second",second,second_history_sha,second_last_sha))):
        audited=source_threshold(source,h,l)
        previous=prior["cohorts"][index]["source_subset_sensitivity_frontier"]
        for k in range(4):
            current=audited["deletion_levels"][k]
            prior_row=previous[k]
            if (current["subset_count"]!=prior_row["subset_count"]
                or current["subsets_with_final_strictly_shorter_than_median"]!=prior_row[
                    "subsets_with_final_shorter_than_median"]
                or current["subsets_with_final_equal_to_median"]!=prior_row[
                    "subsets_with_final_equal_to_median"]
                or current["subsets_with_final_longer_than_median"]!=prior_row[
                    "subsets_with_final_longer_than_median"]):
                raise ExitTimelineError("first four original sensitivity levels differ from Stage332")
        rows.append({"cohort":name,**audited})
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":rows,
        "all_original_stage328_to_332_source_audits_recomputed":True,
        "all_four_original_guest_CSV_SHA256_digests_checked":True,
        "original_guest_software_subsets_per_capture":sum(comb(15,k) for k in range(6)),
        "not_independent_repeated_gameplay_sessions":True,
        "original_guest_absolute_timestamps_not_published":True,
        "guest_software_clock_not_host_PCM_or_DAC_time":True,
        "plus_audio_causality_or_original_soundtrack_not_verified":True,
        "physical_Nintendo_Switch_audio_measured":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-root",required=True,type=Path)
    p.add_argument("--second-root",required=True,type=Path)
    p.add_argument("--first-history-sha256",required=True)
    p.add_argument("--second-history-sha256",required=True)
    p.add_argument("--first-last-sha256",required=True)
    p.add_argument("--second-last-sha256",required=True)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.first_root.resolve()==a.second_root.resolve():
            raise ExitTimelineError("requires two separate original NeXium source captures")
        if a.output.exists() or a.output.is_symlink():
            raise ExitTimelineError("refuse original finite-source reversal report overwrite")
        out=compare_thresholds(
            load(a.first_root),load(a.second_root),
            a.first_history_sha256,a.second_history_sha256,
            a.first_last_sha256,a.second_last_sha256)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(out,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":out["result"],
            "cohorts":out["cohorts"],
            "physical_audio_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE333_ORIGINAL_REVERSAL_THRESHOLD_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
