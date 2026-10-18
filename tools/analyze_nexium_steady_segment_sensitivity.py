#!/usr/bin/env python3
"""Stage281: pair-preserving descriptive sensitivity for Stage280's three thirds.

The two upstream reports must be regenerated together from the same
already original-SD-audited archive copies. Recompute the entire Stage280
report from Stage279 and demand an exact match before analyzing intervals.
This is software audout latency, NOT randomized, audible or hardware data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_segments import analyze_temporal_thirds
from analyze_nexium_idle_switch_variability import (
    DRAWS, _bootstrap, _difference, _median
)

SCHEMA="vh-nexium-temporal-third-paired-sensitivity/v1"


def analyze_sensitivity(verified_steady:dict,observed_segments:dict,
                        draws:int=DRAWS)->dict:
    if type(draws) is not int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded pair-resampling count")
    expected=analyze_temporal_thirds(verified_steady)
    # Reject a fabricated, truncated, reordered, or stale Stage280 report.
    # The origin integrity of verified_steady itself still relies on the
    # independent archived-source/live-SD audit in the same workflow.
    if (not isinstance(observed_segments,dict) or
            observed_segments!=expected):
        raise CorrelationError("Stage280 report differs from independently rederived source")
    thirds=[]
    for segment in expected["segments"]:
        pairs=segment["per_run_pairs"]
        if (len(pairs)!=expected["pair_count"] or
                [p["run_id"] for p in pairs]!=expected["source_run_ids"]):
            raise CorrelationError("temporal third lost paired workflow identity")
        bands={}
        for threshold in ("ge40","ge50"):
            deltas=[
                1000*p["switch_"+threshold]/p["switch_attempts"]
                -1000*p["idle_"+threshold]/p["idle_attempts"]
                for p in pairs
            ]
            loo=[
                _difference([q for q in pairs if q["run_id"]!=p["run_id"]],
                            threshold)
                for p in pairs
            ]
            signs={
                "switch_higher":sum(d>0 for d in deltas),
                "idle_higher":sum(d<0 for d in deltas),
                "exact_ties":sum(d==0 for d in deltas),
            }
            reported=segment["paired_rate_directions"][threshold]
            if (signs["switch_higher"]!=reported["switch_rate_higher"]
                    or signs["idle_higher"]!=reported["idle_rate_higher"]
                    or signs["exact_ties"]!=reported["exact_ties"]):
                raise CorrelationError("temporal per-pair slow-rate signs disagree")
            difference=_difference(pairs,threshold)
            if (round(difference,6)!=
                    segment["switch_minus_idle_per_1000"][threshold]):
                raise CorrelationError("temporal paired rate disagrees with observed aggregate")
            bands[threshold]={
                "aggregate_switch_minus_idle_per_1000":round(difference,6),
                "individual_pair_differences_per_1000":[round(d,6) for d in deltas],
                "median_pair_difference_per_1000":round(_median(deltas),6),
                "leave_one_pair_out_min_per_1000":round(min(loo),6),
                "leave_one_pair_out_max_per_1000":round(max(loo),6),
                "positive_pairs":signs["switch_higher"],
                "negative_pairs":signs["idle_higher"],
                "exact_ties":signs["exact_ties"],
                "whole_pair_resampling":_bootstrap(pairs,threshold,draws),
            }
        thirds.append({
            "first_guest_second":segment["first_guest_second"],
            "last_guest_second":segment["last_guest_second"],
            "seconds_per_mode":17,
            "bands":bands,
        })
    all_totals=expected["complete_51s_totals"]
    whole_differences={
        threshold:round(
            1000*all_totals["switch_"+threshold]/all_totals["switch_attempts"]
            -1000*all_totals["idle_"+threshold]/all_totals["idle_attempts"],6)
        for threshold in ("ge40","ge50")
    }
    return {
        "schema":SCHEMA,
        "result":"THREE_VERIFIED_TEMPORAL_THIRDS_PAIRED_SENSITIVITY",
        "source_steady_result":verified_steady["result"],
        "source_temporal_result":expected["result"],
        "source_run_ids":expected["source_run_ids"],
        "nro_sha256":expected["nro_sha256"],
        "pair_count":expected["pair_count"],
        "thirds":thirds,
        "whole_51s_switch_minus_idle_per_1000":whole_differences,
        "same_original_source_pairs_preserved":True,
        "source_stage280_report_exactly_rederived":True,
        "fixed_order_switch_before_idle":True,
        "bootstrap_intervals_are_descriptive_only":True,
        "is_formal_confidence_interval":False,
        "is_randomization_test":False,
        "music_switch_causality_established":False,
        "guest_to_dac_clock_alignment_verified":False,
        "audible_output_or_underruns_measured":False,
        "physical_switch_tested":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-steady-state",type=Path,required=True)
    parser.add_argument("--verified-temporal-thirds",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse replacement of prior sensitivity report")
        steady=json.loads(args.verified_steady_state.read_text(encoding="utf-8"))
        thirds=json.loads(args.verified_temporal_thirds.read_text(encoding="utf-8"))
        report=analyze_sensitivity(steady,thirds)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "pairs":report["pair_count"],
            "ge40_leave_one_out":[[
                t["bands"]["ge40"]["leave_one_pair_out_min_per_1000"],
                t["bands"]["ge40"]["leave_one_pair_out_max_per_1000"]]
                for t in report["thirds"]],
            "causality_established":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"TEMPORAL_PAIRED_SENSITIVITY_NOT_VERIFIED",
            "error":str(exc),
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
