#!/usr/bin/env python3
"""Stage279: exact same guest-audio seconds 1..51, cold-start excluded.

Only previously original-SD-audited, same-NRO NeXium idle/switch
evidence may enter this *retrospective* comparison. Endpoints count
audoutPlayBuffer durations, NOT DAC timing, audible defects or causation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile

from audit_nexium_audout_scene_correlation import CorrelationError,parse_clock
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_slow_calls import parse_slow
from compare_nexium_idle_switch_pairs import (
    audit_pair_archives,summarize,IDLE_PREFIX
)
from analyze_nexium_idle_switch_variability import analyze

SCHEMA="vh-nexium-steady-audout-same-51s/v1"
BEGIN_SECOND=1
END_SECOND=51
WINDOW_COUNT=END_SECOND-BEGIN_SECOND+1
SOURCES={
    "idle":IDLE_PREFIX,
    "switch":"runtime-evidence/scene-soak/",
}


def subwindow(raw_latency:bytes,raw_clock:bytes,raw_slow:bytes)->dict:
    latency=parse_latency(raw_latency)
    clock=parse_clock(raw_clock)
    calls=parse_slow(raw_slow,clock["origin_ns"],latency)
    if (latency["windows"]<=END_SECOND or
            clock["attempts"]!=latency["attempts"] or
            clock["last_second"]!=latency["windows"]-1 or
            latency["failed_attempts"]!=0 or
            any(not x["returned"] for x in calls)):
        raise CorrelationError("incomplete or failed steady-state audout trace")
    buckets=latency["per_second_call_bands"]
    selected=buckets[BEGIN_SECOND:END_SECOND+1]
    if (len(selected)!=WINDOW_COUNT or
            any(b["second"]!=i+BEGIN_SECOND
                for i,b in enumerate(selected))):
        raise CorrelationError("missing matched guest second windows")
    counts={
        "attempts":sum(b["attempts"] for b in selected),
        "ge40":sum(b["from40to50ms"]+b["ge50ms"] for b in selected),
        "ge50":sum(b["ge50ms"] for b in selected),
    }
    if counts["attempts"]<=0 or counts["ge50"]>counts["ge40"]:
        raise CorrelationError("invalid steady-state audio counts")
    selected_calls=[c for c in calls
                    if BEGIN_SECOND<=c["audio_second"]<=END_SECOND]
    if (len(selected_calls)!=counts["ge40"] or
            sum(c["duration_ns"]>=50_000_000 for c in selected_calls)
              !=counts["ge50"]):
        raise CorrelationError("slow timestamps disagree with matched seconds")
    startup=[c for c in calls if c["audio_second"]==0]
    first_slow=[c for c in startup if c["attempt"]==1]
    return {
        **counts,
        # Already checked against the independent exact slow-call timestamps.
        "per_second":[{
            "second":b["second"],"attempts":b["attempts"],
            "ge40":b["from40to50ms"]+b["ge50ms"],
            "ge50":b["ge50ms"],
        } for b in selected],
        "first_guest_second":BEGIN_SECOND,
        "last_guest_second":END_SECOND,
        "seconds_compared":WINDOW_COUNT,
        "complete_capture_seconds":latency["windows"],
        "excluded_first_second_attempts":buckets[0]["attempts"],
        "excluded_first_second_ge40":buckets[0]["from40to50ms"]+buckets[0]["ge50ms"],
        "excluded_first_second_ge50":buckets[0]["ge50ms"],
        "startup_first_call_ge40":bool(first_slow),
        "startup_first_call_duration_ns":(
            first_slow[0]["duration_ns"] if first_slow else None
        ),
        "slow_call_attempts_in_window":[c["attempt"] for c in selected_calls],
        "window_counts_match_exact_slow_timestamps":True,
    }


def analyze_archives(archives:list[Path],draws:int=16384)->dict:
    # Revalidate the FULL source evidence before extracting selected windows.
    whole=audit_pair_archives(archives)
    validated={p["run_id"]:p for p in whole["pairs"]}
    steady=[]
    details=[]
    for path in archives:
        with zipfile.ZipFile(path) as z:
            witness=json.loads(z.read("integrated-nro-preflight.json"))
            run_id=witness["run_id"]
            if run_id not in validated:
                raise CorrelationError("unverified source archive run ID")
            prior=validated[run_id]
            extracted={}
            for mode,prefix in SOURCES.items():
                part=subwindow(
                    z.read(prefix+"soak-audout-latency-unverified.csv"),
                    z.read(prefix+"soak-audout-clock-unverified.csv"),
                    z.read(prefix+"soak-audout-slow-unverified.csv"),
                )
                if (part["attempts"]>prior[mode+"_attempts"] or
                    part["ge40"]>prior[mode+"_ge40"] or
                    part["ge50"]>prior[mode+"_ge50"]):
                    raise CorrelationError("matched window exceeds full original-SD evidence")
                extracted[mode]=part
        steady.append({
            "run_id":run_id,
            "git_sha":prior["git_sha"],
            "nro_sha256":prior["nro_sha256"],
            "idle_attempts":extracted["idle"]["attempts"],
            "switch_attempts":extracted["switch"]["attempts"],
            "idle_ge40":extracted["idle"]["ge40"],
            "switch_ge40":extracted["switch"]["ge40"],
            "idle_ge50":extracted["idle"]["ge50"],
            "switch_ge50":extracted["switch"]["ge50"],
            "idle_seconds":WINDOW_COUNT,
            "switch_seconds":WINDOW_COUNT,
            "idle_original_sd_audited_in_prior_workflow":True,
            "switch_original_sd_audited_in_prior_workflow":True,
            "all_copied_guest_bytes_reverified":True,
        })
        details.append({
            "run_id":run_id,
            "idle":extracted["idle"],
            "switch":extracted["switch"],
        })
    steady.sort(key=lambda x:x["run_id"])
    details.sort(key=lambda x:x["run_id"])
    steady_verdict=summarize(steady)
    variable=analyze(steady_verdict,draws=draws)
    return {
        "schema":SCHEMA,
        "result":"ORIGINAL_SD_BOUND_COMMON_51S_AUDOUT_REVERIFIED",
        "nro_sha256":whole["nro_sha256"],
        "source_run_ids":sorted(validated),
        "complete_verified_source_pair_count":len(validated),
        "first_included_second":BEGIN_SECOND,
        "last_included_second":END_SECOND,
        "matched_second_count_per_mode":WINDOW_COUNT,
        "source_full_run_totals":whole["totals"],
        "source_full_run_rates":whole["rates"],
        "steady_pair_verdict":steady_verdict,
        "steady_variability":variable,
        "per_run_windows":details,
        "startup_second_excluded":True,
        "fixed_experiment_order_switch_then_idle":True,
        "guest_original_sd_reopened_in_offline_report":False,
        "previous_original_sd_auditor_results_required":True,
        "speaker_audio_output_measured":False,
        "physical_switch_tested":False,
        "music_switch_causality_established":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("will not overwrite prior steady-state report")
        report=analyze_archives(args.archive)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "pairs":report["complete_verified_source_pair_count"],
            "matched_seconds_per_mode":WINDOW_COUNT,
            "ge40_rates":{
                mode:report["steady_pair_verdict"]["rates"][mode+"_ge40_per_1000_attempts"]
                for mode in ("idle","switch")
            },
            "audible_underruns_measured":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError,zipfile.BadZipFile) as exc:
        print(json.dumps({"result":"COMMON_STEADY_STATE_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
