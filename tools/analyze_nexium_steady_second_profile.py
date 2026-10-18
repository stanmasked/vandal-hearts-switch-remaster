#!/usr/bin/env python3
"""Stage287: exact per-second NeXium audout slow-call concentration.

Partition already original-SD-bound guest audio service seconds 1..51
into disjoint 40..<50ms and >=50ms blocking audout calls. Retain exact
per-second denominators, matched workflow IDs and complete count
conservation. Do not confuse software API timing with scheduler, DAC,
hardware or audible audio evidence.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_idle_switch_variability import DRAWS
from analyze_nexium_steady_segments import (
    _row, BEGIN_SECOND, END_SECOND, METRICS
)
from analyze_nexium_steady_rate_exposure import analyze_exposure
from analyze_nexium_steady_disjoint_bands import BANDS, MODES

SCHEMA="vh-nexium-audout-exact-second-profile/v1"
COUNTS=("attempts","ge40","ge50","between40and50")
TOP_N=5


def _pooled_counts(rows:list[dict], mode:str)->dict:
    attempts=sum(r[mode]["attempts"] for r in rows)
    forty=sum(r[mode]["ge40"] for r in rows)
    fifty=sum(r[mode]["ge50"] for r in rows)
    if not (attempts>0 and 0<=fifty<=forty<=attempts):
        raise CorrelationError("invalid per-second pooled audout histogram")
    return {
        "attempts":attempts,
        "ge40":forty,
        "ge50":fifty,
        "between40and50":forty-fifty,
    }


def _difference_counts(idle:dict,switch:dict,band:str)->Fraction:
    if band not in BANDS:
        raise CorrelationError("unexpected duration band")
    return (Fraction(1000*switch[band],switch["attempts"])
            -Fraction(1000*idle[band],idle["attempts"]))


def _concentration(magnitudes:list[tuple[int,Fraction]])->dict:
    if not magnitudes or any(type(second) is not int or
                             abs(value)!=value for second,value in magnitudes):
        raise CorrelationError("invalid absolute-second concentration trace")
    ranked=sorted(magnitudes,key=lambda r:(-r[1],r[0]))
    mass=sum((value for _,value in magnitudes),Fraction(0))
    selected=sum((value for _,value in ranked[:TOP_N]),Fraction(0))
    if mass==0:
        share=0.0
    else:
        share=round(100*float(selected/mass),3)
    return {
        "definition":"top five of 51 absolute individual-second rate gaps (L1)",
        "top_seconds":[{"second":second,"absolute_per_1000":round(float(value),6)}
                       for second,value in ranked[:TOP_N]],
        "top_five_share_percent":share,
        "all_51_abs_rate_gap_sum_per_1000":round(float(mass),6),
        "not_share_of_whole_51s_pooled_rate":True,
    }


def _longest_positive_streak(ordered:list[tuple[int,Fraction]])->int:
    longest=0
    current=0
    last=None
    for second,rate in ordered:
        if last is not None and second!=last+1:
            raise CorrelationError("gap in per-second order")
        current=current+1 if rate>0 else 0
        longest=max(longest,current)
        last=second
    return longest


def analyze_second_profile(steady:dict,temporal:dict,sensitivity:dict,
                           contrasts:dict,boundary:dict,grid:dict,
                           disjoint:dict,exposure:dict,draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded upstream resampling count")
    # Fail closed if ANY preceding live-SD-bound archive reconstruction,
    # historical report, pair ID, NRO or count witness is inconsistent.
    expected=analyze_exposure(steady,temporal,sensitivity,contrasts,
                              boundary,grid,disjoint,draws=draws)
    if not isinstance(exposure,dict) or exposure!=expected:
        raise CorrelationError("Stage286 exact rate-exposure report not reproducible")
    ids=expected["source_run_ids"]
    source_pairs=steady["steady_pair_verdict"]["pairs"]
    details=steady["per_run_windows"]
    if ([p["run_id"] for p in source_pairs]!=ids or
            [d["run_id"] for d in details]!=ids):
        raise CorrelationError("missing matched source workflow identity")

    # Independently revalidate all 51 already timestamp-audited counters
    # rather than trusting a derived report's per-second rates.
    per_run=[]
    for pair,detail in zip(source_pairs,details):
        record={"run_id":pair["run_id"]}
        for mode in MODES:
            window=detail.get(mode)
            if not isinstance(window,dict):
                raise CorrelationError("missing source audout mode trace")
            entries=window.get("per_second")
            if not isinstance(entries,list) or len(entries)!=END_SECOND-BEGIN_SECOND+1:
                raise CorrelationError("guest second count differs from 51")
            rows=[_row(entry,second)
                  for second,entry in zip(range(BEGIN_SECOND,END_SECOND+1),entries)]
            for field in METRICS:
                if sum(entry[field] for entry in rows)!=pair[f"{mode}_{field}"]:
                    raise CorrelationError("source per-second values do not conserve pairs")
            record[mode]=rows
        per_run.append(record)

    seconds=[]
    exact_by_band={band:[] for band in BANDS}
    for second in range(BEGIN_SECOND,END_SECOND+1):
        offset=second-BEGIN_SECOND
        raw=[{
            "run_id":p["run_id"],
            "idle":p["idle"][offset],
            "switch":p["switch"][offset],
        } for p in per_run]
        pooled={mode:_pooled_counts(raw,mode) for mode in MODES}
        differences={band:_difference_counts(
            pooled["idle"],pooled["switch"],band) for band in BANDS}
        if differences["ge40"]!=(
                differences["between40and50"]+differences["ge50"]):
            raise CorrelationError("single second loss in exact duration partition")
        signs={}
        for band in BANDS:
            pair_diffs=[]
            for r in raw:
                idle={**r["idle"],
                      "between40and50":r["idle"]["ge40"]-r["idle"]["ge50"]}
                switch={**r["switch"],
                        "between40and50":r["switch"]["ge40"]-r["switch"]["ge50"]}
                pair_diffs.append(_difference_counts(idle,switch,band))
            signs[band]={
                "switch_higher_pairs":sum(v>0 for v in pair_diffs),
                "idle_higher_pairs":sum(v<0 for v in pair_diffs),
                "equal_pairs":sum(v==0 for v in pair_diffs),
            }
            if sum(signs[band].values())!=len(ids):
                raise CorrelationError("missing individual paired guest second")
            exact_by_band[band].append((second,differences[band]))
        seconds.append({
            "guest_audio_service_second":second,
            "totals":pooled,
            "switch_minus_idle_per_1000":{
                band:round(float(differences[band]),6) for band in BANDS},
            "paired_rate_directions":signs,
        })

    # Integer conservation to ALL 51s totals and to Stage280's
    # three disjoint, individually-audited 17-second partitions.
    full=steady["steady_pair_verdict"]["totals"]
    for mode in MODES:
        for field in METRICS:
            val=sum(row["totals"][mode][field] for row in seconds)
            if val!=full[f"{mode}_{field}"]:
                raise CorrelationError("per-second pooling does not conserve full 51s")
    for third in temporal["segments"]:
        a,b=third["first_guest_second"],third["last_guest_second"]
        segment=seconds[a-BEGIN_SECOND:b-BEGIN_SECOND+1]
        if len(segment)!=17:
            raise CorrelationError("Stage280 third is incomplete")
        for mode in MODES:
            for field in METRICS:
                val=sum(row["totals"][mode][field] for row in segment)
                if val!=third["totals"][f"{mode}_{field}"]:
                    raise CorrelationError("single seconds do not reconstruct Stage280")
        for band in ("ge40","ge50"):
            modecounts={
                mode:{field:sum(row["totals"][mode][field] for row in segment)
                      for field in COUNTS} for mode in MODES
            }
            rate=_difference_counts(modecounts["idle"],modecounts["switch"],band)
            if abs(float(rate)-third["switch_minus_idle_per_1000"][band])>0.000001000001:
                raise CorrelationError("per-second derived third rate disagrees")

    descriptions={}
    for band in BANDS:
        observations=exact_by_band[band]
        descriptions[band]={
            "positive_seconds":sum(v>0 for _,v in observations),
            "negative_seconds":sum(v<0 for _,v in observations),
            "exact_zero_seconds":sum(v==0 for _,v in observations),
            "longest_consecutive_positive_seconds":_longest_positive_streak(observations),
            "absolute_gap_concentration":_concentration([
                (second,abs(value)) for second,value in observations]),
        }
        if sum(descriptions[band][k] for k in (
                "positive_seconds","negative_seconds","exact_zero_seconds"))!=51:
            raise CorrelationError("not exactly 51 rated software seconds")

    return {
        "schema":SCHEMA,
        "result":"AUDITED_51_SECOND_SLOW_CALL_CONCENTRATION_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":expected["nro_sha256"],
        "pair_count":len(ids),
        "seconds_included":51,
        "excluded_startup_guest_second":0,
        "per_second":seconds,
        "band_summary":descriptions,
        "exact_count_and_17s_third_conservation":True,
        "exact_ge40_equals_two_disjoint_bands_before_rounding":True,
        "upstream_stage286_recomputed_exactly":True,
        "same_workflow_pairs_in_each_second":True,
        "top_five_seconds_selected_post_hoc_not_independent":True,
        "guest_service_seconds_not_scheduler_execution_trace":True,
        "fixed_switch_before_idle_capture_order":True,
        "music_switch_causality_proven":False,
        "physical_switch_tested":False,
        "DAC_underruns_or_audible_glitches_measured":False,
    }


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    for field in ("verified-steady-state","verified-temporal-thirds",
                  "verified-third-sensitivity","verified-temporal-contrasts",
                  "verified-boundary-shifts","verified-boundary-pair-grid",
                  "verified-disjoint-bands","verified-rate-exposure","output"):
        ap.add_argument("--"+field,type=Path,required=True)
    args=ap.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of historical second profile")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        report=analyze_second_profile(
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
            load(args.verified_temporal_contrasts),
            load(args.verified_boundary_shifts),
            load(args.verified_boundary_pair_grid),
            load(args.verified_disjoint_bands),
            load(args.verified_rate_exposure),
        )
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],"pairs":report["pair_count"],
            "bands":report["band_summary"],"causality_proven":False,
        },sort_keys=True))
        return 0
    except (OSError,TypeError,ValueError,UnicodeError) as exc:
        print(json.dumps({"result":"SECOND_PROFILE_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
