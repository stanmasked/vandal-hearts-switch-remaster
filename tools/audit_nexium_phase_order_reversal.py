#!/usr/bin/env python3
"""Stage296: source-checked 0,8 | 8,0 queue query order-reversal audit.

The two distinct NROs are executed as four SEQUENTIAL NeXium
capture sessions. These are genuine phase queries from each guest SD,
but the fixed sequence is not randomized; neither order effects
nor any DAC, physical console or audio quality is established.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from compare_nexium_real_queue_phases import (
    compare_real_phases,inspect_observations
)

SCHEMA="vh-nexium-real-two-phase-reversed-order-four-sessions/v1"
ORDER=("phase0_first","phase8_first","phase8_reversed","phase0_reversed")
EXPECTED_PHASES=(0,8,8,0)


def _rate(row:dict,key:str)->Fraction:
    return Fraction(1000*row[key],row["service_query_count"])


def _rounded(rate:Fraction)->float:
    return round(float(rate),6)


def audit_four_sessions(
    phase0_first:dict,phase8_first:dict,
    phase8_reversed:dict,phase0_reversed:dict,
    baseline_manifest:dict,phase8_manifest:dict
)->dict:
    forward=compare_real_phases(
        phase0_first,phase8_first,baseline_manifest,phase8_manifest)
    reverse=compare_real_phases(
        phase0_reversed,phase8_reversed,baseline_manifest,phase8_manifest)
    # compare_real_phases has performed independent sample/accounting/
    # NRO manifest validation for both ordered pairs.
    if (forward["nro_sha256"] if "nro_sha256" in forward else
            forward.get("baseline_nro_sha256")) != reverse.get("baseline_nro_sha256"):
        raise CorrelationError("reversed runs are not the same baseline NRO")
    if (forward.get("phase8_nro_sha256")!=reverse.get("phase8_nro_sha256")
            or forward.get("run_id")!=reverse.get("run_id")
            or forward.get("run_attempt")!=reverse.get("run_attempt")
            or forward.get("git_sha")!=reverse.get("git_sha")):
        raise CorrelationError("reversal must use same run's experimental NRO")
    rows=[
        inspect_observations(record,phase)
        for record,phase in zip(
            (phase0_first,phase8_first,phase8_reversed,phase0_reversed),
            EXPECTED_PHASES)
    ]
    hashes=[x["original_guest_probe_sha256"] for x in rows]
    if len(set(hashes))!=4:
        raise CorrelationError("repeated or relabeled original guest SD across four runs")
    # Even two runs from the same NRO are separate sessions. Cross-run
    # timestamp continuity is not asserted, and no host time is imputed.
    full=[]
    for label,phase,row in zip(ORDER,EXPECTED_PHASES,rows):
        full.append({
            "label":label,
            "phase":phase,
            **row,
        })
    def contrast(first:dict,second:dict)->dict:
        keys=(
            "slow_ge40_on_queried_attempts",
            "slow_ge50_on_queried_attempts",
            "successful_service_queries_with_nonzero_queue",
        )
        results={}
        for key in keys:
            # A per-1000-sampled-attempt contrast of two independent
            # sequential sessions, not causal or paired-in-time.
            results[key+"_delta_per_1000_queried_attempts"]=_rounded(
                _rate(first,key)-_rate(second,key))
        return results
    forward_delta=contrast(rows[0],rows[1])
    reverse_delta=contrast(rows[3],rows[2])
    order_gap={}
    for key in forward_delta:
        order_gap[key+"_forward_minus_reverse"]=_rounded(
            Fraction.from_float(forward_delta[key])-
            Fraction.from_float(reverse_delta[key]))
    zero_count=sum(r["successful_service_queries_with_zero_queue"]
                   for r in rows)
    nonzero_count=sum(r["successful_service_queries_with_nonzero_queue"]
                      for r in rows)
    success_count=sum(r["service_query_success"] for r in rows)
    if zero_count+nonzero_count!=success_count:
        raise CorrelationError("four actual guest service queue histograms disagree")
    return {
        "schema":SCHEMA,
        "result":"FOUR_ORIGINAL_GUEST_SD_PHASE0_PHASE8_REVERSED_ORDER_VERIFIED",
        "nro_sha256_by_phase":{
            "phase0":forward["baseline_nro_sha256"],
            "phase8":forward["phase8_nro_sha256"],
        },
        "git_sha":forward["git_sha"],
        "run_id":forward["run_id"],
        "run_attempt":forward["run_attempt"],
        "capture_sequence":list(ORDER),
        "session_records":full,
        "total_queried_attempts":sum(r["service_query_count"] for r in rows),
        "total_successful_service_queries":success_count,
        "total_zero_queue_service_queries":zero_count,
        "total_nonzero_queue_service_queries":nonzero_count,
        "forward_phase0_minus_phase8":forward_delta,
        "reversed_phase0_minus_phase8":reverse_delta,
        "forward_minus_reverse_contrast":order_gap,
        "all_four_guest_SD_probe_sha256_distinct":True,
        "all_four_guest_SD_sources_originally_audited":True,
        "capture_order_not_randomized":True,
        "different_guest_clocks_not_aligned":True,
        "host_load_may_change_between_runs":True,
        "no_unqueried_queue_values_imputed":True,
        "causal_effect_of_phase_or_order_proven":False,
        "physical_switch_audio_or_DAC_underrun_measured":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("phase0-first","phase8-first","phase8-reversed",
                "phase0-reversed","phase0-manifest","phase8-manifest",
                "output"):
        p.add_argument("--"+arg,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("will not overwrite an audited order experiment")
        def read(path:Path)->dict:
            if path.is_symlink() or not path.is_file():
                raise CorrelationError("missing or aliased original run audit")
            return json.loads(path.read_text(encoding="utf-8"))
        output=audit_four_sessions(
            read(a.phase0_first),read(a.phase8_first),
            read(a.phase8_reversed),read(a.phase0_reversed),
            read(a.phase0_manifest),read(a.phase8_manifest))
        a.output.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":output["result"],
            "order":output["capture_sequence"],
            "samples":{r["label"]:r["service_query_count"] for r in
                       output["session_records"]},
            "ge40_forward":output["forward_phase0_minus_phase8"][
                "slow_ge40_on_queried_attempts_delta_per_1000_queried_attempts"],
            "ge40_reversed":output["reversed_phase0_minus_phase8"][
                "slow_ge40_on_queried_attempts_delta_per_1000_queried_attempts"],
            "causality_proven":False,
        },sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"FOUR_REAL_PHASE_ORDER_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
