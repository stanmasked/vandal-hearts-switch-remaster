#!/usr/bin/env python3
"""Stage337: four genuine NeXium guest/host source captures; NRO bind last two.

Replays the first three originals via Stage335, independently replays the
fourth Stage334 original receipt and fourth Stage336 NRO/monitor binding.
Also independently binds the historical third source to its own original
same-run NRO/monitor evidence. All original CSV sets must be distinct.

A source-matched NRO proves within-workflow provenance, NOT third-party
attestation, physical Switch audio, game soundtrack quality or PCM playback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import audit_original_capture,load
from audit_nexium_stage336_capture_build_binding import bind_sources,read_json,RESULT as STAGE336_RESULT
from compare_nexium_stage335_three_original_capture_sources import (
    audit_three,locate_runtime_root,ALL_PINS,RESULT as STAGE335_RESULT,
)

SCHEMA="vh-stage337-four-genuine-neXium-guest-host-source-to-nro-cohorts/v1"
RESULT="FOUR_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_CAPTURE_COHORTS_SOURCE_VERIFIED"


def compare_four(sources:list[dict],old_pins:list[dict],
                 third_saved:dict,third_preflight:dict,third_monitor:dict,
                 fourth_saved:dict,fourth_binding_saved:dict,
                 fourth_preflight:dict,fourth_monitor:dict,
                 *,third_sha:str,third_run_id:int,third_attempt:int,
                 fourth_sha:str,fourth_run_id:int,fourth_attempt:int)->dict:
    if len(sources)!=4 or third_run_id==fourth_run_id or third_sha==fourth_sha:
        raise ExitTimelineError("four original captures and two distinct run builds required")
    old=audit_three(sources[:3],old_pins,third_saved)
    if old.get("result")!=STAGE335_RESULT:
        raise ExitTimelineError("historical three original NeXium captures not source replayed")
    fourth=audit_original_capture(sources[3])
    if fourth!=fourth_saved:
        raise ExitTimelineError("new fourth Stage334 source receipt differs from exact archive")
    third_bound=bind_sources(
        sources[2],third_saved,third_preflight,third_monitor,
        git_sha=third_sha,run_id=third_run_id,run_attempt=third_attempt)
    fourth_bound=bind_sources(
        sources[3],fourth_saved,fourth_preflight,fourth_monitor,
        git_sha=fourth_sha,run_id=fourth_run_id,run_attempt=fourth_attempt)
    if (third_bound.get("result")!=STAGE336_RESULT
            or fourth_bound!=fourth_binding_saved
            or fourth_bound.get("result")!=STAGE336_RESULT
            or fourth_bound.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("original third/fourth NRO, PCM monitor or receipt differs")
    for key in ALL_PINS:
        if len({r[key] for r in [*(old["cohorts"]),fourth]})!=4:
            raise ExitTimelineError("four original guest or host CSVs have duplicate source identity")
    rows=[*old["cohorts"],{
        "source":"original_fourth",
        **{k:fourth[k] for k in ALL_PINS},
        "guest_normal_call_count":fourth["original_guest_normal_call_count"],
        "guest_retained_call_count":fourth["original_guest_retained_call_count"],
        "guest_previous_successful_calls_in_window":
            fourth["original_guest_previous_successful_calls_in_window"],
        "guest_last_software_duration_ns":
            fourth["original_guest_last_call_duration_software_ns"],
        "guest_prior_lower_median_software_ns":
            fourth["original_guest_prior_lower_median_software_ns"],
        "guest_prior_median_minus_last_software_ns":
            fourth["original_guest_prior_median_minus_last_software_ns"],
        "guest_previous_faster_equal_slower_counts":
            fourth["original_guest_prior_faster_equal_slower_counts"],
        "guest_last_first_possible_rank":
            fourth["original_guest_last_call_first_possible_rank"],
        "host_control_intervals":fourth["original_host_control_deltas"],
    }]
    last=rows[-1]
    differences=[]
    for earlier in rows[:3]:
        a=last["guest_prior_lower_median_software_ns"]
        b=earlier["guest_prior_lower_median_software_ns"]
        differences.append({
            "fourth_minus_earlier_guest_last_software_ns":
                last["guest_last_software_duration_ns"]-earlier[
                    "guest_last_software_duration_ns"],
            "fourth_minus_earlier_guest_prior_median_software_ns":
                (a-b) if a is not None and b is not None else None,
            "fourth_minus_earlier_host_monotonic_control_deltas_ns":[
                x["host_monotonic_delta_ns"]-y["host_monotonic_delta_ns"]
                for x,y in zip(last["host_control_intervals"],
                               earlier["host_control_intervals"])],
        })
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":rows,
        "fourth_minus_previous_three_own_clock_differences":differences,
        "original_third_run_id":third_run_id,
        "original_fourth_run_id":fourth_run_id,
        "third_same_run_nro_sha256":third_bound["source_nro_sha256"],
        "fourth_same_run_nro_sha256":fourth_bound["source_nro_sha256"],
        "third_and_fourth_nro_sha256_match":
            third_bound["source_nro_sha256"]==fourth_bound["source_nro_sha256"],
        "all_three_previous_stage335_original_sources_replayed":True,
        "original_fourth_stage334_receipt_recomputed_exactly":True,
        "original_fourth_stage336_receipt_recomputed_exactly":True,
        "historical_third_and_new_fourth_NRO_PCM_monitor_source_bound":True,
        "all_four_original_guest_host_CSV_source_hashes_distinct":True,
        "no_software_guest_clock_converted_into_host_PCM_clock":True,
        "host_PCM_byte_size_is_not_sample_exact_audio_playback":True,
        "no_absolute_original_host_or_guest_timestamps_published":True,
        "no_independent_runner_or_physical_NRO_attestation":True,
        "original_PS1_soundtrack_or_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def find_unique(archive:Path,name:str,*,limit:int=65_536)->Path:
    if archive.is_symlink() or not archive.is_dir():
        raise ExitTimelineError("missing or symlinked original archive")
    candidates=list(archive.rglob(name))
    accepted=[p for p in candidates if p.is_file() and not p.is_symlink()
              and all(not a.is_symlink() for a in p.relative_to(archive).parents)
              and 0<p.stat().st_size<=limit]
    if len(candidates)!=1 or len(accepted)!=1:
        raise ExitTimelineError("missing or ambiguous source receipt/preflight in original archive")
    return accepted[0]


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for label in ("first","second","third","fourth"):
        p.add_argument(f"--{label}-archive",required=True,type=Path)
    p.add_argument("--old-pins",required=True,type=Path)
    p.add_argument("--third-git-sha",required=True)
    p.add_argument("--third-run-id",required=True,type=int)
    p.add_argument("--third-attempt",required=True,type=int)
    p.add_argument("--fourth-git-sha",required=True)
    p.add_argument("--fourth-run-id",required=True,type=int)
    p.add_argument("--fourth-attempt",required=True,type=int)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        archives=[getattr(args,f"{label}_archive") for label in ("first","second","third","fourth")]
        if len({p.resolve() for p in archives})!=4:
            raise ExitTimelineError("four distinct source archive directories required")
        if args.output.exists() or args.output.is_symlink():
            raise ExitTimelineError("refuse overwrite original capture source verification")
        roots=[locate_runtime_root(p) for p in archives]
        original=[load(root) for root in roots]
        if args.old_pins.is_symlink() or not args.old_pins.is_file() or args.old_pins.stat().st_size>4096:
            raise ExitTimelineError("previous original source SHA-256 pins missing")
        old_pins=json.loads(args.old_pins.read_text(encoding="utf-8"))
        third_saved=read_json(find_unique(archives[2],"source-guest-host-stage334.json"))
        fourth_saved=read_json(find_unique(archives[3],"source-guest-host-stage334.json"))
        fourth_binding=read_json(find_unique(archives[3],"source-capture-to-build-stage336.json"))
        report=compare_four(
            original,old_pins,
            third_saved,read_json(find_unique(archives[2],"integrated-nro-preflight.json"),max_bytes=4096),
            read_json(find_unique(archives[2],"pcm-quality-report.json")),
            fourth_saved,fourth_binding,
            read_json(find_unique(archives[3],"integrated-nro-preflight.json"),max_bytes=4096),
            read_json(find_unique(archives[3],"pcm-quality-report.json")),
            third_sha=args.third_git_sha,third_run_id=args.third_run_id,
            third_attempt=args.third_attempt,fourth_sha=args.fourth_git_sha,
            fourth_run_id=args.fourth_run_id,fourth_attempt=args.fourth_attempt)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":report["result"],
            "original_software_cohorts":[{
                "name":r["source"],
                "last_guest_software_ns":r["guest_last_software_duration_ns"],
                "prior_guest_median_ns":r["guest_prior_lower_median_software_ns"],
                "rank":r["guest_last_first_possible_rank"],
            } for r in report["cohorts"]],
            "physical_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE337_FOUR_INDEPENDENT_NEXIUM_SOURCE_RUNS_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
