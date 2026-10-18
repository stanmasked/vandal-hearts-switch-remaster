#!/usr/bin/env python3
"""Stage295: compare TWO actually queried service phases in consecutive NROs.

The input is two separately verified ORIGINAL-GUEST-SD probe audit JSONs:
baseline (0) and experimentally compiled (8). It never infers the
service queue count on unobserved calls or equates two runs' guest clocks.
Different NROs / captures are NOT randomized A/B inference.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from audit_nexium_audout_scene_correlation import CorrelationError

SCHEMA="vh-nexium-real-phase0-phase8-service-observations/v1"
_HEX=re.compile(r"[0-9a-f]{64}\Z")
_GIT_HEX=re.compile(r"[0-9a-f]{40}\Z")


def _hex64(value:object)->bool:
    return isinstance(value,str) and _HEX.fullmatch(value) is not None


def _hex40(value:object)->bool:
    return isinstance(value,str) and _GIT_HEX.fullmatch(value) is not None


def inspect_observations(report:dict,phase:int)->dict:
    if type(phase) is not int or phase not in (0,8):
        raise CorrelationError("unsupported experimental phase")
    if (report.get("result")!="GUEST_PRE_SUBMIT_SERVICE_PROBES_RECONCILED"
            or report.get("schema")!="vh-audout-service-probe-guest-clock/v1"
            or report.get("declared_query_phase")!=phase
            or report.get("original_guest_sd_opened_in_current_workflow") is not True
            or report.get("pre_submit_queue_service_snapshot_only") is not True
            or report.get("queries_per_sixteen_attempts_at_most_one") is not True
            or report.get("scene_input_count")!=10
            or report.get("probe_samples_begin_within_500ms_of_input") is None
            or report.get("scheduler_or_DAC_state_measured") is not False
            or report.get("physical_switch_tested") is not False
            or report.get("audible_underruns_measured") is not False
            or report.get("scene_to_probe_causality_proven") is not False
            or report.get("query_timestamp_is_exactly_recorded") is not False
            or report.get("audout_submission_begin_timestamp_is_exactly_recorded") is not True
            or not _hex64(report.get("guest_original_probe_sha256"))
            or report.get("copied_probe_sha256")!=report.get("guest_original_probe_sha256")
            or not _hex64(report.get("guest_writer_receipt_sha256"))
            or report.get("queue_probe_dropped")!=0):
        raise CorrelationError("original guest SD queue samples are not independently bound")
    attempts=report.get("audout_attempts")
    records=report.get("sample_records")
    slow=report.get("probed_slow_calls")
    if (type(attempts) is not int or attempts<32 or
            not isinstance(records,list) or not records or
            not isinstance(slow,list) or
            report.get("queue_probe_samples")!=len(records) or
            len(records)!=(attempts+15-phase)//16):
        raise CorrelationError("sample count is not canonical for declared phase")
    last_ns=0
    success=failed=0
    hist=Counter()
    indexed={}
    for i,row in enumerate(records):
        if (type(row.get("index")) is not int or row["index"]!=i
                or type(row.get("attempt")) is not int
                or row["attempt"]!=1+phase+16*i
                or row["attempt"]>attempts
                or type(row.get("submit_begin_ns")) is not int
                or row["submit_begin_ns"]<=last_ns
                or type(row.get("audio_second")) is not int
                or row["audio_second"]<0):
            raise CorrelationError("not exact indexed original guest query attempts")
        last_ns=row["submit_begin_ns"]
        indexed[row["attempt"]]=row
        if row.get("query_succeeded") is True:
            count=row.get("pre_submit_queue_count")
            if type(count) is not int or count<0:
                raise CorrelationError("invalid observed queue service count")
            hist[count]+=1
            success+=1
        elif (row.get("query_succeeded") is False and
              row.get("pre_submit_queue_count") is None):
            failed+=1
        else:
            raise CorrelationError("failed query incorrectly assigned queue occupancy")
    if (report.get("queue_probe_successes")!=success or
            report.get("queue_probe_failures")!=failed or
            success+failed!=len(records)):
        raise CorrelationError("original query outcomes do not match totals")
    slow40=slow50=0
    seen=set()
    for row in slow:
        attempt=row.get("attempt")
        duration=row.get("duration_ns")
        if (type(attempt) is not int or attempt not in indexed
                or attempt in seen
                or type(duration) is not int or duration<40_000_000
                or any(row.get(field)!=indexed[attempt].get(field)
                       for field in (
                           "index","submit_begin_ns","audio_second",
                           "query_succeeded","pre_submit_queue_count"))):
            raise CorrelationError("slow call is not one of the original service query attempts")
        seen.add(attempt)
        slow40+=1
        slow50+=duration>=50_000_000
    return {
        "phase":phase,
        "original_guest_probe_sha256":report["guest_original_probe_sha256"],
        "audout_attempts":attempts,
        "service_query_count":len(records),
        "service_query_success":success,
        "service_query_failure":failed,
        "measured_queue_count_histogram":{
            str(n):hist[n] for n in sorted(hist)
        },
        "successful_service_queries_with_zero_queue":hist[0],
        "successful_service_queries_with_nonzero_queue":success-hist[0],
        "slow_ge40_on_queried_attempts":slow40,
        "slow_ge50_on_queried_attempts":slow50,
        "slow_ge40_per_1000_queried_attempts":round(
            1000*slow40/len(records),6),
        "service_query_nonzero_fraction_among_successes":
            round((success-hist[0])/success,6) if success else None,
        "guest_scene_changing_inputs":10,
        "queue_query_is_before_audio_submit":True,
    }


def compare_real_phases(baseline:dict,phase8:dict,
                        baseline_manifest:dict,experimental_manifest:dict)->dict:
    normal=inspect_observations(baseline,0)
    alt=inspect_observations(phase8,8)
    main_sha=baseline_manifest.get("nro_sha256")
    experimental_sha=experimental_manifest.get("nro_sha256")
    if (baseline_manifest.get("schema")!="vh-switch-same-run-nro/v1"
            or experimental_manifest.get("schema")!="vh-switch-explicit-probe-phase/v1"
            or not _hex64(main_sha) or not _hex64(experimental_sha)
            or main_sha==experimental_sha
            or experimental_manifest.get("baseline_sha256")!=main_sha
            or experimental_manifest.get("phase")!=8
            or baseline_manifest.get("git_sha")!=experimental_manifest.get("git_sha")
            or baseline_manifest.get("run_id")!=experimental_manifest.get("run_id")
            or baseline_manifest.get("run_attempt")!=experimental_manifest.get("run_attempt")
            or type(baseline_manifest.get("run_id")) is not int
            or type(baseline_manifest.get("run_attempt")) is not int
            or baseline_manifest["run_id"]<1 or baseline_manifest["run_attempt"]<1
            or not _hex40(baseline_manifest.get("git_sha"))
            or type(baseline_manifest.get("nro_bytes")) is not int
            or type(experimental_manifest.get("nro_bytes")) is not int
            or baseline_manifest["nro_bytes"]<=0
            or experimental_manifest["nro_bytes"]<=0
            or normal["original_guest_probe_sha256"]==
               alt["original_guest_probe_sha256"]):
        raise CorrelationError("phase0 and phase8 are not distinct same-run guest NRO sources")
    return {
        "schema":SCHEMA,
        "result":"REAL_DISTINCT_NRO_ORIGINAL_GUEST_SD_PHASE0_AND_PHASE8_RECONCILED",
        "git_sha":baseline_manifest["git_sha"],
        "run_id":baseline_manifest["run_id"],
        "run_attempt":baseline_manifest["run_attempt"],
        "baseline_nro_sha256":main_sha,
        "phase8_nro_sha256":experimental_sha,
        "phase0":normal,
        "phase8":alt,
        "both_modes_have_real_pre_submit_queue_observations":True,
        "distinct_current_run_nro_binaries_and_guest_sources":True,
        "captured_sequentially_not_simultaneously":True,
        "same_audio_scene_switch_input_count":10,
        "no_unqueried_phase_service_occupancy_imputed":True,
        "differing_guest_run_clocks_not_directly_compared":True,
        "not_a_randomized_trial":True,
        "causal_effect_of_query_phase_proven":False,
        "guest_scheduler_or_DAC_starvation_measured":False,
        "physical_switch_or_audible_playback_confirmed":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("phase0-probe","phase8-probe","phase0-manifest",
                 "phase8-manifest","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refuse to replace existing phase comparison")
        def load(path:Path)->dict:
            return json.loads(path.read_text(encoding="utf-8"))
        result=compare_real_phases(
            load(a.phase0_probe),load(a.phase8_probe),
            load(a.phase0_manifest),load(a.phase8_manifest))
        a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "phase0":{k:result["phase0"][k] for k in
                      ("service_query_count","successful_service_queries_with_nonzero_queue",
                       "slow_ge40_on_queried_attempts","slow_ge50_on_queried_attempts")},
            "phase8":{k:result["phase8"][k] for k in
                      ("service_query_count","successful_service_queries_with_nonzero_queue",
                       "slow_ge40_on_queried_attempts","slow_ge50_on_queried_attempts")},
            "hardware_confirmed":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({
            "result":"REAL_TWO_PHASE_SERVICE_COMPARISON_NOT_VERIFIED",
            "error":str(exc),
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
