#!/usr/bin/env python3
"""Stage297: four real NeXium sessions, all-call vs queried-call slow rates.

Reopens ORIGINAL guest SD sources for each of 0,8,8,0 runs, rechecks
the bounded service sample against exact slow-call IDs, and contrasts
sampling with the complete independently recorded >=40ms API calls.
Not a randomized experiment or hardware/DAC/scheduler measurement.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_audout_idle_control import original_and_copy
from audit_nexium_audout_queue import parse_telemetry
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import CorrelationError,parse_clock,parse_scene_inputs
from audit_nexium_audout_slow_calls import parse_slow
from audit_nexium_audout_service_probes import parse_probes

SCHEMA="vh-nexium-four-sessions-actual-probe-versus-entire-audout/v1"
LABELS=("phase0_first","phase8_first","phase8_reversed","phase0_reversed")
PHASES=(0,8,8,0)
MAP=(
    ("queue","audio-audout-queue-*.csv","soak-audout-sd-unverified.csv",
     "soak-audout-sd-locations.txt","soak-audout-export-result.txt"),
    ("clock","audio-audout-clock-*.csv","soak-audout-clock-unverified.csv",
     "soak-audout-clock-locations.txt","soak-audout-clock-export-result.txt"),
    ("latency","audio-audout-latency-*.csv","soak-audout-latency-unverified.csv",
     "soak-audout-latency-locations.txt","soak-audout-latency-export-result.txt"),
    ("slow","audio-audout-slow-*.csv","soak-audout-slow-unverified.csv",
     "soak-audout-slow-locations.txt","soak-audout-slow-export-result.txt"),
    ("probe","audio-audout-probe-*.csv","soak-audout-probe-unverified.csv",
     "soak-audout-probe-locations.txt","soak-audout-probe-export-result.txt"),
    ("scene","audio-scene-trace-*.csv","soak-sd-unverified.csv",
     "soak-sd-locations.txt",None),
)


def rate(n:int,d:int)->Fraction:
    if (type(n) is not int or type(d) is not int or not 0<=n<=d or d==0):
        raise CorrelationError("not an exact audout count/denominator")
    return Fraction(1000*n,d)


def signed(n:Fraction)->float:
    return round(float(n),6)


def source_profile(*,sd_root:Path,evidence:Path,phase:int,
                   verified_row:dict)->dict:
    folder=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if (sd_root.is_symlink() or evidence.is_symlink()
            or folder.is_symlink() or not folder.is_dir()):
        raise CorrelationError("missing independently mounted original SD")
    raw={}
    for label,pattern,copy,locations,receipt in MAP:
        raw[label]=original_and_copy(folder,evidence,pattern,copy,locations,receipt)
    clock=parse_clock(raw["clock"])
    telemetry=parse_telemetry(raw["queue"],phase=phase)
    latency=parse_latency(raw["latency"])
    slow=parse_slow(raw["slow"],clock["origin_ns"],latency)
    inputs=parse_scene_inputs(raw["scene"])
    probe=parse_probes(raw["probe"],clock,telemetry,latency,slow,phase=phase)
    full_ge40=len(slow)
    full_ge50=sum(x["duration_ns"]>=50_000_000 for x in slow)
    queried_ge40=len(probe["probed_slow_calls"])
    queried_ge50=sum(x["duration_ns"]>=50_000_000
                     for x in probe["probed_slow_calls"])
    queries=probe["queue_probe_samples"]
    attempts=clock["attempts"]
    if (telemetry["attempts"]!=attempts or latency["attempts"]!=attempts
            or latency["from40to50ms_calls"]+latency["ge50ms_calls"]!=full_ge40
            or len(inputs)!=10
            or probe["audout_attempts"]!=attempts
            or len(probe["sample_records"])!=queries
            or queries!=verified_row["service_query_count"]
            or attempts!=verified_row["audout_attempts"]
            or probe["declared_query_phase"]!=verified_row["phase"]
            or queried_ge40!=verified_row["slow_ge40_on_queried_attempts"]
            or queried_ge50!=verified_row["slow_ge50_on_queried_attempts"]
            or hashlib.sha256(raw["probe"]).hexdigest()!=
                 verified_row["original_guest_probe_sha256"]
            or probe["queue_probe_dropped"]!=0
            or telemetry["queue_probes_ok"]!=
                 verified_row["service_query_success"]
            or telemetry["queue_probes_failed"]!=
                 verified_row["service_query_failure"]):
        raise CorrelationError("full-call original source differs from Stage296 query witness")
    if any(x["returned"] is not True for x in slow):
        raise CorrelationError("unexpected failed original guest slow call")
    if (sum(x["attempt"]%16==((phase+1)%16) for x in slow)!=queried_ge40):
        raise CorrelationError("the exact queried phase loses slow-call attempt IDs")
    if (sum(x["attempt"]%16==((phase+1)%16) and
            x["duration_ns"]>=50_000_000 for x in slow)!=queried_ge50):
        raise CorrelationError("phase-specific >=50ms slow-call IDs disagree")
    return {
        "phase":phase,
        "audout_attempts":attempts,
        "sample_count":queries,
        "slow_ge40_all_calls":full_ge40,
        "slow_ge50_all_calls":full_ge50,
        "slow_ge40_queried":queried_ge40,
        "slow_ge50_queried":queried_ge50,
        "original_slow_csv_sha256":hashlib.sha256(raw["slow"]).hexdigest(),
        "original_probe_csv_sha256":hashlib.sha256(raw["probe"]).hexdigest(),
        "original_scene_csv_sha256":hashlib.sha256(raw["scene"]).hexdigest(),
        "source_guest_SD_reread_and_verified":True,
    }


def compare_complete(stage296:dict,profiles:list[dict])->dict:
    if (stage296.get("result")!=
            "FOUR_ORIGINAL_GUEST_SD_PHASE0_PHASE8_REVERSED_ORDER_VERIFIED"
            or stage296.get("capture_sequence")!=list(LABELS)
            or stage296.get("all_four_guest_SD_sources_originally_audited") is not True
            or stage296.get("no_unqueried_queue_values_imputed") is not True
            or stage296.get("causal_effect_of_phase_or_order_proven") is not False
            or stage296.get("physical_switch_audio_or_DAC_underrun_measured") is not False
            or not isinstance(profiles,list) or len(profiles)!=4):
        raise CorrelationError("unverified four-run source for all-call study")
    rows=stage296["session_records"]
    if (not isinstance(rows,list) or len(rows)!=4
            or len(set(x["original_guest_probe_sha256"] for x in rows))!=4):
        raise CorrelationError("not four independent guest originals")
    descriptions=[]
    for label,phase,row,src in zip(LABELS,PHASES,rows,profiles):
        if (row["label"]!=label or row["phase"]!=phase
                or src.get("phase")!=phase
                or src.get("source_guest_SD_reread_and_verified") is not True
                or src.get("original_probe_csv_sha256")!=
                   row["original_guest_probe_sha256"]
                or src.get("sample_count")!=row["service_query_count"]
                or src.get("audout_attempts")!=row["audout_attempts"]
                or src.get("slow_ge40_queried")!=
                   row["slow_ge40_on_queried_attempts"]
                or src.get("slow_ge50_queried")!=
                   row["slow_ge50_on_queried_attempts"]):
            raise CorrelationError("one original source does not match verified order witness")
        if (src["slow_ge50_all_calls"]>src["slow_ge40_all_calls"]
                or src["slow_ge50_queried"]>src["slow_ge40_queried"]):
            raise CorrelationError(">=50ms must be a subset of >=40ms calls")
        for band in ("ge40","ge50"):
            observed=src["slow_"+band+"_queried"]
            total=src["slow_"+band+"_all_calls"]
            if (type(observed) is not int or type(total) is not int or
                    not 0<=observed<=total<=src["audout_attempts"]):
                raise CorrelationError("invalid original latency band conservation")
        if len(src["original_slow_csv_sha256"])!=64:
            raise CorrelationError("missing original slow CSV digest")
        d={
            "label":label,"phase":phase,
            "audout_attempts":src["audout_attempts"],
            "queried_attempts":src["sample_count"],
            "source_original_slow_sha256":src["original_slow_csv_sha256"],
            "full_slow_ge40":src["slow_ge40_all_calls"],
            "full_slow_ge50":src["slow_ge50_all_calls"],
            "queried_slow_ge40":src["slow_ge40_queried"],
            "queried_slow_ge50":src["slow_ge50_queried"],
        }
        for band in ("ge40","ge50"):
            full=rate(src["slow_"+band+"_all_calls"],src["audout_attempts"])
            sampled=rate(src["slow_"+band+"_queried"],src["sample_count"])
            d[band+"_per_1000_all_calls"]=signed(full)
            d[band+"_per_1000_queried_calls"]=signed(sampled)
            d[band+"_sample_minus_full_per_1000"]=signed(sampled-full)
        descriptions.append(d)
    def compare(a:dict,b:dict,band:str,scope:str)->Fraction:
        if scope=="all":
            return (rate(a["slow_"+band+"_all_calls"],a["audout_attempts"])-
                    rate(b["slow_"+band+"_all_calls"],b["audout_attempts"]))
        return (rate(a["slow_"+band+"_queried"],a["sample_count"])-
                rate(b["slow_"+band+"_queried"],b["sample_count"]))
    pairs={}
    for title,first,second in (("first_pair",0,1),("reversed_pair",3,2)):
        pairs[title]={}
        for band in ("ge40","ge50"):
            all_delta=compare(profiles[first],profiles[second],band,"all")
            sampled_delta=compare(profiles[first],profiles[second],band,"queried")
            pairs[title][band]={
                "phase0_minus_phase8_per_1000_all_calls":signed(all_delta),
                "phase0_minus_phase8_per_1000_queried_calls":signed(sampled_delta),
                "sample_minus_full_contrast_per_1000":signed(sampled_delta-all_delta),
            }
    if (abs(pairs["first_pair"]["ge40"][
            "phase0_minus_phase8_per_1000_queried_calls"]-
            stage296["forward_phase0_minus_phase8"][
                "slow_ge40_on_queried_attempts_delta_per_1000_queried_attempts"])
            >0.0000011 or
        abs(pairs["reversed_pair"]["ge40"][
            "phase0_minus_phase8_per_1000_queried_calls"]-
            stage296["reversed_phase0_minus_phase8"][
                "slow_ge40_on_queried_attempts_delta_per_1000_queried_attempts"])
            >0.0000011):
        raise CorrelationError("Stage296 sampled contrasts are not conserved")
    return {
        "schema":SCHEMA,
        "result":"FOUR_REAL_GUEST_SD_FULL_AUDOUT_VS_QUERIED_RATES_VERIFIED",
        "source_git_sha":stage296["git_sha"],
        "source_run_id":stage296["run_id"],
        "capture_sequence":list(LABELS),
        "sessions":descriptions,
        "pairs":pairs,
        "four_current_run_original_slow_sources_reread":True,
        "queried_slow_call_IDs_exact_subset_of_full_calls":True,
        "no_unqueried_queue_service_counts_imputed":True,
        "run_order_fixed_not_randomized":True,
        "software_API_latency_only":True,
        "phase_or_music_switch_causality_proven":False,
        "DAC_underruns_or_physical_Switch_audio_measured":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage296",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    for label in LABELS:
        p.add_argument("--"+label+"-sd-root",type=Path,required=True)
        p.add_argument("--"+label+"-evidence",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refuse overwrite of four-run full-call report")
        previous=json.loads(a.stage296.read_text(encoding="utf-8"))
        profiles=[]
        for name,phase,row in zip(LABELS,PHASES,previous["session_records"]):
            profiles.append(source_profile(
                sd_root=getattr(a,name+"_sd_root"),
                evidence=getattr(a,name+"_evidence"),
                phase=phase,verified_row=row))
        report=compare_complete(previous,profiles)
        a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "full_ge40_by_capture":{x["label"]:x["full_slow_ge40"]
                                    for x in report["sessions"]},
            "sample_ge40_by_capture":{x["label"]:x["queried_slow_ge40"]
                                      for x in report["sessions"]},
            "first_pair":report["pairs"]["first_pair"]["ge40"],
            "reversed_pair":report["pairs"]["reversed_pair"]["ge40"],
            "DAC_or_hardware_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError,KeyError) as exc:
        print(json.dumps({"result":"FOUR_FULL_CALL_RATE_AUDIT_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
