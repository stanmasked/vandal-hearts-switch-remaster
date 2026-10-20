#!/usr/bin/env python3
"""Stage331: omit every pair of prior source-authenticated guest PlayBuffer calls.

Exactly 105 unordered exclusions from fifteen real previous software-call
durations per original NeXium capture. Original last successful call is never
removed. This is descriptive sensitivity, not statistical independence,
DAC/speaker audio, guest-host time alignment, or a causal timing model.
"""
from __future__ import annotations

import argparse
from itertools import combinations
import json
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage330_original_playbuffer_jackknife import compare_jackknives
from compare_nexium_stage328_original_playbuffer_histories import load,verify

SCHEMA="vh-stage331-original-PlayBuffer-two-deletions-software-sensitivity/v1"
RESULT="TWO_PINNED_ORIGINAL_PLAYBUFFER_TAILS_ALL_PAIR_DELETIONS_REPLAYED"
EXPECTED_REPLICAS=105


def one_cohort(source:dict,history_sha:str,last_sha:str)->dict:
    original=verify(source,history_sha,last_sha)
    calls=original["original_call_rows"]
    if len(calls)!=16 or any(x["lease_returned"] is not True for x in calls):
        raise ExitTimelineError("not an authentic complete 16-success guest software tail")
    previous=[r["duration_guest_ns"] for r in calls[:15]]
    last=calls[-1]["duration_guest_ns"]
    if (len(previous)!=15 or type(last) is not int or last<0 or
            any(type(v) is not int or v<0 for v in previous)):
        raise ExitTimelineError("invalid original previous-call software durations")
    medians=[]
    mads=[]
    ranks=[]
    for i,j in combinations(range(15),2):
        kept=[v for index,v in enumerate(previous) if index!=i and index!=j]
        if len(kept)!=13:
            raise ExitTimelineError("pairwise source omission conservation violated")
        middle=median_low(kept)
        medians.append(middle)
        mads.append(median_low([abs(v-middle) for v in kept]))
        ranks.append(1+sum(v<last for v in kept))
    if (len(medians)!=EXPECTED_REPLICAS or
            len(mads)!=EXPECTED_REPLICAS or len(ranks)!=EXPECTED_REPLICAS):
        raise ExitTimelineError("incomplete combinatorial deletion of original source calls")
    whole_median=original["prior_successful_duration_lower_median_guest_ns"]
    if not min(medians)<=whole_median<=max(medians):
        raise ExitTimelineError("invalid leave-two-out source lower median bounds")
    return {
        "original_guest_history_sha256":history_sha,
        "original_last_success_sha256":last_sha,
        "previous_successful_call_count":15,
        "final_untouched_call_guest_software_ns":last,
        "previous_fifteen_lower_median_guest_software_ns":whole_median,
        "deleted_original_previous_call_count_per_replica":2,
        "retained_previous_call_count_per_replica":13,
        "unordered_pair_deletion_replica_count":EXPECTED_REPLICAS,
        "leave_two_out_lower_median_min_guest_software_ns":min(medians),
        "leave_two_out_lower_median_max_guest_software_ns":max(medians),
        "leave_two_out_lower_median_span_guest_software_ns":max(medians)-min(medians),
        "leave_two_out_MAD_min_guest_software_ns":min(mads),
        "leave_two_out_MAD_max_guest_software_ns":max(mads),
        "leave_two_out_final_first_possible_rank_min":min(ranks),
        "leave_two_out_final_first_possible_rank_max":max(ranks),
        "replicas_with_final_shorter_than_previous_median":sum(last<x for x in medians),
        "replicas_with_final_equal_to_previous_median":sum(last==x for x in medians),
        "replicas_with_final_longer_than_previous_median":sum(last>x for x in medians),
    }


def compare_two(a:dict,b:dict,first_history_sha:str,second_history_sha:str,
                first_last_sha:str,second_last_sha:str)->dict:
    earlier=compare_jackknives(
        a,b,first_history_sha,second_history_sha,first_last_sha,second_last_sha)
    if (earlier.get("result")!=
            "TWO_SOURCE_PINNED_PLAYBUFFER_SOFTWARE_TAILS_LEAVE_ONE_OUT_REAUDITED"
            or earlier.get("physical_Nintendo_Switch_audio_measured") is not False):
        raise ExitTimelineError("independent Stage330 original provenance missing")
    first=one_cohort(a,first_history_sha,first_last_sha)
    second=one_cohort(b,second_history_sha,second_last_sha)
    for item in (first,second):
        if sum(item[k] for k in (
            "replicas_with_final_shorter_than_previous_median",
            "replicas_with_final_equal_to_previous_median",
            "replicas_with_final_longer_than_previous_median"))!=EXPECTED_REPLICAS:
            raise ExitTimelineError("pairwise deletion source outcome accounting incomplete")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":[{"cohort":"first",**first},{"cohort":"second",**second}],
        "all_stage330_original_source_and_four_csv_pins_replayed":True,
        "two_original_captures_not_105_independent_experiments":True,
        "leave_two_out_statistics_not_population_confidence_intervals":True,
        "no_original_guest_absolute_timestamps_published":True,
        "no_guest_to_host_pcm_sample_clock_alignment":True,
        "original_soundtrack_or_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
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
            raise ExitTimelineError("distinct original NeXium captures required")
        if a.output.exists() or a.output.is_symlink():
            raise ExitTimelineError("refuse overwrite original Stage331 source report")
        obj=compare_two(load(a.first_root),load(a.second_root),
                        a.first_history_sha256,a.second_history_sha256,
                        a.first_last_sha256,a.second_last_sha256)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(obj,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({"result":obj["result"],"cohorts":obj["cohorts"],
                          "physical_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE331_PAIRWISE_SOURCE_REPLAY_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "physical_audio_verified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
