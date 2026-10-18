#!/usr/bin/env python3
"""Stage288: bind archived scene INPUTs to exact NeXium guest audout calls.

The live original-guest-SD audits are historical. Reopen their bound
copies, independently reverify scene/clock/slow call timestamps and
reconcile all 51 second bins with Stage287. This is same guest monotonic
software timing, NEVER a scheduler trace, audio DAC or causal test.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import zipfile

from analyze_nexium_idle_switch_variability import DRAWS
from analyze_nexium_steady_second_profile import analyze_second_profile
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock,parse_scene_inputs
)
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_slow_calls import parse_slow,relate
from compare_nexium_idle_switch_pairs import audit_pair_archives
from compare_nexium_verified_slow_runs import PREFIX,audit_archive

SCHEMA="vh-nexium-audout-verified-scene-input-alignment/v1"
SECOND_NS=1_000_000_000
NEAR_NS=500_000_000
MODES=("idle","switch")
BANDS=("ge40","between40and50","ge50")
SOURCE_FILES={
    "clock":PREFIX+"soak-audout-clock-unverified.csv",
    "latency":PREFIX+"soak-audout-latency-unverified.csv",
    "slow":PREFIX+"soak-audout-slow-unverified.csv",
    "scene":PREFIX+"soak-guest-optical.csv",
}


def _counts(row:dict,band:str)->int:
    if band=="between40and50":
        return row["ge40"]-row["ge50"]
    if band in ("ge40","ge50"):
        return row[band]
    raise CorrelationError("unknown duration band")


def _pooled_rate(rows:list[dict],mode:str,band:str)->float:
    attempts=sum(r[mode]["attempts"] for r in rows)
    count=sum(_counts(r[mode],band) for r in rows)
    if attempts<=0 or count<0 or count>attempts:
        raise CorrelationError("invalid scene vs no-scene audout denominators")
    return round(float(Fraction(1000*count,attempts)),6)


def _partition_rates(rows:list[dict])->dict:
    if not rows:
        raise CorrelationError("empty input/time-control second collection")
    totals={}
    for mode in MODES:
        totals[mode]={
            "attempts":sum(row[mode]["attempts"] for row in rows),
            "ge40":sum(row[mode]["ge40"] for row in rows),
            "ge50":sum(row[mode]["ge50"] for row in rows),
        }
        totals[mode]["between40and50"]=(
            totals[mode]["ge40"]-totals[mode]["ge50"])
    rates={
        mode:{band:_pooled_rate(rows,mode,band) for band in BANDS}
        for mode in MODES
    }
    return {
        "matched_pair_seconds":len(rows),
        "totals":totals,
        "rate_per_1000":rates,
        "scene_switching_effect_identified":False,
    }


def analyze_scene_alignment(archives:list[Path], steady:dict,temporal:dict,
                            sensitivity:dict,contrasts:dict,boundary:dict,
                            grid:dict,disjoint:dict,exposure:dict,profile:dict,
                            draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded historical resample count")
    upstream=analyze_second_profile(
        steady,temporal,sensitivity,contrasts,boundary,grid,
        disjoint,exposure,draws=draws)
    if not isinstance(profile,dict) or profile!=upstream:
        raise CorrelationError("Stage287 51-second source witness does not reproduce")
    ids=upstream["source_run_ids"]
    if (len(archives)!=len(ids) or
            len({str(p.resolve()) for p in archives})!=len(ids)):
        raise CorrelationError("not exactly the bound independent archive set")
    whole=audit_pair_archives(archives)
    if (whole["independent_workflow_run_ids"]!=ids
            or whole["nro_sha256"]!=upstream["nro_sha256"]
            or whole["totals"]!=steady["source_full_run_totals"]):
        raise CorrelationError("Stage277 live-original-SD-backed archive set differs")
    pairs={p["run_id"]:p for p in steady["per_run_windows"]}
    if set(pairs)!=set(ids):
        raise CorrelationError("missing source workflow paired time windows")

    run_records=[]
    all_second_rows=[]
    near_events=[]
    for path in archives:
        # This rechecks archived original-SD hash/receipt witnesses,
        # individual nanosecond timings and historical scene relations.
        accepted=audit_archive(path)
        run_id=accepted["run_id"]
        if (run_id not in pairs
                or accepted["nro_sha256"]!=upstream["nro_sha256"]):
            raise CorrelationError("unknown scene/slow archive identity")
        with zipfile.ZipFile(path) as z:
            raw={key:z.read(name) for key,name in SOURCE_FILES.items()}
        clock=parse_clock(raw["clock"])
        latency=parse_latency(raw["latency"])
        calls=parse_slow(raw["slow"],clock["origin_ns"],latency)
        inputs=parse_scene_inputs(raw["scene"])
        verified_near=relate(calls,inputs)
        if (len(inputs)!=10 or len(verified_near)!=10
                or accepted["guest_scene_inputs"]!=len(inputs)):
            raise CorrelationError("missing actual guest scene switch input event")
        expected=pairs[run_id]
        for mode in MODES:
            selected=expected[mode]["per_second"]
            if len(selected)!=51:
                raise CorrelationError("missing paired idle/switch second")
            for idx,entry in enumerate(selected):
                second=idx+1
                if entry["second"]!=second:
                    raise CorrelationError("unmatched guest second in source")
                counted=[c for c in calls if c["audio_second"]==second] if mode=="switch" else None
                if counted is not None and (
                        len(counted)!=entry["ge40"] or
                        sum(c["duration_ns"]>=50_000_000 for c in counted)!=entry["ge50"]):
                    raise CorrelationError("scene slow timestamp disagrees with Stage287 bin")
        indexed={}
        for event,relation in zip(inputs,verified_near):
            second=(event["timestamp_ns"]-clock["origin_ns"])//SECOND_NS
            if not 1<=second<=51:
                raise CorrelationError("scene input outside common 51-second evidence")
            if second in indexed:
                raise CorrelationError("two guest scene INPUTs in same audio second")
            if relation["serial"]!=event["serial"]:
                raise CorrelationError("independent Stage274 scene serial mismatch")
            indexed[second]=event
            near=[c for c in calls
                  if abs(c["begin_ns"]-event["timestamp_ns"])<=NEAR_NS]
            if len(near)!=relation["slow_calls_start_within_500ms"]:
                raise CorrelationError("near-input slow call count not reproducible")
            before=sum(c["end_ns"]<=event["timestamp_ns"] for c in near)
            after=sum(c["begin_ns"]>=event["timestamp_ns"] for c in near)
            overlap=len(near)-before-after
            if (before!=relation["fully_ended_before_input"]
                    or after!=relation["began_after_input"]
                    or overlap!=relation["straddled_input"]):
                raise CorrelationError("relative slow call order inconsistent")
            bin_data=expected["switch"]["per_second"][second-1]
            near_events.append({
                "run_id":run_id,
                "scene_input_serial":event["serial"],
                "scene":event["scene"],
                "guest_input_ns":event["timestamp_ns"],
                "audout_guest_second":second,
                "slow_call_beginnings_within_500ms":len(near),
                "slow_40to50_beginnings_within_500ms":
                    sum(c["duration_ns"]<50_000_000 for c in near),
                "slow_ge50_beginnings_within_500ms":
                    sum(c["duration_ns"]>=50_000_000 for c in near),
                "slow_calls_completed_before_input":before,
                "slow_calls_began_after_input":after,
                "slow_calls_straddled_input":overlap,
                "same_second_switch_ge40":bin_data["ge40"],
                "same_second_switch_ge50":bin_data["ge50"],
                "timestamp_relation_only":True,
            })
        if len(indexed)!=10:
            raise CorrelationError("missing unique scene INPUT second")
        for second in range(1,52):
            idle=expected["idle"]["per_second"][second-1]
            switching=expected["switch"]["per_second"][second-1]
            all_second_rows.append({
                "run_id":run_id,"second":second,
                "contains_guest_scene_input":second in indexed,
                "idle":idle,"switch":switching,
            })
        run_records.append({
            "run_id":run_id,
            "nro_sha256":accepted["nro_sha256"],
            "guest_clock_origin_ns":clock["origin_ns"],
            "guest_scene_inputs":len(indexed),
            "input_relative_seconds":[
                (event["timestamp_ns"]-clock["origin_ns"])//SECOND_NS
                for event in inputs],
            "full_guest_slow_call_records_reverified":len(calls),
            "prior_live_original_sd_verified":True,
        })
    if ([r["run_id"] for r in run_records]!=ids
            or len(all_second_rows)!=51*len(ids)
            or len(near_events)!=10*len(ids)):
        raise CorrelationError("original-SD pairs/inputs not conserved")
    # Complete counts must match the independently validated Stage287
    # per-second columns. No host timestamps or guessed clock offsets.
    for second in range(1,52):
        grouped=[r for r in all_second_rows if r["second"]==second]
        source=upstream["per_second"][second-1]["totals"]
        if len(grouped)!=len(ids):
            raise CorrelationError("lost one workflow in event-second comparison")
        for mode in MODES:
            for name in ("attempts","ge40","ge50"):
                if sum(r[mode][name] for r in grouped)!=source[mode][name]:
                    raise CorrelationError("archival event-second bin mismatch")
    scene_rows=[r for r in all_second_rows if r["contains_guest_scene_input"]]
    other_rows=[r for r in all_second_rows if not r["contains_guest_scene_input"]]
    if len(scene_rows)!=len(ids)*10 or len(other_rows)!=len(ids)*41:
        raise CorrelationError("scene/non-scene relative second partition incomplete")
    return {
        "schema":SCHEMA,
        "result":"SAME_GUEST_CLOCK_SCENE_INPUT_AUDOUT_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":upstream["nro_sha256"],
        "pair_count":len(ids),
        "guest_scene_inputs_per_run":10,
        "near_window_begin_ns":-NEAR_NS,
        "near_window_end_ns":NEAR_NS,
        "runs":run_records,
        "events":near_events,
        "scene_input_seconds":_partition_rates(scene_rows),
        "other_guest_seconds":_partition_rates(other_rows),
        "all_matched_seconds":_partition_rates(all_second_rows),
        "near_input_slow_calls_ge40":sum(
            r["slow_call_beginnings_within_500ms"] for r in near_events),
        "near_input_slow_calls_40to50":sum(
            r["slow_40to50_beginnings_within_500ms"] for r in near_events),
        "near_input_slow_calls_ge50":sum(
            r["slow_ge50_beginnings_within_500ms"] for r in near_events),
        "original_ephemeral_guest_sd_reopened_offline":False,
        "historical_live_original_sd_audits_required":True,
        "upstream_stage287_recalculated_exactly":True,
        "same_guest_monotonic_clock_for_scene_and_audout":True,
        "host_pcm_clock_alignment_proven":False,
        "independent_audio_scheduler_event_trace_present":False,
        "event_second_intervals_not_randomized":True,
        "fixed_switch_before_idle_capture_order":True,
        "scene_switch_causality_proven":False,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",action="append",type=Path,required=True)
    for name in ("verified-steady-state","verified-temporal-thirds",
                 "verified-third-sensitivity","verified-temporal-contrasts",
                 "verified-boundary-shifts","verified-boundary-pair-grid",
                 "verified-disjoint-bands","verified-rate-exposure",
                 "verified-second-profile","output"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of earlier scene relation")
        def load(file:Path)->dict:
            return json.loads(file.read_text(encoding="utf-8"))
        report=analyze_scene_alignment(
            args.archive,
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
            load(args.verified_temporal_contrasts),
            load(args.verified_boundary_shifts),
            load(args.verified_boundary_pair_grid),
            load(args.verified_disjoint_bands),
            load(args.verified_rate_exposure),
            load(args.verified_second_profile),
        )
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],"pairs":report["pair_count"],
            "scene_inputs":len(report["events"]),
            "near_ge40":report["near_input_slow_calls_ge40"],
            "near_ge50":report["near_input_slow_calls_ge50"],
            "scene_second_rate_40_to_50":
                report["scene_input_seconds"]["rate_per_1000"]["switch"]["between40and50"],
            "non_scene_second_rate_40_to_50":
                report["other_guest_seconds"]["rate_per_1000"]["switch"]["between40and50"],
            "audible_audio_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError,zipfile.BadZipFile) as exc:
        print(json.dumps({"result":"SCENE_SLOW_ALIGNMENT_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
