#!/usr/bin/env python3
"""Stage278: exploratory, pair-preserving variation of accepted NeXium audio controls.

Reads the output of compare_nexium_idle_switch_pairs.py, not arbitrary
raw event totals. Reports exact within-pair rate differences, leave-one-pair-
out range and reproducible whole-pair bootstrap sensitivity ranges. Because
the current experimental order always runs switching BEFORE idle, and
audio events within runs are dependent, the ranges are NOT confidence
intervals, a randomization test or evidence of music-switch causality.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError

SCHEMA="vh-nexium-audout-paired-variation/v1"
SOURCE_SCHEMA="vh-nexium-idle-switch-multi-pair/v1"
SEED=278
DRAWS=16384


def _positive_int(x:object,allow_zero:bool=False)->int:
    if type(x) is not int or (x<0 if allow_zero else x<=0):
        raise CorrelationError("invalid nonnegative guest audout counter")
    return x


def _rate(pairs:list[dict],mode:str,threshold:str)->float:
    count=sum(row[f"{mode}_{threshold}"] for row in pairs)
    attempts=sum(row[f"{mode}_attempts"] for row in pairs)
    if attempts<=0:
        raise CorrelationError("zero denominator in paired guest trace")
    return 1000.0*count/attempts


def _difference(pairs:list[dict],threshold:str)->float:
    return _rate(pairs,"switch",threshold)-_rate(pairs,"idle",threshold)


def _median(vals:list[float])->float:
    ordered=sorted(vals)
    n=len(ordered)
    if n%2:
        return ordered[n//2]
    return (ordered[n//2-1]+ordered[n//2])/2.0


def _xorshift32(state:int)->int:
    state ^= (state<<13)&0xffffffff
    state ^= state>>17
    state ^= (state<<5)&0xffffffff
    return state&0xffffffff


def _bootstrap(pairs:list[dict],band:str,draws:int=DRAWS)->dict:
    # Fixed 32-bit integer PRNG ensures byte-reproducible outputs across
    # CPython releases. Each draw selects COMPLETE correlated session
    # pairs; individual audout calls are NEVER treated as independent.
    state=SEED
    n=len(pairs)
    samples=[]
    for _ in range(draws):
        selected=[]
        for _ in range(n):
            state=_xorshift32(state)
            selected.append(pairs[state % n])
        samples.append(_difference(selected,band))
    samples.sort()
    lower=samples[int(.025*(draws-1))]
    upper=samples[int(.975*(draws-1))]
    if not all(math.isfinite(x) for x in (lower,upper)):
        raise CorrelationError("invalid paired sensitivity interval")
    return {
        "method":"fixed-seed whole-pair-resampling descriptive percentiles",
        "resamples":draws,
        "seed":SEED,
        "p025_switch_minus_idle_per_1000":round(lower,6),
        "p975_switch_minus_idle_per_1000":round(upper,6),
        "is_formal_confidence_interval":False,
        "is_randomization_test":False,
    }


def analyze(source:dict,draws:int=DRAWS)->dict:
    if (source.get("schema")!=SOURCE_SCHEMA
            or source.get("result")!="SAME_NRO_IDLE_SWITCH_ARCHIVED_PAIRS_REVERIFIED"
            or source.get("original_guest_sd_reopened_offline") is not False
            or source.get("randomized_or_causal_inference") is not False
            or source.get("audible_output_or_physical_switch_tested") is not False
            or source.get("original_sd_audit_witness")!="PRIOR_SUCCEEDED_LIVE_NEXIUM_WORKFLOW"):
        raise CorrelationError("not accepted same-NRO pair evidence")
    pairs=source.get("pairs")
    if not isinstance(pairs,list) or not 2<=len(pairs)<=12:
        raise CorrelationError("expected two to twelve complete NeXium pairs")
    nro=source.get("nro_sha256")
    if (type(nro) is not str or len(nro)!=64 or
            any(x not in "0123456789abcdef" for x in nro)):
        raise CorrelationError("invalid NRO digest")
    ids=[]
    for p in pairs:
        if not isinstance(p,dict) or p.get("nro_sha256")!=nro:
            raise CorrelationError("NRO mismatch within accepted paired evidence")
        run_id=_positive_int(p.get("run_id"))
        ids.append(run_id)
        if (p.get("idle_original_sd_audited_in_prior_workflow") is not True
                or p.get("switch_original_sd_audited_in_prior_workflow") is not True
                or p.get("all_copied_guest_bytes_reverified") is not True):
            raise CorrelationError("paired guest original SD was not verified")
        for mode in ("idle","switch"):
            total=_positive_int(p.get(f"{mode}_attempts"))
            over40=_positive_int(p.get(f"{mode}_ge40"),True)
            over50=_positive_int(p.get(f"{mode}_ge50"),True)
            if not 0<=over50<=over40<=total:
                raise CorrelationError("slow-call counter conservation broken")
            if _positive_int(p.get(f"{mode}_seconds"))<50:
                raise CorrelationError("too few full guest audio seconds")
    if (ids!=sorted(set(ids))
            or source.get("independent_workflow_run_ids")!=ids):
        raise CorrelationError("duplicate, unordered or unaudited run identifiers")
    totals=source.get("totals")
    rates=source.get("rates")
    if not isinstance(totals,dict) or not isinstance(rates,dict):
        raise CorrelationError("missing independent Stage277 totals/rates")
    for mode in ("idle","switch"):
        for field in ("attempts","ge40","ge50"):
            key=f"{mode}_{field}"
            value=sum(p[key] for p in pairs)
            if totals.get(key)!=value:
                raise CorrelationError("Stage277 source total does not match per-run records")
        for band in ("ge40","ge50"):
            key=f"{mode}_{band}_per_1000_attempts"
            if rates.get(key)!=round(_rate(pairs,mode,band),3):
                raise CorrelationError("Stage277 normalized rate is inconsistent")
    if not type(draws) is int or not 1<=draws<=65536:
        raise CorrelationError("invalid bounded bootstrap iteration count")

    bands={}
    for band in ("ge40","ge50"):
        differences=[
            1000*p[f"switch_{band}"]/p["switch_attempts"]
            -1000*p[f"idle_{band}"]/p["idle_attempts"] for p in pairs
        ]
        loo=[_difference([other for other in pairs if other["run_id"]!=p["run_id"]],band)
             for p in pairs]
        above=sum(delta>0 for delta in differences)
        below=sum(delta<0 for delta in differences)
        ties=len(pairs)-above-below
        if (source.get("paired_rate_directions",{}).get(band)!={
                "switch_rate_higher":above,"idle_rate_higher":below,"exact_ties":ties}):
            raise CorrelationError("Stage277 pair directions disagree")
        bands[band]={
            "idle_per_1000":round(_rate(pairs,"idle",band),6),
            "switch_per_1000":round(_rate(pairs,"switch",band),6),
            "aggregate_switch_minus_idle_per_1000":round(_difference(pairs,band),6),
            "individual_pair_differences_per_1000":[round(x,6) for x in differences],
            "median_pair_difference_per_1000":round(_median(differences),6),
            "leave_one_pair_out_difference_min_per_1000":round(min(loo),6),
            "leave_one_pair_out_difference_max_per_1000":round(max(loo),6),
            "positive_pairs":above,"negative_pairs":below,"zero_difference_pairs":ties,
            "paired_resampling_sensitivity":_bootstrap(pairs,band,draws),
        }
    return {
        "schema":SCHEMA,
        "result":"EXPLORATORY_PAIRED_NEXIUM_VARIABILITY_COMPUTED",
        "nro_sha256":nro,
        "workflow_run_ids":ids,
        "pair_count":len(pairs),
        "bands":bands,
        "all_switching_sessions_preceded_idle":True,
        "switching_order_randomized":False,
        "within_session_audio_calls_independent":False,
        "bootstrap_is_inferential_confidence_interval":False,
        "statistical_causal_music_claim":False,
        "physical_switch_or_audible_underrun_measurement":False,
        "original_live_guest_sd_accessible_offline":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-pairs",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of prior pair-variation report")
        report=analyze(json.loads(args.verified_pairs.read_text("utf-8")))
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "pairs":report["pair_count"],
            "ge40_difference_per_1000":report["bands"]["ge40"]["aggregate_switch_minus_idle_per_1000"],
            "ge50_difference_per_1000":report["bands"]["ge50"]["aggregate_switch_minus_idle_per_1000"],
            "physical_hardware_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError,json.JSONDecodeError) as exc:
        print(json.dumps({"result":"NEXIUM_PAIRED_VARIABILITY_UNVERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
