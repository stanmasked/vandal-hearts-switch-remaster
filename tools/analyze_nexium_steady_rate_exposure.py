#!/usr/bin/env python3
"""Stage286: exact numerator vs denominator contribution in NeXium slow-call rates.

For each audited 17-second pair of windows, decompose early-minus-late
slow calls per 1,000 audout attempts into symmetric count and exposure
(denominator) terms, using exact Fraction arithmetic. Repeat for all
five Stage283 boundaries and all source-pair omissions, retaining
40..<50ms and >=50ms as disjoint classes. The decompositions are
descriptive mathematical identities, not causal effect attributions.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_idle_switch_variability import DRAWS
from analyze_nexium_steady_boundary_shifts import (
    OFFSETS, MIDDLE_START, LATE_START, _bounded_pair_window
)
from analyze_nexium_steady_disjoint_bands import (
    analyze_components, _raw_components, _count, BANDS, MODES
)

SCHEMA="vh-nexium-symmetric-rate-exposure-decomposition/v1"
TERMS=("count_effect","denominator_effect","rate_drift")


def _mode_effects(earlier:list[dict],later:list[dict],
                  mode:str,band:str)->dict:
    if (mode not in MODES or band not in BANDS
            or not earlier or len(earlier)!=len(later)
            or [p["run_id"] for p in earlier]!=
               [p["run_id"] for p in later]):
        raise CorrelationError("unmatched modes, bands or original source run IDs")
    ce=sum(_count(r,mode,band) for r in earlier)
    cl=sum(_count(r,mode,band) for r in later)
    ae=sum(r[f"{mode}_attempts"] for r in earlier)
    al=sum(r[f"{mode}_attempts"] for r in later)
    if ae<=0 or al<=0:
        raise CorrelationError("zero source audout attempt denominator")

    # Exact midpoint/symmetric decomposition, no preferred reference
    # denominator and no ambiguous subtraction of rounded rates.
    count=Fraction(500*(ce-cl)*(ae+al),ae*al)
    denominator=Fraction(500*(ce+cl)*(al-ae),ae*al)
    drift=Fraction(1000*ce,ae)-Fraction(1000*cl,al)
    if count+denominator!=drift:
        raise CorrelationError("symmetric rate decomposition does not conserve")
    return {
        "count_effect":count,
        "denominator_effect":denominator,
        "rate_drift":drift,
        "earlier_slow_calls":ce,
        "later_slow_calls":cl,
        "earlier_attempts":ae,
        "later_attempts":al,
    }


def _full_effects(early:list[dict],late:list[dict])->dict:
    raw=_raw_components(early,late)
    calculated={}
    for band in BANDS:
        idle=_mode_effects(early,late,"idle",band)
        switching=_mode_effects(early,late,"switch",band)
        contrast={term:switching[term]-idle[term] for term in TERMS}
        if (contrast["count_effect"]+contrast["denominator_effect"]
                !=contrast["rate_drift"]
                or contrast["rate_drift"]!=raw[band]["contrast"]
                or idle["rate_drift"]!=raw[band]["idle"]
                or switching["rate_drift"]!=raw[band]["switch"]):
            raise CorrelationError("source duration band drift failed conservation")
        calculated[band]={"idle":idle,"switch":switching,"contrast":contrast}
    # Splitting ge40 into 40..<50 and >=50 must preserve both
    # components and the total rate drift for BOTH modes and contrast.
    for mode in (*MODES,"contrast"):
        for term in TERMS:
            if (calculated["ge40"][mode][term] !=
                    calculated["between40and50"][mode][term]+
                    calculated["ge50"][mode][term]):
                raise CorrelationError("disjoint band decomposition lost a component")
    return calculated


def _serialise(raw:dict)->dict:
    return {
        band:{
            mode:{
                **{k:round(float(value),6) for k,value in record.items()
                   if k in TERMS},
                **{k:value for k,value in record.items() if k not in TERMS},
            }
            for mode,record in modes.items()
        }
        for band,modes in raw.items()
    }


def _same_stage285(raw:dict,previous:dict)->bool:
    if set(previous)!=set(BANDS):
        return False
    for band in BANDS:
        for mode,witness_field in (
            ("idle","idle_earlier_minus_later_per_1000"),
            ("switch","switch_earlier_minus_later_per_1000"),
            ("contrast","switch_drift_minus_idle_drift_per_1000"),
        ):
            if (round(float(raw[band][mode]["rate_drift"]),6)
                    !=previous[band][witness_field]):
                return False
    return True


def analyze_exposure(steady:dict,temporal:dict,sensitivity:dict,
                     contrasts:dict,boundary:dict,grid:dict,
                     disjoint:dict,draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded audit draw count")
    expected=analyze_components(
        steady,temporal,sensitivity,contrasts,boundary,grid,draws)
    if not isinstance(disjoint,dict) or disjoint!=expected:
        raise CorrelationError("Stage285 original-SD band witness cannot be reproduced")
    ids=expected["source_run_ids"]
    paired=steady["steady_pair_verdict"]["pairs"]
    details=steady["per_run_windows"]
    if ([p["run_id"] for p in paired]!=ids or
            [p["run_id"] for p in details]!=ids):
        raise CorrelationError("source run order changed in exposure analysis")

    windows=[]
    for shift,prior in zip(OFFSETS,expected["boundary_rows"]):
        if prior["shift_seconds"]!=shift:
            raise CorrelationError("boundary shift witness is out of order")
        early=[_bounded_pair_window(p,d,MIDDLE_START+shift)
               for p,d in zip(paired,details)]
        late=[_bounded_pair_window(p,d,LATE_START+shift)
              for p,d in zip(paired,details)]
        full_raw=_full_effects(early,late)
        if not _same_stage285(full_raw,prior["full_cohort_disjoint_bands"]):
            raise CorrelationError("full-cohort fractions disagree with Stage285")
        deletions=[]
        for i,run_id in enumerate(ids):
            previous=prior["excluded_pairs"][i]
            if previous["excluded_source_run_id"]!=run_id:
                raise CorrelationError("different deleted source pair identity")
            a=[p for p in early if p["run_id"]!=run_id]
            b=[p for p in late if p["run_id"]!=run_id]
            raw=_full_effects(a,b)
            if not _same_stage285(raw,previous["bands"]):
                raise CorrelationError("deleted-cohort fractions disagree with Stage285")
            deletions.append({
                "excluded_source_run_id":run_id,
                "bands":_serialise(raw),
            })
        windows.append({
            "shift_seconds":shift,
            "earlier_guest_seconds":prior["earlier_seconds"],
            "later_guest_seconds":prior["later_seconds"],
            "full_cohort":_serialise(full_raw),
            "leave_one_pair_out":deletions,
            "exact_count_plus_denominator_equals_rate":True,
            "exact_disjoint_band_conservation":True,
        })

    summary={}
    for band in BANDS:
        values=[
            deletion["bands"][band]["contrast"]
            for row in windows for deletion in row["leave_one_pair_out"]
        ]
        if len(values)!=len(OFFSETS)*len(ids):
            raise CorrelationError("incomplete rate exposure pair deletion matrix")
        count=[p["count_effect"] for p in values]
        den=[p["denominator_effect"] for p in values]
        actual=[p["rate_drift"] for p in values]
        reported=expected["matrix_summary"][band]
        sign=(sum(v>0 for v in actual),sum(v<0 for v in actual),
              sum(v==0 for v in actual))
        if sign!=(reported["positive_cells"],reported["negative_cells"],
                 reported["zero_cells"]):
            raise CorrelationError("Stage285 disjoint band signs not reproduced")
        summary[band]={
            "total_shift_and_excluded_pair_cells":len(actual),
            "rate_positive_cells":sign[0],
            "rate_negative_cells":sign[1],
            "rate_zero_cells":sign[2],
            "count_effect_positive_cells":sum(v>0 for v in count),
            "count_effect_negative_cells":sum(v<0 for v in count),
            "count_effect_zero_cells":sum(v==0 for v in count),
            "denominator_effect_positive_cells":sum(v>0 for v in den),
            "denominator_effect_negative_cells":sum(v<0 for v in den),
            "denominator_effect_zero_cells":sum(v==0 for v in den),
            "count_effect_min_per_1000":min(count),
            "count_effect_max_per_1000":max(count),
            "denominator_effect_min_per_1000":min(den),
            "denominator_effect_max_per_1000":max(den),
        }
    return {
        "schema":SCHEMA,
        "result":"EXACT_SYMMETRIC_AUDOUT_RATE_EXPOSURE_COMPONENTS_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":expected["nro_sha256"],
        "pair_count":len(ids),
        "shifts_seconds":list(OFFSETS),
        "window_length_seconds":17,
        "windows":windows,
        "matrix_summary":summary,
        "upstream_stage285_exactly_recomputed":True,
        "exact_fraction_identity_before_rounding":True,
        "same_pair_removed_from_both_windows_and_modes":True,
        "no_denominator_interpolation_or_fabricated_calls":True,
        "overlapping_windows_and_deleted_cohorts_are_not_independent":True,
        "all_music_switching_sessions_preceded_idle":True,
        "count_vs_exposure_is_mathematical_not_causal_attribution":True,
        "randomized_significance_test":False,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
    }


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__)
    for field in (
        "verified-steady-state","verified-temporal-thirds",
        "verified-third-sensitivity","verified-temporal-contrasts",
        "verified-boundary-shifts","verified-boundary-pair-grid",
        "verified-disjoint-bands","output"
    ):
        ap.add_argument("--"+field,type=Path,required=True)
    args=ap.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of previous decomposition")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        report=analyze_exposure(
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
            load(args.verified_temporal_contrasts),
            load(args.verified_boundary_shifts),
            load(args.verified_boundary_pair_grid),
            load(args.verified_disjoint_bands),
        )
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "pairs":report["pair_count"],
            "symmetric_exposure_summary":report["matrix_summary"],
            "is_causal":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"AUDOUT_EXPOSURE_DECOMPOSITION_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
