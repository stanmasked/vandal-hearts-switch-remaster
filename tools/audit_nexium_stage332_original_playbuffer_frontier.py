#!/usr/bin/env python3
"""Stage332: original NeXium PlayBuffer tail sensitivity frontier, deleting 0..3.

All 1+15+105+455 subsets of fifteen previous original guest-software call
durations are considered, preserving the final successful call. The previous
Stage328–331 source audits are rerun against four authentic pinned SHA-256
CSV sources. Subsets are NOT independent experimental runs or hardware audio.
"""
from __future__ import annotations

import argparse
from itertools import combinations
import json
from math import comb
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage330_original_playbuffer_jackknife import compare_jackknives
from audit_nexium_stage331_original_playbuffer_pair_deletion import compare_two
from compare_nexium_stage328_original_playbuffer_histories import load,verify

SCHEMA="vh-stage332-original-guest-PlayBuffer-tail-0-to-3-deletion-frontier/v1"
RESULT="TWO_ORIGINAL_GUEST_PLAYBUFFER_SOURCE_DELETION_FRONTIERS_VERIFIED"


def cohort_frontier(source:dict, history_sha:str, last_sha:str)->dict:
    receipt=verify(source,history_sha,last_sha)
    calls=receipt["original_call_rows"]
    if len(calls)!=16 or any(c["lease_returned"] is not True for c in calls):
        raise ExitTimelineError("incomplete authentic sixteen-call PlayBuffer source")
    previous=[c["duration_guest_ns"] for c in calls[:-1]]
    last=calls[-1]["duration_guest_ns"]
    if (len(previous)!=15 or type(last) is not int or last<0
            or any(type(x) is not int or x<0 for x in previous)):
        raise ExitTimelineError("noninteger or missing original guest software durations")
    frontier=[]
    for k in range(4):
        medians=[]
        mads=[]
        ranks=[]
        shorter=equal=longer=0
        for excluded in combinations(range(15),k):
            mask=set(excluded)
            kept=[v for i,v in enumerate(previous) if i not in mask]
            if len(kept)!=15-k:
                raise ExitTimelineError("guest source subset omission lost a call")
            center=median_low(kept)
            deviation=median_low([abs(v-center) for v in kept])
            rank=1+sum(v<last for v in kept)
            medians.append(center)
            mads.append(deviation)
            ranks.append(rank)
            shorter+=last<center
            equal+=last==center
            longer+=last>center
        n=comb(15,k)
        if (len(medians)!=n or len(mads)!=n or len(ranks)!=n
                or shorter+equal+longer!=n):
            raise ExitTimelineError("incorrect distinct source software subcohort count")
        frontier.append({
            "excluded_previous_calls":k,
            "retained_previous_calls_per_subset":15-k,
            "subset_count":n,
            "lower_median_min_software_ns":min(medians),
            "lower_median_max_software_ns":max(medians),
            "lower_median_span_software_ns":max(medians)-min(medians),
            "MAD_min_software_ns":min(mads),
            "MAD_max_software_ns":max(mads),
            "final_first_possible_rank_min":min(ranks),
            "final_first_possible_rank_max":max(ranks),
            "subsets_with_final_shorter_than_median":shorter,
            "subsets_with_final_equal_to_median":equal,
            "subsets_with_final_longer_than_median":longer,
            "final_shorter_than_all_subsets":shorter==n,
        })
    if frontier[0]["lower_median_min_software_ns"]!=receipt[
            "prior_successful_duration_lower_median_guest_ns"]:
        raise ExitTimelineError("original Stage322 full previous baseline changed")
    stability=tuple(f["excluded_previous_calls"] for f in frontier
                    if f["final_shorter_than_all_subsets"])
    return {
        "original_guest_history_sha256":history_sha,
        "original_last_call_sha256":last_sha,
        "retained_normal_successful_guest_software_calls":16,
        "final_call_duration_software_ns":last,
        "full_previous_lower_median_software_ns":frontier[0]["lower_median_min_software_ns"],
        "source_subset_sensitivity_frontier":frontier,
        "largest_checked_exclusion_k_with_all_subsets_shorter":
            max(stability) if stability else None,
        "first_checked_k_not_stable":
            next((f["excluded_previous_calls"] for f in frontier
                  if not f["final_shorter_than_all_subsets"]),None),
        "cannot_extrapolate_beyond_three_deleted_calls":True,
    }


def compare_frontiers(a:dict,b:dict,
                     first_history_sha:str,second_history_sha:str,
                     first_last_sha:str,second_last_sha:str)->dict:
    prior330=compare_jackknives(a,b,first_history_sha,second_history_sha,
                                first_last_sha,second_last_sha)
    prior331=compare_two(a,b,first_history_sha,second_history_sha,
                         first_last_sha,second_last_sha)
    if (prior330.get("result")!=
            "TWO_SOURCE_PINNED_PLAYBUFFER_SOFTWARE_TAILS_LEAVE_ONE_OUT_REAUDITED"
            or prior331.get("result")!=
            "TWO_PINNED_ORIGINAL_PLAYBUFFER_TAILS_ALL_PAIR_DELETIONS_REPLAYED"):
        raise ExitTimelineError("original Stage330/331 strict source replay missing")
    cohorts=[]
    for i,(name,source,h,l) in enumerate((
            ("first",a,first_history_sha,first_last_sha),
            ("second",b,second_history_sha,second_last_sha))):
        row=cohort_frontier(source,h,l)
        single=prior330["cohorts"][i]
        paired=prior331["cohorts"][i]
        one=row["source_subset_sensitivity_frontier"][1]
        two=row["source_subset_sensitivity_frontier"][2]
        if (one["lower_median_min_software_ns"]!=single[
                "leave_one_out_lower_median_min_ns"]
            or one["lower_median_max_software_ns"]!=single[
                "leave_one_out_lower_median_max_ns"]
            or one["MAD_min_software_ns"]!=single["leave_one_out_MAD_min_ns"]
            or one["MAD_max_software_ns"]!=single["leave_one_out_MAD_max_ns"]
            or one["final_first_possible_rank_min"]!=single[
                "leave_one_out_last_first_possible_rank_min"]
            or one["final_first_possible_rank_max"]!=single[
                "leave_one_out_last_first_possible_rank_max"]
            or two["lower_median_min_software_ns"]!=paired[
                "leave_two_out_lower_median_min_guest_software_ns"]
            or two["lower_median_max_software_ns"]!=paired[
                "leave_two_out_lower_median_max_guest_software_ns"]
            or two["MAD_min_software_ns"]!=paired[
                "leave_two_out_MAD_min_guest_software_ns"]
            or two["MAD_max_software_ns"]!=paired[
                "leave_two_out_MAD_max_guest_software_ns"]
            or two["final_first_possible_rank_min"]!=paired[
                "leave_two_out_final_first_possible_rank_min"]
            or two["final_first_possible_rank_max"]!=paired[
                "leave_two_out_final_first_possible_rank_max"]
            or two["subsets_with_final_shorter_than_median"]!=paired[
                "replicas_with_final_shorter_than_previous_median"]
            or two["subsets_with_final_equal_to_median"]!=paired[
                "replicas_with_final_equal_to_previous_median"]
            or two["subsets_with_final_longer_than_median"]!=paired[
                "replicas_with_final_longer_than_previous_median"]):
            raise ExitTimelineError("Stage332 original source disagrees with Stage330/331")
        cohorts.append({"cohort":name,**row})
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":cohorts,
        "independent_original_stage328_to_331_source_replays_match":True,
        "four_original_guest_CSV_SHA256_pins_verified":True,
        "subset_count_per_cohort":sum(comb(15,k) for k in range(4)),
        "source_deletions_are_not_independent_gameplay_runs":True,
        "no_population_confidence_or_audio_latency_guarantee":True,
        "original_absolute_guest_begin_end_timestamps_not_republished":True,
        "guest_clock_not_mapped_to_host_PCM_or_DAC":True,
        "original_soundtrack_or_audible_audio_verified":False,
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
    args=p.parse_args()
    try:
        if args.first_root.resolve()==args.second_root.resolve():
            raise ExitTimelineError("two distinct original NeXium archives required")
        if args.output.exists() or args.output.is_symlink():
            raise ExitTimelineError("refuse overwrite source-authentic frontier")
        report=compare_frontiers(
            load(args.first_root),load(args.second_root),
            args.first_history_sha256,args.second_history_sha256,
            args.first_last_sha256,args.second_last_sha256)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":report["result"],
            "cohorts":report["cohorts"],
            "physical_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE332_ORIGINAL_SOFTWARE_FRONTIER_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
