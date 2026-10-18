#!/usr/bin/env python3
"""Stage330: leave-one-out robustness for two source-authentic normal audout tails.

Each of 15 original previous guest-software PlayBuffer durations is omitted
once; report the spread of resulting 14-call lower medians, MADs, and last
call's first-possible insertion rank. NOT DAC, speakers, guest-to-host PCM
time, a population confidence interval, or a reliability guarantee.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median_low

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage329_guest_software_dispersion import (
    compare_shapes,original_cohort_shape,SCHEMA as STAGE329_SCHEMA,
    RESULT as STAGE329_RESULT,
)
from compare_nexium_stage328_original_playbuffer_histories import (
    load,verify,
)

SCHEMA="vh-stage330-original-playbuffer-tail-leave-one-out/v1"
RESULT="TWO_SOURCE_PINNED_PLAYBUFFER_SOFTWARE_TAILS_LEAVE_ONE_OUT_REAUDITED"


def source_jackknife(source:dict,history_sha:str,last_sha:str)->dict:
    original=original_cohort_shape(source,history_sha,last_sha)
    receipt=verify(source,history_sha,last_sha)
    entries=receipt["original_call_rows"]
    if len(entries)!=16 or any(x["lease_returned"] is not True for x in entries):
        raise ExitTimelineError("incomplete source-authentic last 16 successful software calls")
    previous=[x["duration_guest_ns"] for x in entries[:-1]]
    if len(previous)!=15 or any(type(x) is not int or x<0 for x in previous):
        raise ExitTimelineError("missing or malformed previous normal service software calls")
    last=entries[-1]["duration_guest_ns"]
    if last!=original["last_successful_duration_guest_software_ns"]:
        raise ExitTimelineError("final software service duration disagrees with Stage329")
    medians=[]
    mads=[]
    insertion_ranks=[]
    for excluded in range(15):
        kept=previous[:excluded]+previous[excluded+1:]
        if len(kept)!=14:
            raise ExitTimelineError("leave-one-out call conservation violation")
        center=median_low(kept)
        deviation=median_low([abs(v-center) for v in kept])
        rank=1+sum(v<last for v in kept)
        medians.append(center)
        mads.append(deviation)
        insertion_ranks.append(rank)
    if len(medians)!=15 or len(mads)!=15 or len(insertion_ranks)!=15:
        raise ExitTimelineError("missing a previous original software observation")
    return {
        "original_guest_history_sha256":history_sha,
        "original_last_success_sha256":last_sha,
        "original_retained_success_count":16,
        "original_previous_success_count":15,
        "jackknife_deleted_one_previous_call_per_replica":True,
        "jackknife_replica_count":15,
        "calls_in_each_replica":14,
        "full_previous_lower_median_ns":
            original["previous_lower_median_duration_guest_software_ns"],
        "full_previous_MAD_ns":
            original["previous_median_absolute_deviation_guest_software_ns"],
        "last_successful_software_call_ns":last,
        "leave_one_out_lower_median_min_ns":min(medians),
        "leave_one_out_lower_median_max_ns":max(medians),
        "leave_one_out_lower_median_span_ns":max(medians)-min(medians),
        "leave_one_out_MAD_min_ns":min(mads),
        "leave_one_out_MAD_max_ns":max(mads),
        "leave_one_out_last_first_possible_rank_min":min(insertion_ranks),
        "leave_one_out_last_first_possible_rank_max":max(insertion_ranks),
        "all_replicas_have_last_shorter_than_prior_lower_median":
            all(last<x for x in medians),
    }


def compare_jackknives(first:dict,second:dict,
                       first_history_sha:str,second_history_sha:str,
                       first_last_sha:str,second_last_sha:str)->dict:
    # Fail closed using Stage329's existing original Stage328 source replay
    # and all four independent SHA-256 CSV pins.
    original=compare_shapes(first,second,first_history_sha,
                            second_history_sha,first_last_sha,second_last_sha)
    if original.get("schema")!=STAGE329_SCHEMA or original.get("result")!=STAGE329_RESULT:
        raise ExitTimelineError("Stage329 original distribution source verification missing")
    a=source_jackknife(first,first_history_sha,first_last_sha)
    b=source_jackknife(second,second_history_sha,second_last_sha)
    # A reversal of the last-call ordering under one deleted observation
    # is itself important evidence of *sensitivity*. Report it rather than
    # failing the source auditor or suppressing a genuine guest observation.
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":[{"cohort":"first",**a},{"cohort":"second",**b}],
        "both_stage329_original_source_receipts_independently_replayed":True,
        "leave_one_out_is_descriptive_not_population_confidence_interval":True,
        "only_previous_15_of_last_16_guest_calls_compared":True,
        "raw_guest_software_start_end_timestamps_not_published":True,
        "source_guest_clock_not_mapped_to_host_PCM_clock":True,
        "original_PS1_music_or_speaker_sound_verified":False,
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
            raise ExitTimelineError("cannot compare identical NeXium source capture directory")
        if a.output.is_symlink() or a.output.exists():
            raise ExitTimelineError("refuse overwrite of original Stage330 evidence")
        doc=compare_jackknives(
            load(a.first_root),load(a.second_root),
            a.first_history_sha256,a.second_history_sha256,
            a.first_last_sha256,a.second_last_sha256)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(doc,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":doc["result"],
            "cohorts":doc["cohorts"],
            "speaker_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE330_ORIGINAL_GUEST_JACKKNIFE_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "speaker_audio_verified":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
