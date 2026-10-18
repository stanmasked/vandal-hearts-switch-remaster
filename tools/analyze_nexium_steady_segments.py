#!/usr/bin/env python3
"""Stage280: descriptive temporal thirds of Stage279's validated guest seconds.

Three fixed 17-second intervals partition guest-audio seconds 1..51.
Input MUST be the freshly reaudited Stage279 report, generated from the
original-SD-bound source archives in the same CI job. Reading an arbitrary
JSON report alone cannot independently authenticate its origin.
These are blocking audout API calls, NOT audible/hardware measurements.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from audit_nexium_audout_scene_correlation import CorrelationError
from analyze_nexium_steady_state import (
    SCHEMA as SOURCE_SCHEMA, BEGIN_SECOND, END_SECOND, WINDOW_COUNT
)
from compare_nexium_idle_switch_pairs import summarize

SCHEMA="vh-nexium-audout-temporal-thirds/v1"
SEGMENTS=((1,17),(18,34),(35,51))
METRICS=("attempts","ge40","ge50")
MODES=("idle","switch")


def _row(row: object, second: int) -> dict:
    if (not isinstance(row,dict) or
            set(row)!=set(("second",*METRICS)) or
            type(row.get("second")) is not int or row["second"]!=second):
        raise CorrelationError("missing, duplicate or out-of-order guest second")
    if any(type(row.get(key)) is not int or row[key]<0 for key in METRICS):
        raise CorrelationError("noncanonical per-second audout counts")
    if (row["attempts"]<=0 or
            not 0<=row["ge50"]<=row["ge40"]<=row["attempts"]):
        raise CorrelationError("impossible per-second slow-call bands")
    return row


def analyze_temporal_thirds(source: dict) -> dict:
    if (not isinstance(source,dict)
            or source.get("schema")!=SOURCE_SCHEMA
            or source.get("result")!="ORIGINAL_SD_BOUND_COMMON_51S_AUDOUT_REVERIFIED"
            or source.get("startup_second_excluded") is not True
            or source.get("matched_second_count_per_mode")!=WINDOW_COUNT
            or source.get("first_included_second")!=BEGIN_SECOND
            or source.get("last_included_second")!=END_SECOND
            or source.get("previous_original_sd_auditor_results_required") is not True
            or source.get("guest_original_sd_reopened_in_offline_report") is not False
            or source.get("music_switch_causality_established") is not False
            or source.get("speaker_audio_output_measured") is not False
            or source.get("physical_switch_tested") is not False):
        raise CorrelationError("unverified or overclaimed Stage279 source")
    full=source.get("steady_pair_verdict")
    if (not isinstance(full,dict)
            or full.get("result")!="SAME_NRO_IDLE_SWITCH_ARCHIVED_PAIRS_REVERIFIED"
            or full.get("original_guest_sd_reopened_offline") is not False
            or full.get("randomized_or_causal_inference") is not False
            or full.get("audible_output_or_physical_switch_tested") is not False):
        raise CorrelationError("unverified paired Stage279 source")
    pairs=full.get("pairs")
    details=source.get("per_run_windows")
    if (not isinstance(pairs,list) or not 2<=len(pairs)<=12
            or not isinstance(details,list) or len(details)!=len(pairs)
            or source.get("complete_verified_source_pair_count")!=len(pairs)):
        raise CorrelationError("missing exact Stage279 paired source windows")
    ids=[p.get("run_id") for p in pairs if isinstance(p,dict)]
    if (len(ids)!=len(pairs) or
            any(type(i) is not int or i<=0 for i in ids)
            or ids!=sorted(set(ids))
            or source.get("source_run_ids")!=ids
            or full.get("independent_workflow_run_ids")!=ids):
        raise CorrelationError("unmatched source run identity")
    if [r.get("run_id") for r in details if isinstance(r,dict)]!=ids:
        raise CorrelationError("guest window order or identity changed")
    if full.get("nro_sha256")!=source.get("nro_sha256"):
        raise CorrelationError("source NRO does not match paired report")
    for pair in pairs:
        if (pair.get("nro_sha256")!=full["nro_sha256"]
                or pair.get("idle_original_sd_audited_in_prior_workflow") is not True
                or pair.get("switch_original_sd_audited_in_prior_workflow") is not True
                or pair.get("all_copied_guest_bytes_reverified") is not True):
            raise CorrelationError("original SD audit binding absent")
    expected=summarize(pairs)
    for key in ("totals","rates","paired_rate_directions"):
        if expected[key]!=full.get(key):
            raise CorrelationError("Stage279 source aggregate does not reconcile")

    windows={}
    for pair,detail in zip(pairs,details):
        run=pair["run_id"]
        windows[run]={}
        for mode in MODES:
            selected=detail.get(mode)
            if (not isinstance(selected,dict)
                    or selected.get("window_counts_match_exact_slow_timestamps") is not True
                    or selected.get("seconds_compared")!=WINDOW_COUNT
                    or selected.get("first_guest_second")!=BEGIN_SECOND
                    or selected.get("last_guest_second")!=END_SECOND):
                raise CorrelationError("per-second trace lacks exact timestamp audit")
            rows=selected.get("per_second")
            if not isinstance(rows,list) or len(rows)!=WINDOW_COUNT:
                raise CorrelationError("not exactly 51 audited per-second bins")
            rows=[_row(row,BEGIN_SECOND+i) for i,row in enumerate(rows)]
            for field in METRICS:
                val=sum(row[field] for row in rows)
                if (val!=selected.get(field) or
                        val!=pair.get(f"{mode}_{field}")):
                    raise CorrelationError("selected bins fail Stage279 conservation")
            windows[run][mode]=rows

    slices=[]
    for begin,end in SEGMENTS:
        segment_pairs=[]
        for pair in pairs:
            row=pair.copy()
            for mode in MODES:
                subset=windows[pair["run_id"]][mode][
                    begin-BEGIN_SECOND:end-BEGIN_SECOND+1]
                if len(subset)!=17 or [r["second"] for r in subset]!=list(
                        range(begin,end+1)):
                    raise CorrelationError("temporal segment missing second")
                for field in METRICS:
                    row[f"{mode}_{field}"]=sum(r[field] for r in subset)
                row[f"{mode}_seconds"]=17
            segment_pairs.append(row)
        verdict=summarize(segment_pairs)
        totals=verdict["totals"]
        differences={
            threshold:round(
                1000*totals["switch_"+threshold]/totals["switch_attempts"]
                -1000*totals["idle_"+threshold]/totals["idle_attempts"],6)
            for threshold in ("ge40","ge50")
        }
        slices.append({
            "first_guest_second":begin,
            "last_guest_second":end,
            "seconds_per_mode":17,
            "totals":totals,
            "rates":verdict["rates"],
            "switch_minus_idle_per_1000":differences,
            "paired_rate_directions":verdict["paired_rate_directions"],
            "per_run_pairs":verdict["pairs"],
        })
    for mode in MODES:
        for field in METRICS:
            key=f"{mode}_{field}"
            if sum(s["totals"][key] for s in slices)!=full["totals"][key]:
                raise CorrelationError("17-second segments do not conserve 51-second totals")
    return {
        "schema":SCHEMA,
        "result":"STAGE279_VERIFIED_TEMPORAL_THIRDS_RECONCILED",
        "stage279_result":source["result"],
        "source_run_ids":ids,
        "nro_sha256":source["nro_sha256"],
        "pair_count":len(pairs),
        "first_included_second":BEGIN_SECOND,
        "last_included_second":END_SECOND,
        "segment_count":len(slices),
        "segments":slices,
        "complete_51s_totals":full["totals"],
        "conserves_every_attempt_and_threshold":True,
        "previous_live_original_sd_audits_required":True,
        "reanalyzed_original_guest_sd_live":False,
        "same_order_switch_then_idle":True,
        "randomized_experiment":False,
        "music_switch_causal_effect_proven":False,
        "audible_output_or_underruns_measured":False,
        "physical_switch_tested":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verified-steady-state",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite of earlier temporal comparison")
        source=json.loads(args.verified_steady_state.read_text("utf-8"))
        result=analyze_temporal_thirds(source)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],"pairs":result["pair_count"],
            "segment_differences":[s["switch_minus_idle_per_1000"]
                                   for s in result["segments"]],
            "causality_proven":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError) as exc:
        print(json.dumps({"result":"TEMPORAL_THIRDS_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
