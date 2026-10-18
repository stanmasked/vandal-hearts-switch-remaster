#!/usr/bin/env python3
"""Stage283: fixed one-sided boundary shifts for paired 17-second NeXium audio.

Compare adjacent equal 17-second windows at shifts -4,-3,-2,-1,0
relative to Stage282's middle (18..34) / late (35..51) comparison.
Positive shifts require nonexistent seconds beyond 51 and are forbidden.

All values are software audoutPlayBuffer call durations. This is
post-hoc descriptive window sensitivity, not audible output or causality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from analyze_nexium_steady_temporal_contrasts import (
    analyze_contrasts, _paired_contrast
)
from analyze_nexium_steady_segments import BEGIN_SECOND, END_SECOND, MODES, METRICS
from audit_nexium_audout_scene_correlation import CorrelationError
from compare_nexium_idle_switch_pairs import summarize

SCHEMA="vh-nexium-audout-fixed-boundary-shifts/v1"
OFFSETS=(-4,-3,-2,-1,0)
MIDDLE_START=18
LATE_START=35
LENGTH=17
BANDS=("ge40","ge50")


def _bounded_pair_window(pair:dict, detail:dict, start:int)->dict:
    """Compute a single pair's actual counts without averaged denominators."""
    if start<BEGIN_SECOND or start+LENGTH-1>END_SECOND:
        raise CorrelationError("requested window exceeds common 51 seconds")
    result=pair.copy()
    if detail.get("run_id")!=pair.get("run_id"):
        raise CorrelationError("mismatched original-SD-bound run ID")
    for mode in MODES:
        record=detail.get(mode)
        if not isinstance(record,dict):
            raise CorrelationError("missing already audited mode windows")
        rows=record.get("per_second")
        if not isinstance(rows,list) or len(rows)!=51:
            raise CorrelationError("incomplete per-second source")
        chosen=rows[start-BEGIN_SECOND:start-BEGIN_SECOND+LENGTH]
        if (len(chosen)!=LENGTH or
                [r.get("second") for r in chosen] !=
                list(range(start,start+LENGTH))):
            raise CorrelationError("nonconsecutive or missing source second")
        for field in METRICS:
            values=[r.get(field) for r in chosen]
            if any(type(value) is not int or value<0 for value in values):
                raise CorrelationError("noncanonical boundary-window counter")
            result[f"{mode}_{field}"]=sum(values)
        if (result[f"{mode}_attempts"]<=0 or
                not 0<=result[f"{mode}_ge50"]<=
                    result[f"{mode}_ge40"]<=result[f"{mode}_attempts"]):
            raise CorrelationError("inconsistent boundary-window count bands")
        result[f"{mode}_seconds"]=LENGTH
    return result


def analyze_boundary_shifts(steady:dict, temporal:dict,
                            sensitivity:dict, contrasts:dict,
                            draws:int=16384)->dict:
    # Recalculate all Stage279..282 identity, seconds and count witnesses.
    checked=analyze_contrasts(steady,temporal,sensitivity,draws=draws)
    if not isinstance(contrasts,dict) or contrasts!=checked:
        raise CorrelationError("unreproducible Stage282 contrast upstream")
    whole=steady["steady_pair_verdict"]
    pairs=whole["pairs"]
    details=steady["per_run_windows"]
    ids=checked["source_run_ids"]
    if (len(pairs)!=len(details) or
            [p["run_id"] for p in pairs]!=ids or
            [d["run_id"] for d in details]!=ids):
        raise CorrelationError("Stage283 pairs and source seconds differ")
    windows=[]
    for shift in OFFSETS:
        early_start=MIDDLE_START+shift
        late_start=LATE_START+shift
        if (early_start<BEGIN_SECOND or
                early_start+LENGTH!=late_start or
                late_start+LENGTH-1>END_SECOND):
            raise CorrelationError("illegal temporal window shift")
        early=[_bounded_pair_window(p,d,early_start)
               for p,d in zip(pairs,details)]
        late=[_bounded_pair_window(p,d,late_start)
              for p,d in zip(pairs,details)]
        # Independent check of denominators and slow bands for each
        # mode. No interpolation and no pooled averaging of per-pair rates.
        first=summarize(early)
        second=summarize(late)
        bands={}
        for band in BANDS:
            per_pair=[
                _paired_contrast([a],[b],band)
                for a,b in zip(early,late)
            ]
            loo=[
                _paired_contrast(
                    [p for p in early if p["run_id"]!=id],
                    [p for p in late if p["run_id"]!=id],
                    band,
                ) for id in ids
            ]
            aggregate=_paired_contrast(early,late,band)
            bands[band]={
                "difference_of_pooled_rate_differences_per_1000":
                    round(aggregate,6),
                "within_pair_contrasts_per_1000":
                    [round(value,6) for value in per_pair],
                "positive_pairs":sum(x>0 for x in per_pair),
                "negative_pairs":sum(x<0 for x in per_pair),
                "exact_ties":sum(x==0 for x in per_pair),
                "leave_one_pair_out_min_per_1000":round(min(loo),6),
                "leave_one_pair_out_max_per_1000":round(max(loo),6),
            }
        windows.append({
            "shift_seconds":shift,
            "earlier_seconds":[early_start,early_start+LENGTH-1],
            "later_seconds":[late_start,late_start+LENGTH-1],
            "source_workflow_run_ids":ids,
            "earlier_mode_totals":first["totals"],
            "later_mode_totals":second["totals"],
            "bands":bands,
        })
    reference=checked["contrasts"][1]["bands"]
    for band in BANDS:
        if (windows[-1]["bands"][band][
                "difference_of_pooled_rate_differences_per_1000"]
                !=reference[band]["aggregate_earlier_minus_later_per_1000"]
                or windows[-1]["bands"][band][
                    "within_pair_contrasts_per_1000"]
                !=reference[band]["per_pair_earlier_minus_later_per_1000"]
                or windows[-1]["bands"][band]["positive_pairs"]
                !=reference[band]["positive_pairs"]):
            raise CorrelationError("unshifted Stage283 disagrees with Stage282")
    ranges={}
    for band in BANDS:
        changes=[record["bands"][band][
            "difference_of_pooled_rate_differences_per_1000"]
                 for record in windows]
        ranges[band]={
            "min_aggregate_contrast_per_1000":min(changes),
            "max_aggregate_contrast_per_1000":max(changes),
            "shifts_with_positive_aggregate":sum(x>0 for x in changes),
            "shifts_with_negative_aggregate":sum(x<0 for x in changes),
            "shifts_with_exact_zero_aggregate":sum(x==0 for x in changes),
        }
    return {
        "schema":SCHEMA,
        "result":"FIVE_PRESPECIFIED_NEARBY_BOUNDARIES_RECONCILED",
        "source_run_ids":ids,
        "nro_sha256":checked["nro_sha256"],
        "pair_count":len(ids),
        "offsets_seconds":list(OFFSETS),
        "window_length_seconds":LENGTH,
        "candidate_boundaries":windows,
        "contrast_ranges":ranges,
        "upstream_stage282_recomputed_exactly":True,
        "unshifted_contrast_matches_stage282":True,
        "all_windows_use_matched_relative_audio_seconds":True,
        "overlapping_shifted_windows_are_not_independent":True,
        "only_left_shifts_possible_at_common_51s_end":True,
        "fixed_switch_then_idle_order":True,
        "randomized_or_causal_conclusion":False,
        "physical_switch_tested":False,
        "audible_underruns_or_DAC_clock_measured":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-steady-state",type=Path,required=True)
    parser.add_argument("--verified-temporal-thirds",type=Path,required=True)
    parser.add_argument("--verified-third-sensitivity",type=Path,required=True)
    parser.add_argument("--verified-temporal-contrasts",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse replacement of previous boundary audit")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        result=analyze_boundary_shifts(
            load(args.verified_steady_state),
            load(args.verified_temporal_thirds),
            load(args.verified_third_sensitivity),
            load(args.verified_temporal_contrasts),
        )
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "pairs":result["pair_count"],
            "middle_vs_late_ge40_by_shift":[
                [w["shift_seconds"],w["bands"]["ge40"][
                    "difference_of_pooled_rate_differences_per_1000"]]
                for w in result["candidate_boundaries"]],
            "is_causal":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"SHIFTED_BOUNDARY_NOT_VERIFIED",
            "error":str(exc),
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
