#!/usr/bin/env python3
"""Stage277: six (or 2–12) same-NRO paired idle/switch NeXium archive checks.

Live original guest SD files existed only on each CI runner. Reopen the
archived copies, reproduce the counters and compare against *earlier*
successful original-SD audit results. These reports are not signatures
and do not establish audible effects or causality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from audit_nexium_audout_queue import parse_telemetry
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError,parse_clock
)
from audit_nexium_audout_slow_calls import parse_slow
from audit_nexium_audout_idle_control import parse_idle_scene
from compare_nexium_verified_slow_runs import (
    PREFIX,audit_archive,digest,json_record,MAX_ARCHIVE_UNCOMPRESSED
)

IDLE_PREFIX="runtime-evidence/idle-control/"
IDLE_COPIES={
    "scene":"soak-sd-unverified.csv",
    "queue":"soak-audout-sd-unverified.csv",
    "latency":"soak-audout-latency-unverified.csv",
    "clock":"soak-audout-clock-unverified.csv",
    "slow":"soak-audout-slow-unverified.csv",
}
RECEIPTS={
    "queue":"soak-audout-export-result.txt",
    "latency":"soak-audout-latency-export-result.txt",
    "clock":"soak-audout-clock-export-result.txt",
    "slow":"soak-audout-slow-export-result.txt",
}
PAIR_KEYS=(
    ("guest_idle_audout_attempts","guest_audout_attempts"),
    ("idle_slow_ge40ms_calls","slow_ge40ms_calls"),
    ("idle_slow_ge50ms_calls","slow_ge50ms_calls"),
)

def read_bound_idle(path:Path, switch:dict)->dict:
    with zipfile.ZipFile(path) as z:
        members=z.infolist()
        names=[m.filename for m in members]
        required={
            IDLE_PREFIX+"idle-audout-verification.json",
            IDLE_PREFIX+"idle-vs-switch.json",
            *[IDLE_PREFIX+x for x in IDLE_COPIES.values()],
            *[IDLE_PREFIX+x for x in RECEIPTS.values()],
        }
        if (len(names)!=len(set(names))
                or not required.issubset(names)
                or any(n.startswith("/") or ".." in n.split("/")
                       or "\\" in n for n in names)
                or sum(m.file_size for m in members)>MAX_ARCHIVE_UNCOMPRESSED
                or z.testzip() is not None):
            raise CorrelationError("unsafe, incomplete or altered paired evidence")
        report=json_record(z.read(IDLE_PREFIX+"idle-audout-verification.json"))
        pair=json_record(z.read(IDLE_PREFIX+"idle-vs-switch.json"))
        raw={key:z.read(IDLE_PREFIX+value)
             for key,value in IDLE_COPIES.items()}
        for name in RECEIPTS.values():
            if IDLE_PREFIX+name not in names:
                raise CorrelationError("missing writer receipt")
        receipts={key:z.read(IDLE_PREFIX+name)
                  for key,name in RECEIPTS.items()}

    if (report.get("schema")!="vh-nexium-no-scene-switch-guest-audout/v1"
            or report.get("result")!="ORIGINAL_SD_IDLE_50S_AUDOUT_VERIFIED"
            or report.get("original_sd_verified_during_run") is not True
            or report.get("source_mode")!="NO_AB_SCENE_KEYS_SENT"
            or report.get("guest_scene_change_inputs")!=0
            or report.get("slow_records_dropped")!=0
            or report.get("physical_switch_tested") is not False
            or report.get("audible_underruns_measured") is not False
            or report.get("run_id")!=switch["run_id"]
            or report.get("run_attempt")!=switch["run_attempt"]
            or report.get("git_sha")!=switch["git_sha"]
            or report.get("nro_sha256")!=switch["nro_sha256"]):
        raise CorrelationError("idle result not matched to switch NRO/workflow")
    if (set(report.get("idle_guest_sd_sha256",{}))!=set(IDLE_COPIES)
            or any(report["idle_guest_sd_sha256"][name]!=digest(content)
                   for name,content in raw.items())):
        raise CorrelationError("idle original guest SD hash and copies disagree")
    for name,receipt in receipts.items():
        expected=(f"export_status=0\npath_present=1\n"
                  f"file_size={len(raw[name])}\n").encode("ascii")
        if receipt!=expected:
            raise CorrelationError("idle SD original writer receipt mismatch")

    clock=parse_clock(raw["clock"])
    startup=parse_idle_scene(raw["scene"],clock["origin_ns"])
    latency=parse_latency(raw["latency"])
    queue=parse_telemetry(raw["queue"])
    slow=parse_slow(raw["slow"],clock["origin_ns"],latency)
    if (report.get("guest_scene_events")!=startup
            or report.get("guest_audio_second_windows")!=latency["windows"]
            or report.get("guest_audout_attempts")!=latency["attempts"]
            or report.get("audout_failed_attempts")!=0
            or queue["attempts"]!=latency["attempts"]
            or queue["releases"]!=queue["attempts"]
            or queue["windows"]!=latency["windows"]
            or clock["attempts"]!=latency["attempts"]
            or clock["last_second"]!=latency["windows"]-1
            or queue["failed_attempts"]!=0
            or latency["failed_attempts"]!=0
            or queue["max_call_us"]!=latency["max_call_us"]
            or report.get("slow_max_call_us")!=latency["max_call_us"]
            or report.get("slow_ge40ms_calls")!=len(slow)
            or report.get("slow_ge50ms_calls")!=latency["ge50ms_calls"]
            or latency["windows"]<50):
        raise CorrelationError("idle control archived counters cannot be reproduced")

    if (pair.get("schema")!="vh-nexium-idle-versus-switch-same-nro/v1"
            or pair.get("result")!="SAME_NRO_GUEST_IDLE_AND_SWITCH_MEASUREMENTS_VERIFIED"
            or pair.get("nro_sha256")!=switch["nro_sha256"]
            or pair.get("idle_run_id")!=switch["run_id"]
            or pair.get("scene_switching_causality_proven") is not False
            or pair.get("physical_hardware_tested") is not False
            or pair.get("audible_underruns_measured") is not False):
        raise CorrelationError("stored idle-versus-switch summary is invalid")
    for key,field in PAIR_KEYS:
        if pair.get(key)!=report[field]:
            raise CorrelationError("idle paired summary differs from original-SD auditor")
    expected_switch={
        "guest_switch_audout_attempts":switch["audout_attempts"],
        "switch_slow_ge40ms_calls":switch["slow_records"],
        "switch_slow_ge50ms_calls":switch["slow_ge50_calls"],
    }
    if any(pair.get(key)!=value for key,value in expected_switch.items()):
        raise CorrelationError("switch paired summary differs from exact slow-call auditor")
    for stem,count,attempts in [
        ("idle",len(slow),latency["attempts"]),
        ("switch",switch["slow_records"],switch["audout_attempts"])
    ]:
        for minimum,actual in [("ge40",count),("ge50",
            latency["ge50ms_calls"] if stem=="idle" else switch["slow_ge50_calls"])]:
            key=f"{stem}_{minimum}_per_1000_attempts"
            if key in pair and pair[key]!=round(1000*actual/attempts,3):
                raise CorrelationError("normalized rate differs from audited calls")
    return {
        "run_id":switch["run_id"],
        "git_sha":switch["git_sha"],
        "nro_sha256":switch["nro_sha256"],
        "idle_attempts":latency["attempts"],
        "switch_attempts":switch["audout_attempts"],
        "idle_ge40":len(slow),
        "switch_ge40":switch["slow_records"],
        "idle_ge50":latency["ge50ms_calls"],
        "switch_ge50":switch["slow_ge50_calls"],
        "idle_seconds":latency["windows"],
        "switch_seconds":switch["audout_seconds"],
        "idle_original_sd_audited_in_prior_workflow":True,
        "switch_original_sd_audited_in_prior_workflow":True,
        "all_copied_guest_bytes_reverified":True,
    }

def summarize(pairs:list[dict])->dict:
    if not 2<=len(pairs)<=12:
        raise CorrelationError("need between 2 and 12 separate accepted pairs")
    ids=[p["run_id"] for p in pairs]
    nro={p["nro_sha256"] for p in pairs}
    if len(set(ids))!=len(ids) or len(nro)!=1:
        raise CorrelationError("duplicated run or different NRO")
    totals={}
    for field in ("attempts","ge40","ge50"):
        for mode in ("idle","switch"):
            key=mode+"_"+field
            totals[key]=sum(p[key] for p in pairs)
    if any(totals[mode+"_attempts"]<=0 for mode in ("idle","switch")):
        raise CorrelationError("invalid attempted buffer denominator")
    normalized={
        mode+"_"+band+"_per_1000_attempts":round(
            1000*totals[mode+"_"+band]/totals[mode+"_attempts"],3)
        for mode in ("idle","switch") for band in ("ge40","ge50")
    }
    directions={
        band:{
            "switch_rate_higher":sum(
                p["switch_"+band]*p["idle_attempts"] >
                p["idle_"+band]*p["switch_attempts"] for p in pairs),
            "idle_rate_higher":sum(
                p["switch_"+band]*p["idle_attempts"] <
                p["idle_"+band]*p["switch_attempts"] for p in pairs),
            "exact_ties":sum(
                p["switch_"+band]*p["idle_attempts"] ==
                p["idle_"+band]*p["switch_attempts"] for p in pairs),
        } for band in ("ge40","ge50")
    }
    return {
        "schema":"vh-nexium-idle-switch-multi-pair/v1",
        "result":"SAME_NRO_IDLE_SWITCH_ARCHIVED_PAIRS_REVERIFIED",
        "nro_sha256":next(iter(nro)),
        "pairs":sorted(pairs,key=lambda p:p["run_id"]),
        "independent_workflow_run_ids":sorted(ids),
        "totals":totals,"rates":normalized,
        "paired_rate_directions":directions,
        "original_guest_sd_reopened_offline":False,
        "original_sd_audit_witness":"PRIOR_SUCCEEDED_LIVE_NEXIUM_WORKFLOW",
        "randomized_or_causal_inference":False,
        "audible_output_or_physical_switch_tested":False,
    }

def audit_pair_archives(paths:list[Path])->dict:
    checked=[]
    for path in paths:
        switch=audit_archive(path)
        checked.append(read_bound_idle(path,switch))
    return summarize(checked)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.is_symlink() or args.output.exists():
            raise CorrelationError("refuse to replace previous multi-pair verdict")
        report=audit_pair_archives(args.archive)
        args.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        print(json.dumps({
            "result":report["result"],
            "pairs":len(report["pairs"]),
            "rates":report["rates"],
            "physical_switch_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,zipfile.BadZipFile) as exc:
        print(json.dumps({"result":"IDLE_SWITCH_MULTIRUN_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
