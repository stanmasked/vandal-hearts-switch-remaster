#!/usr/bin/env python3
"""Stage329: source-backed bounded PlayBuffer software-call dispersion.

Replays two original successful NeXium last-16 guest histories through
Stage328's pinned Stage320/Stage322 verifier. Classifies earlier 15
software-call durations and the final-call insertion rank. Never publishes
original guest absolute timestamps, PCM samples or acoustic claims.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from compare_nexium_stage328_original_playbuffer_histories import (
    load, compare, verify, SCHEMA as STAGE328_SCHEMA, VERIFIED as STAGE328_RESULT
)

SCHEMA="vh-stage329-two-original-playbuffer-guest-software-dispersion/v1"
RESULT="TWO_SOURCE_PINNED_GUEST_PLAYBUFFER_SOFTWARE_DISTRIBUTIONS_CLASSIFIED"


def original_cohort_shape(source:dict,history_sha:str,last_sha:str)->dict:
    receipt=verify(source,history_sha,last_sha)
    calls=receipt["original_call_rows"]
    if (len(calls)!=16 or any(c["lease_returned"] is not True for c in calls)
            or len(set(c["sequence"] for c in calls))!=16
            or calls[-1]["duration_guest_ns"]!=receipt["final_call_duration_guest_ns"]):
        raise ExitTimelineError("original bounded PlayBuffer source not a complete success cohort")
    earlier=[c["duration_guest_ns"] for c in calls[:-1]]
    last=calls[-1]["duration_guest_ns"]
    if len(earlier)!=15 or any(type(x) is not int or x<0 for x in earlier):
        raise ExitTimelineError("untrustworthy previous PlayBuffer software call durations")
    ordered=sorted(earlier)
    center=median_low(ordered)
    mad=median_low([abs(x-center) for x in earlier])
    if center!=receipt["prior_successful_duration_lower_median_guest_ns"]:
        raise ExitTimelineError("previous baseline differs from original Stage322")
    lower=sum(x<last for x in earlier)
    equal=sum(x==last for x in earlier)
    higher=sum(x>last for x in earlier)
    if lower+equal+higher!=15:
        raise ExitTimelineError("lost a source-authentic previous software call")
    return {
        "original_guest_history_sha256":history_sha,
        "original_last_success_sha256":last_sha,
        "previous_successful_call_count":15,
        "previous_min_duration_guest_software_ns":ordered[0],
        "previous_lower_median_duration_guest_software_ns":center,
        "previous_max_duration_guest_software_ns":ordered[-1],
        "previous_range_guest_software_ns":ordered[-1]-ordered[0],
        "previous_median_absolute_deviation_guest_software_ns":mad,
        "last_successful_duration_guest_software_ns":last,
        "previous_calls_faster_than_last":lower,
        "previous_calls_equal_to_last":equal,
        "previous_calls_slower_than_last":higher,
        "last_call_insertion_rank_among_16_if_ties_before":lower+1,
        "last_call_is_shorter_than_prior_lower_median":last<center,
    }


def compare_shapes(first:dict,second:dict,
                   first_history_sha:str,second_history_sha:str,
                   first_last_sha:str,second_last_sha:str)->dict:
    # Require Stage328's exact independent original-source validation
    # before deriving extra summary metrics.
    previous=compare(first,second,first_history_sha,second_history_sha,
                     first_last_sha,second_last_sha)
    if previous.get("schema")!=STAGE328_SCHEMA or previous.get("result")!=STAGE328_RESULT:
        raise ExitTimelineError("original Stage328 comparison provenance missing")
    p=original_cohort_shape(first,first_history_sha,first_last_sha)
    q=original_cohort_shape(second,second_history_sha,second_last_sha)
    if (not p["last_call_is_shorter_than_prior_lower_median"]
            or not q["last_call_is_shorter_than_prior_lower_median"]):
        raise ExitTimelineError("Stage329 original observations not consistent with Stage328")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":[{"cohort":"first",**p},{"cohort":"second",**q}],
        "second_minus_first_previous_range_guest_software_ns":
            q["previous_range_guest_software_ns"]-p["previous_range_guest_software_ns"],
        "second_minus_first_previous_MAD_guest_software_ns":
            q["previous_median_absolute_deviation_guest_software_ns"]-
            p["previous_median_absolute_deviation_guest_software_ns"],
        "original_stage328_pinned_sources_independently_replayed":True,
        "two_bounded_cohorts_not_population_latency_estimate":True,
        "previous_15_are_only_tail_of_normal_call_history":True,
        "no_absolute_original_guest_software_timestamps_published":True,
        "no_guest_to_host_clock_mapping_proven":True,
        "original_PS1_soundtrack_or_audible_dropout_verified":False,
        "Nintendo_Switch_speaker_audio_measured":False,
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
            raise ExitTimelineError("original cohort roots must be distinct")
        if a.output.exists() or a.output.is_symlink():
            raise ExitTimelineError("refuse overwrite Stage329 original-source result")
        result=compare_shapes(
            load(a.first_root),load(a.second_root),
            a.first_history_sha256,a.second_history_sha256,
            a.first_last_sha256,a.second_last_sha256)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":result["result"],
            "original_source_dispersions":result["cohorts"],
            "Nintendo_Switch_speaker_audio_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE329_SOURCE_DISPERSION_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "Nintendo_Switch_speaker_audio_measured":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
