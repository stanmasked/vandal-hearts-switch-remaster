#!/usr/bin/env python3
"""Stage285: exact integer-count decomposition of NeXium 40ms slow-call drift.

Splits ≥40ms calls into disjoint 40..<50ms and ≥50ms classes for each
of five overlapping 17s boundary positions and all 8 source-pair
deletions. Every identity is exact rational arithmetic BEFORE six-
decimal serialization. Never infer audible glitches or causality.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from analyze_nexium_idle_switch_variability import DRAWS
from analyze_nexium_steady_boundary_pair_grid import analyze_grid
from analyze_nexium_steady_boundary_shifts import (
    OFFSETS,MIDDLE_START,LATE_START,_bounded_pair_window
)
from audit_nexium_audout_scene_correlation import CorrelationError

SCHEMA="vh-nexium-disjoint-slow-call-temporal-components/v1"
BANDS=("ge40","between40and50","ge50")
MODES=("idle","switch")
ROUNDED_TOLERANCE=0.000001000001


def _count(row:dict,mode:str,band:str)->int:
    forty=row[f"{mode}_ge40"]
    fifty=row[f"{mode}_ge50"]
    value=(forty-fifty if band=="between40and50"
           else row[f"{mode}_{band}"])
    attempts=row[f"{mode}_attempts"]
    if (type(value) is not int or type(attempts) is not int
            or not 0<=fifty<=forty<=attempts or attempts<=0
            or not 0<=value<=attempts):
        raise CorrelationError("invalid or overlapping disjoint slow-call counts")
    return value


def _per_mode_rate(rows:list[dict],mode:str,band:str)->Fraction:
    if mode not in MODES or band not in BANDS or not rows:
        raise CorrelationError("invalid mode/band or empty original-source cohort")
    total_calls=sum(_count(row,mode,band) for row in rows)
    attempts=sum(row[f"{mode}_attempts"] for row in rows)
    return Fraction(1000*total_calls,attempts)


def _raw_components(earlier:list[dict],later:list[dict])->dict:
    if (not earlier or len(earlier)!=len(later)
            or [x["run_id"] for x in earlier]!=
               [x["run_id"] for x in later]):
        raise CorrelationError("incomplete matched audio runs in component pair")
    drifts={}
    for band in BANDS:
        idle=_per_mode_rate(earlier,"idle",band)-_per_mode_rate(later,"idle",band)
        switch=(_per_mode_rate(earlier,"switch",band)
                -_per_mode_rate(later,"switch",band))
        drifts[band]={
            "idle":idle,"switch":switch,"contrast":switch-idle
        }
    for measure in ("idle","switch","contrast"):
        if (drifts["ge40"][measure] !=
                drifts["between40and50"][measure]+drifts["ge50"][measure]):
            raise CorrelationError("exact rational band decomposition failure")
    return drifts


def _serialize_components(raw:dict)->dict:
    return {
        band:{
            "idle_earlier_minus_later_per_1000":round(float(raw[band]["idle"]),6),
            "switch_earlier_minus_later_per_1000":round(float(raw[band]["switch"]),6),
            "switch_drift_minus_idle_drift_per_1000":
                round(float(raw[band]["contrast"]),6),
            "numerically_positive_contrast":raw[band]["contrast"]>0,
            "numerically_negative_contrast":raw[band]["contrast"]<0,
            "exact_zero_contrast":raw[band]["contrast"]==0,
        }
        for band in BANDS
    }


def _matches_witness(value:Fraction,recorded:float)->bool:
    # Historical Stage284 subtraction used rounded binary floats.
    # Accept only the bounded difference of two six-decimal roundings.
    return type(recorded) in (float,int) and abs(float(value)-recorded) <= ROUNDED_TOLERANCE


def analyze_components(steady:dict,temporal:dict,sensitivity:dict,
                       contrasts:dict,boundary:dict,grid:dict,
                       draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid whole-pair resampling bound")
    expected=analyze_grid(steady,temporal,sensitivity,contrasts,boundary,draws)
    if not isinstance(grid,dict) or grid!=expected:
        raise CorrelationError("Stage284 grid not exactly reproducible")
    ids=expected["source_run_ids"]
    pairs=steady["steady_pair_verdict"]["pairs"]
    details=steady["per_run_windows"]
    if ([r["run_id"] for r in pairs]!=ids or
            [r["run_id"] for r in details]!=ids):
        raise CorrelationError("original source paired run IDs changed")
    records=[]
    for shift,prior in zip(OFFSETS,grid["grid"]):
        if prior["shift_seconds"]!=shift:
            raise CorrelationError("shift positions were reordered")
        early=[_bounded_pair_window(p,d,MIDDLE_START+shift)
               for p,d in zip(pairs,details)]
        late=[_bounded_pair_window(p,d,LATE_START+shift)
              for p,d in zip(pairs,details)]
        full_raw=_raw_components(early,late)
        full=_serialize_components(full_raw)
        omitted=[]
        for id in ids:
            a=[r for r in early if r["run_id"]!=id]
            b=[r for r in late if r["run_id"]!=id]
            raw=_raw_components(a,b)
            row={"excluded_source_run_id":id,"bands":_serialize_components(raw)}
            for band in ("ge40","ge50"):
                witness=next(r for r in prior["bands"][band]["leave_one_pair_out"]
                             if r["excluded_workflow_run_id"]==id)
                if not _matches_witness(raw[band]["contrast"],
                                        witness["switch_drift_minus_idle_drift_per_1000"]):
                    raise CorrelationError("independent omitted-pair contrast mismatch")
            omitted.append(row)
        for band in ("ge40","ge50"):
            witness=prior["bands"][band]["full_cohort_mode_drifts"]
            for mode,key in (
                ("idle","idle_earlier_minus_later_per_1000"),
                ("switch","switch_earlier_minus_later_per_1000"),
                ("contrast","switch_drift_minus_idle_drift_per_1000"),
            ):
                if not _matches_witness(full_raw[band][mode],witness[key]):
                    raise CorrelationError("original Stage284 per-mode drift disagrees")
        records.append({
            "shift_seconds":shift,
            "earlier_seconds":prior["earlier_guest_seconds"],
            "later_seconds":prior["later_guest_seconds"],
            "full_cohort_disjoint_bands":full,
            "excluded_pairs":omitted,
            "exact_ge40_equals_disjoint_sum":True,
        })
    summary={}
    for band in BANDS:
        values=[
            entry["bands"][band]["switch_drift_minus_idle_drift_per_1000"]
            for position in records for entry in position["excluded_pairs"]
        ]
        if len(values)!=len(OFFSETS)*len(ids):
            raise CorrelationError("incomplete full paired band partition matrix")
        summary[band]={
            "evaluated_shift_and_exclusion_cells":len(values),
            "positive_cells":sum(v>0 for v in values),
            "negative_cells":sum(v<0 for v in values),
            "zero_cells":sum(v==0 for v in values),
            "minimum_per_1000":min(values),
            "maximum_per_1000":max(values),
        }
        if band in ("ge40","ge50"):
            earlier=grid["matrix_summary"][band]
            if any(summary[band][a]!=earlier[b] for a,b in (
                ("positive_cells","positive_cells"),
                ("negative_cells","negative_cells"),
                ("zero_cells","exact_zero_cells"),
            )):
                raise CorrelationError("Stage284 pair grid signs do not reconcile")
    return {
        "schema":SCHEMA,
        "result":"DISJOINT_40_TO_50_AND_GE50_BANDS_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":expected["nro_sha256"],
        "pair_count":len(ids),
        "fixed_shifts_seconds":list(OFFSETS),
        "window_length_seconds":17,
        "boundary_rows":records,
        "matrix_summary":summary,
        "disjoint_classes":"40ms <= duration < 50ms; duration >= 50ms",
        "exact_fraction_conservation_before_rounding":True,
        "stage284_recomputed_from_archived_original_sd_evidence":True,
        "all_run_exclusions_apply_to_both_modes_and_windows":True,
        "overlapping_shift_windows_are_not_independent_trials":True,
        "fixed_switch_before_idle_order":True,
        "threshold_band_difference_is_not_causal":True,
        "audible_glitches_measured":False,
        "physical_switch_tested":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ("verified-steady-state","verified-temporal-thirds",
                  "verified-third-sensitivity","verified-temporal-contrasts",
                  "verified-boundary-shifts","verified-boundary-pair-grid","output"):
        parser.add_argument("--"+field,type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of prior disjoint band report")
        def read(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        r=analyze_components(
            read(args.verified_steady_state),
            read(args.verified_temporal_thirds),
            read(args.verified_third_sensitivity),
            read(args.verified_temporal_contrasts),
            read(args.verified_boundary_shifts),
            read(args.verified_boundary_pair_grid),
        )
        args.output.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":r["result"],"pairs":r["pair_count"],
            "band_40_to_50":r["matrix_summary"]["between40and50"],
            "band_ge50":r["matrix_summary"]["ge50"],
            "physical_switch_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"DISJOINT_BAND_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
