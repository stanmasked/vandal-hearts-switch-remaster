#!/usr/bin/env python3
"""Stage282: within-pair temporal contrasts, using the SAME pair resample twice.

This is an exploratory sensitivity assessment of audited NeXium
blocking audout API calls. No physical/audio/causal inference is made.
The Stage279/280/281 reports MUST be generated together in the CI
workflow from the previously live-SD-audited archived source files.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_segment_sensitivity import analyze_sensitivity
from analyze_nexium_idle_switch_variability import (
    DRAWS, _difference, _median, _xorshift32
)

SCHEMA="vh-nexium-audout-paired-temporal-contrast/v1"
SEED=282
COMPARISONS=(
    ("early_minus_middle",0,1),
    ("middle_minus_late",1,2),
    ("early_minus_late",0,2),
)


def _paired_contrast(earlier:list[dict],later:list[dict],band:str)->float:
    if ([r["run_id"] for r in earlier]!=[r["run_id"] for r in later]
            or not earlier or len(earlier)!=len(later)):
        raise CorrelationError("temporal cohorts are not identical run pairs")
    return _difference(earlier,band)-_difference(later,band)


def _resample_correlated(earlier:list[dict],later:list[dict],
                         band:str,draws:int)->dict:
    # The SAME randomly selected run IDs occur in both time windows.
    # Never bootstrap audout calls or select unrelated samples per window.
    state=SEED
    n=len(earlier)
    observations=[]
    for _ in range(draws):
        chosen=[]
        for _ in range(n):
            state=_xorshift32(state)
            chosen.append(state % n)
        diff=_paired_contrast([earlier[i] for i in chosen],
                              [later[i] for i in chosen],band)
        if not math.isfinite(diff):
            raise CorrelationError("nonfinite paired temporal contrast")
        observations.append(diff)
    observations.sort()
    return {
        "method":"fixed-seed same-pair correlated-window descriptive resampling",
        "resamples":draws,
        "seed":SEED,
        "p025_earlier_minus_later_per_1000":
            round(observations[int(.025*(draws-1))],6),
        "p975_earlier_minus_later_per_1000":
            round(observations[int(.975*(draws-1))],6),
        "is_formal_confidence_interval":False,
        "is_randomization_test":False,
    }


def analyze_contrasts(steady:dict,temporal:dict,
                      sensitivity:dict,draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded whole-pair resampling count")
    # A downstream JSON file may not silently fabricate any upstream
    # per-second count, cohort identity, statistical band, or device claim.
    expected=analyze_sensitivity(steady,temporal,draws=draws)
    if not isinstance(sensitivity,dict) or sensitivity!=expected:
        raise CorrelationError("Stage281 sensitivity is stale or not reproducible")
    segments=temporal["segments"]
    ids=sensitivity["source_run_ids"]
    results=[]
    for label,first,second in COMPARISONS:
        earlier=segments[first]
        later=segments[second]
        a,b=earlier["per_run_pairs"],later["per_run_pairs"]
        if ([p["run_id"] for p in a]!=ids or
                [p["run_id"] for p in b]!=ids):
            raise CorrelationError("different workflow identities in temporal contrast")
        bands={}
        for threshold in ("ge40","ge50"):
            pair_deltas=[
                _paired_contrast([left],[right],threshold)
                for left,right in zip(a,b)
            ]
            loo=[
                _paired_contrast(
                    [p for p in a if p["run_id"]!=identity],
                    [p for p in b if p["run_id"]!=identity],
                    threshold,
                ) for identity in ids
            ]
            aggregate=_paired_contrast(a,b,threshold)
            reported=(
                sensitivity["thirds"][first]["bands"][threshold][
                    "aggregate_switch_minus_idle_per_1000"]
                -sensitivity["thirds"][second]["bands"][threshold][
                    "aggregate_switch_minus_idle_per_1000"]
            )
            # Stage281 serializes the two rates separately to six decimals.
            # Their subtraction may differ from the unrounded contrast
            # by up to one unit in the sixth decimal place.
            if abs(aggregate-reported)>0.000001000001:
                raise CorrelationError("Stage281 differences contradict temporal contrast")
            bands[threshold]={
                "aggregate_earlier_minus_later_per_1000":round(aggregate,6),
                "per_pair_earlier_minus_later_per_1000":
                    [round(delta,6) for delta in pair_deltas],
                "median_per_pair_per_1000":round(_median(pair_deltas),6),
                "positive_pairs":sum(x>0 for x in pair_deltas),
                "negative_pairs":sum(x<0 for x in pair_deltas),
                "exact_ties":sum(x==0 for x in pair_deltas),
                "leave_one_pair_out_min_per_1000":round(min(loo),6),
                "leave_one_pair_out_max_per_1000":round(max(loo),6),
                "same_pair_correlated_resampling":
                    _resample_correlated(a,b,threshold,draws),
            }
        results.append({
            "name":label,
            "earlier_guest_seconds":[earlier["first_guest_second"],
                                      earlier["last_guest_second"]],
            "later_guest_seconds":[later["first_guest_second"],
                                    later["last_guest_second"]],
            "bands":bands,
        })
    return {
        "schema":SCHEMA,
        "result":"VERIFIED_EIGHT_PAIR_TEMPORAL_CONTRAST_SENSITIVITY",
        "source_run_ids":ids,
        "nro_sha256":sensitivity["nro_sha256"],
        "pair_count":len(ids),
        "contrasts":results,
        "middle_minus_late_ge40_per_1000":
            results[1]["bands"]["ge40"][
                "aggregate_earlier_minus_later_per_1000"],
        "upstream_281_exactly_recalculated":True,
        "same_pair_indices_used_in_both_resampled_windows":True,
        "fixed_switch_then_idle_order":True,
        "randomized_experiment":False,
        "confidence_interval_claim":False,
        "music_switch_causality_established":False,
        "audible_or_hardware_measurement":False,
        "physical_switch_tested":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-steady-state",type=Path,required=True)
    parser.add_argument("--verified-temporal-thirds",type=Path,required=True)
    parser.add_argument("--verified-third-sensitivity",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse replacement of previous temporal contrast")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        verdict=analyze_contrasts(
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
        )
        args.output.write_text(json.dumps(verdict,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        middle=verdict["contrasts"][1]["bands"]["ge40"]
        print(json.dumps({
            "result":verdict["result"],
            "pairs":verdict["pair_count"],
            "middle_minus_late_ge40_per_1000":
                verdict["middle_minus_late_ge40_per_1000"],
            "ge40_positive_pairs":middle["positive_pairs"],
            "ge40_leave_one_out":[
                middle["leave_one_pair_out_min_per_1000"],
                middle["leave_one_pair_out_max_per_1000"],
            ],
            "causality_proven":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"TEMPORAL_CONTRAST_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
