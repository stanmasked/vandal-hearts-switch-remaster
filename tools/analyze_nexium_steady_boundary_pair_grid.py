#!/usr/bin/env python3
"""Stage284: audit five boundary shifts against every leave-one-pair deletion.

Separate observed switching and idle within-session temporal drift,
then recombine their rate differences for each of five fixed offsets.
Each of 8 run-pair deletions is evaluated at EVERY offset. Recompute
the entire Stage279..283 chain from the same source archive witnesses.
Software audout API timing only; not a device or causal measurement.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from analyze_nexium_steady_boundary_shifts import (
    analyze_boundary_shifts, _bounded_pair_window, OFFSETS,
    MIDDLE_START, LATE_START, BANDS
)
from analyze_nexium_idle_switch_variability import _rate
from audit_nexium_audout_scene_correlation import CorrelationError

SCHEMA="vh-nexium-audout-leave-one-pair-boundary-grid/v1"
MODES=("idle","switch")


def _mode_delta(first:list[dict], second:list[dict],
                mode:str, threshold:str)->float:
    if (mode not in MODES or threshold not in BANDS
            or len(first)!=len(second) or not first
            or [x["run_id"] for x in first]!=[x["run_id"] for x in second]):
        raise CorrelationError("invalid mode or nonmatching workflow pairs")
    return _rate(first,mode,threshold)-_rate(second,mode,threshold)


def _decompose(first:list[dict], second:list[dict], threshold:str)->dict:
    idle=_mode_delta(first,second,"idle",threshold)
    switching=_mode_delta(first,second,"switch",threshold)
    contrast=switching-idle
    return {
        "idle_earlier_minus_later_per_1000":round(idle,6),
        "switch_earlier_minus_later_per_1000":round(switching,6),
        "switch_drift_minus_idle_drift_per_1000":round(contrast,6),
        "_unrounded_contrast":contrast,
    }


def analyze_grid(steady:dict, temporal:dict, sensitivity:dict,
                 contrasts:dict, boundary:dict, draws:int=16384)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid resampling size")
    expected=analyze_boundary_shifts(
        steady,temporal,sensitivity,contrasts,draws=draws)
    if not isinstance(boundary,dict) or boundary!=expected:
        raise CorrelationError("Stage283 report differs from reaudited source")
    ids=expected["source_run_ids"]
    pairs=steady["steady_pair_verdict"]["pairs"]
    details=steady["per_run_windows"]
    if ([p["run_id"] for p in pairs]!=ids
            or [p["run_id"] for p in details]!=ids):
        raise CorrelationError("mixed source cohort in boundary grid")
    result=[]
    for shift,comparison in zip(OFFSETS,expected["candidate_boundaries"]):
        if comparison["shift_seconds"]!=shift:
            raise CorrelationError("shifted witness out of order")
        first_start=MIDDLE_START+shift
        second_start=LATE_START+shift
        first=[_bounded_pair_window(pair,detail,first_start)
               for pair,detail in zip(pairs,details)]
        second=[_bounded_pair_window(pair,detail,second_start)
                for pair,detail in zip(pairs,details)]
        bands={}
        for threshold in BANDS:
            base=_decompose(first,second,threshold)
            reference=comparison["bands"][threshold]
            if (base["switch_drift_minus_idle_drift_per_1000"]
                    !=reference["difference_of_pooled_rate_differences_per_1000"]):
                raise CorrelationError("independent mode drifts do not explain contrast")
            leaves=[]
            raw=[]
            for excluded in ids:
                earlier=[p for p in first if p["run_id"]!=excluded]
                later=[p for p in second if p["run_id"]!=excluded]
                drift=_decompose(earlier,later,threshold)
                raw.append(drift.pop("_unrounded_contrast"))
                leaves.append({"excluded_workflow_run_id":excluded,**drift})
            if (round(min(raw),6)!=reference["leave_one_pair_out_min_per_1000"]
                    or round(max(raw),6)!=reference["leave_one_pair_out_max_per_1000"]):
                raise CorrelationError("Stage283 leave-one bounds do not reconcile")
            bands[threshold]={
                "full_cohort_mode_drifts":{
                    k:v for k,v in base.items() if k!="_unrounded_contrast"
                },
                "leave_one_pair_out":leaves,
                "positive_leave_one_out":sum(x>0 for x in raw),
                "negative_leave_one_out":sum(x<0 for x in raw),
                "exact_zero_leave_one_out":sum(x==0 for x in raw),
                "all_leave_one_out_contrasts_positive":all(x>0 for x in raw),
                "leave_one_pair_out_min_per_1000":round(min(raw),6),
                "leave_one_pair_out_max_per_1000":round(max(raw),6),
            }
        result.append({
            "shift_seconds":shift,
            "earlier_guest_seconds":comparison["earlier_seconds"],
            "later_guest_seconds":comparison["later_seconds"],
            "bands":bands,
        })
    summaries={}
    for threshold in BANDS:
        all_leave=[value
                   for row in result
                   for value in row["bands"][threshold]["leave_one_pair_out"]]
        numeric=[x["switch_drift_minus_idle_drift_per_1000"]
                 for x in all_leave]
        summaries[threshold]={
            "total_shift_by_excluded_pair_cells":len(numeric),
            "positive_cells":sum(x>0 for x in numeric),
            "negative_cells":sum(x<0 for x in numeric),
            "exact_zero_cells":sum(x==0 for x in numeric),
            "minimum_cell_contrast_per_1000":min(numeric),
            "maximum_cell_contrast_per_1000":max(numeric),
            "every_shift_and_pair_deletion_stays_positive":all(x>0 for x in numeric),
        }
        if len(numeric)!=len(OFFSETS)*len(ids):
            raise CorrelationError("incomplete boundary x pair deletion matrix")
    return {
        "schema":SCHEMA,
        "result":"FIVE_BOUNDARIES_EIGHT_DELETIONS_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":expected["nro_sha256"],
        "pair_count":len(ids),
        "shift_count":len(result),
        "fixed_shifts_seconds":list(OFFSETS),
        "window_length_seconds":17,
        "grid":result,
        "matrix_summary":summaries,
        "stage283_recomputed_exactly_from_source":True,
        "same_workflow_pair_removed_in_both_modes_and_both_windows":True,
        "no_independent_per_window_resampling":True,
        "fixed_switch_before_idle_order":True,
        "overlapping_offsets_not_independent_observations":True,
        "is_statistical_significance_test":False,
        "scene_switch_causal_effect_established":False,
        "physical_switch_tested":False,
        "audible_underruns_or_DAC_clock_measured":False,
    }


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    for opt in ("verified-steady-state","verified-temporal-thirds",
                "verified-third-sensitivity","verified-temporal-contrasts",
                "verified-boundary-shifts","output"):
        ap.add_argument("--"+opt,type=Path,required=True)
    args=ap.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of earlier boundary grid")
        def load(p:Path)->dict:
            return json.loads(p.read_text(encoding="utf-8"))
        report=analyze_grid(
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
            load(args.verified_temporal_contrasts),
            load(args.verified_boundary_shifts),
        )
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],"pairs":report["pair_count"],
            "ge40_grid":report["matrix_summary"]["ge40"],
            "physical_hardware_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"BOUNDARY_PAIR_GRID_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
