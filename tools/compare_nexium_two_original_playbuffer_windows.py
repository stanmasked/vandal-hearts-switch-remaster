#!/usr/bin/env python3
"""Stage324: compare two INDEPENDENTLY reaudited original guest PlayBuffer windows.

Two separately successful NeXium runs must supply separate byte-original
guest artifacts. Replay complete Stage323 source chain for EACH before
computing two-run within-capture final-call vs 15 prior call comparisons.
No host PCM/DAC clock calibration, audible Plus claim or original music.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_switch_guest_scene_trace import TraceError
from replay_nexium_original_playbuffer_history_archive import (
    read_archive, replay_original_history, VERIFIED as SOURCE_VERIFIED,
)

SCHEMA="vh-independent-two-run-original-last16-PlayBuffer-cohort/v1"
VERIFIED="TWO_ORIGINAL_GUEST_PLAYBUFFER_WINDOWS_INDEPENDENTLY_REPLAYED"


def compare_replays(a:dict,b:dict)->dict:
    if not isinstance(a,dict) or not isinstance(b,dict):
        raise TraceError("two distinct original guest audout sources are required")
    for sample in (a,b):
        if (sample.get("result")!=SOURCE_VERIFIED or
                sample.get("original_stage322_history_CSV_and_receipt_replayed") is not True or
                sample.get("original_stage307_308_310_313_314_317_320_321_sources_replayed") is not True or
                sample.get("guest_software_call_is_NOT_DAC_or_speaker_sound") is not True or
                sample.get("physical_Nintendo_Switch_audio_tested") is not False or
                sample.get("original_guest_to_host_PCM_clock_fit_verified") is not False or
                sample.get("plus_caused_audible_dropout_verified") is not False):
            raise TraceError("unverified or overclaimed original guest source")
        for name in ("original_source_workflow_run_id",
                     "source_call_count","recent_original_service_call_count",
                     "last_successful_duration_guest_ns",
                     "prior_successful_calls_in_window",
                     "prior_successful_calls_shorter_than_last",
                     "prior_successful_calls_equal_to_last",
                     "prior_successful_calls_longer_than_last"):
            if type(sample.get(name)) is not int or sample[name]<0:
                raise TraceError("missing/noninteger original guest call metrics")
        if not sample["original_source_workflow_run_id"]:
            raise TraceError("invalid original workflow source identity")
        n=sample["prior_successful_calls_in_window"]
        if (not 0<sample["recent_original_service_call_count"]<=16
                or sample["source_call_count"]<sample["recent_original_service_call_count"]
                or not 0<n<=15
                or not sample["has_source_verified_prior_call_baseline"]
                or sample["prior_successful_lower_median_duration_guest_ns"] is None):
            raise TraceError("insufficient source-backed prior normal audout calls")
        if (sample["prior_successful_calls_shorter_than_last"]+
            sample["prior_successful_calls_equal_to_last"]+
            sample["prior_successful_calls_longer_than_last"] != n or
            sample["last_call_ascending_rank_among_prior_plus_last"] !=
                sample["prior_successful_calls_shorter_than_last"]+1 or
            sample["last_minus_prior_lower_median_guest_ns"] !=
                sample["last_successful_duration_guest_ns"]-
                sample["prior_successful_lower_median_duration_guest_ns"]):
            raise TraceError("per-run original source timing conservation broken")
        if sample["prior_successful_duration_rank_is_only_this_bounded_window"] is not True:
            raise TraceError("source rank claimed beyond bounded window")
    if a["original_source_workflow_run_id"]==b["original_source_workflow_run_id"]:
        raise TraceError("same original workflow cannot prove two runs")
    for k in ("original_guest_history_csv_sha256",
              "original_guest_exit_csv_sha256",
              "original_guest_optical_crc_PNG_sha256"):
        v1,v2=a.get(k),b.get(k)
        if (not isinstance(v1,str) or not isinstance(v2,str) or
                len(v1)!=64 or len(v2)!=64 or
                v1==v2 or any(ch not in "0123456789abcdef" for ch in v1+v2)):
            raise TraceError("original guest software sources are not independently distinct")
    inputs=[a,b]
    samples=[
        {
            "original_neXium_run_id":sample["original_source_workflow_run_id"],
            "original_guest_history_csv_sha256":sample["original_guest_history_csv_sha256"],
            "original_guest_exit_csv_sha256":sample["original_guest_exit_csv_sha256"],
            "original_guest_optical_PNG_sha256":sample["original_guest_optical_crc_PNG_sha256"],
            "original_call_window_size":sample["recent_original_service_call_count"],
            "prior_successes_in_window":sample["prior_successful_calls_in_window"],
            "final_successful_call_duration_guest_ns":sample["last_successful_duration_guest_ns"],
            "prior_successful_lower_median_guest_ns":
                sample["prior_successful_lower_median_duration_guest_ns"],
            "final_minus_prior_median_guest_ns":sample["last_minus_prior_lower_median_guest_ns"],
            "final_call_ascending_rank_in_window":
                sample["last_call_ascending_rank_among_prior_plus_last"],
            "prior_shorter":sample["prior_successful_calls_shorter_than_last"],
            "prior_equal":sample["prior_successful_calls_equal_to_last"],
            "prior_longer":sample["prior_successful_calls_longer_than_last"],
            "final_below_own_prior_median":
                sample["last_minus_prior_lower_median_guest_ns"]<0,
        }
        for sample in inputs
    ]
    both_below=all(s["final_below_own_prior_median"] for s in samples)
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "independent_original_workflow_run_count":2,
        "source_runs":samples,
        "both_original_guest_archive_chains_independently_replayed":True,
        "both_have_source_verified_prior_baseline":True,
        "both_final_calls_below_own_prior_lower_median":both_below,
        "last_call_guest_duration_difference_second_minus_first_ns":
            b["last_successful_duration_guest_ns"]-
            a["last_successful_duration_guest_ns"],
        "prior_lower_median_difference_second_minus_first_ns":
            b["prior_successful_lower_median_duration_guest_ns"]-
            a["prior_successful_lower_median_duration_guest_ns"],
        "two_captures_do_not_establish_population_latency_distribution":True,
        "guest_software_times_not_host_PCM_or_DAC_samples":True,
        "retail_PlayStation_music_fidelity_verified":False,
        "audible_Plus_audio_dropout_causality_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def audit_two_original_archives(old_root:Path,new_root:Path,
                                old_id:int,new_id:int)->dict:
    if (type(old_id) is not int or type(new_id) is not int or
            old_id<=0 or new_id<=0 or old_id==new_id):
        raise TraceError("two distinct positive original capture run IDs are required")
    return compare_replays(
        replay_original_history(*read_archive(old_root),old_id),
        replay_original_history(*read_archive(new_root),new_id),
    )


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-run-id",type=int,required=True)
    p.add_argument("--first-archive",type=Path,required=True)
    p.add_argument("--second-run-id",type=int,required=True)
    p.add_argument("--second-archive",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise TraceError("refuse overwrite previously published source evidence")
        r=audit_two_original_archives(a.first_archive,a.second_archive,
                                      a.first_run_id,a.second_run_id)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":r["result"],
            "two_source_workflow_run_ids":
                [s["original_neXium_run_id"] for s in r["source_runs"]],
            "both_final_below_own_source_median":
                r["both_final_calls_below_own_prior_lower_median"],
            "audible_speaker_sound_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE324_TWO_ORIGINAL_PLAYBUFFER_CAPTURES_NOT_VERIFIED",
            "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
