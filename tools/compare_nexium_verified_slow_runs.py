#!/usr/bin/env python3
"""Stage275: compare separate original-SD-audited NeXium slow-call ZIPs.

Only fully Stage274-accepted evidence is eligible. This offline process
rechecks *archived copies* and previously saved original-SD audit
verdicts; it cannot reopen the runner's ephemeral guest SD. Same NRO
software timestamps do not establish DAC timing or scene causality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError, parse_clock, parse_scene_inputs,
)
from audit_nexium_audout_slow_calls import parse_slow, relate

PREFIX = "runtime-evidence/scene-soak/"
EXPECTED = (
    "integrated-nro-preflight.json",
    PREFIX+"soak-audout-slow-unverified.csv",
    PREFIX+"soak-audout-slow-export-result.txt",
    PREFIX+"soak-audout-exact-slow-verification.json",
    PREFIX+"soak-audout-clock-unverified.csv",
    PREFIX+"soak-audout-latency-unverified.csv",
    PREFIX+"soak-audout-latency-verification.json",
    PREFIX+"soak-guest-optical.csv",
    PREFIX+"soak-audout-scene-correlation.json",
    PREFIX+"soak-verification.json",
)
MAX_ARCHIVE_UNCOMPRESSED=128*1024*1024

def digest(raw: bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def unique_object(pairs: list)->dict:
    result={}
    for key,value in pairs:
        if key in result:
            raise CorrelationError("duplicate JSON member")
        result[key]=value
    return result

def json_record(raw: bytes)->dict:
    if len(raw)>262144:
        raise CorrelationError("oversized JSON witness")
    try:
        data=json.loads(raw.decode("ascii"),object_pairs_hook=unique_object)
    except (UnicodeError,ValueError) as exc:
        raise CorrelationError("invalid JSON witness") from exc
    if not isinstance(data,dict):
        raise CorrelationError("JSON witness root is not an object")
    return data

def audit_archive(path: Path)->dict:
    if path.is_symlink() or not path.is_file():
        raise CorrelationError("archive must be regular, non-symlink file")
    with zipfile.ZipFile(path) as z:
        members=z.infolist()
        names=[m.filename for m in members]
        if (len(set(names))!=len(names)
                or any(n.startswith("/") or ".." in n.split("/")
                       or "\\" in n for n in names)
                or sum(m.file_size for m in members)>MAX_ARCHIVE_UNCOMPRESSED):
            raise CorrelationError("unsafe or oversized archive")
        if not set(EXPECTED).issubset(names):
            raise CorrelationError("missing complete Stage274 audit evidence")
        if z.testzip() is not None:
            raise CorrelationError("bad ZIP member CRC")
        preflight=json_record(z.read(EXPECTED[0]))
        report=json_record(z.read(PREFIX+"soak-audout-exact-slow-verification.json"))
        latency=json_record(z.read(PREFIX+"soak-audout-latency-verification.json"))
        correlation=json_record(z.read(PREFIX+"soak-audout-scene-correlation.json"))
        scene_report=json_record(z.read(PREFIX+"soak-verification.json"))
        slow_csv=z.read(PREFIX+"soak-audout-slow-unverified.csv")
        clock_csv=z.read(PREFIX+"soak-audout-clock-unverified.csv")
        latency_csv=z.read(PREFIX+"soak-audout-latency-unverified.csv")
        scene_csv=z.read(PREFIX+"soak-guest-optical.csv")
        receipt=z.read(PREFIX+"soak-audout-slow-export-result.txt")
    run_id=preflight.get("run_id")
    nro=preflight.get("nro_sha256")
    if (type(run_id) is not int or run_id<=0
            or type(preflight.get("run_attempt")) is not int
            or preflight["run_attempt"]<1
            or type(nro) is not str or len(nro)!=64
            or any(c not in "0123456789abcdef" for c in nro)
            or report.get("result")!="GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED"
            or report.get("stage273_result")!="GUEST_CLOCK_BOUND_SCENE_AND_AUDOUT_WINDOWS"
            or report.get("nro_sha256")!=nro
            or correlation.get("source_nro_sha256")!=nro
            or scene_report.get("guest_nro_sha256")!=nro
            or scene_report.get("result")!="TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED"
            or latency.get("result")!="GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED"
            or latency.get("sd_binding")!="ORIGINAL_SD_AND_COPY_MATCHED"
            or report.get("slow_calls_dropped")!=0
            or report.get("physical_switch_tested") is not False
            or report.get("audible_underruns_measured") is not False):
        raise CorrelationError("not a fully original-SD-audited NeXium run")
    if (report.get("slow_copy_sha256")!=digest(slow_csv)
            or report.get("guest_sd_slow_sha256")!=digest(slow_csv)
            or latency.get("original_csv_sha256")!=digest(latency_csv)
            or latency.get("copied_csv_sha256")!=digest(latency_csv)
            or scene_report.get("guest_csv_sha256")!=digest(scene_csv)
            or correlation.get("scene_csv_sha256")!=digest(scene_csv)
            or correlation.get("guest_clock_copy_sha256")!=digest(clock_csv)
            or correlation.get("latency_csv_sha256")!=digest(latency_csv)
            or report.get("slow_receipt_sha256")!=digest(receipt)):
        raise CorrelationError("archived bytes differ from verified report")
    try:
        receipt_lines=receipt.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise CorrelationError("invalid writer receipt") from exc
    if receipt_lines!=[
        "export_status=0","path_present=1",f"file_size={len(slow_csv)}"
    ]:
        raise CorrelationError("original guest writer receipt status invalid")
    origin=parse_clock(clock_csv)
    lat=parse_latency(latency_csv)
    if (origin["origin_ns"]!=report.get("audio_origin_ns")
            or origin["origin_ns"]!=correlation.get("guest_monotonic_origin_ns")
            or origin["attempts"]!=lat["attempts"]
            or origin["last_second"]!=lat["windows"]-1
            or lat["attempts"]!=report.get("audout_attempts")
            or lat["windows"]!=report.get("audout_seconds")):
        raise CorrelationError("absolute guest-clock origin not bound to audout")
    calls=parse_slow(slow_csv,origin["origin_ns"],lat)
    if (calls!=report.get("slow_calls")
            or len(calls)!=report.get("slow_calls_captured")
            or sum(c["duration_ns"]>=50_000_000 for c in calls)
               !=report.get("slow_ge50ms_count")):
        raise CorrelationError("exact calls diverge from live original-SD auditor")
    inputs=parse_scene_inputs(scene_csv)
    observations=relate(calls,inputs)
    if (observations!=report.get("scene_input_timings")
            or len(observations)!=10):
        raise CorrelationError("exact guest INPUT ordering not independently reproduced")
    near_ge50=[
        x["serial"] for x in observations
        if any(c["duration_ns"]>=50_000_000 for c in x["calls"])
    ]
    return {
        "run_id":run_id,
        "run_attempt":preflight["run_attempt"],
        "git_sha":preflight.get("git_sha"),
        "nro_sha256":nro,
        "audout_attempts":lat["attempts"],
        "audout_seconds":lat["windows"],
        "slow_40to50_calls":lat["from40to50ms_calls"],
        "slow_ge50_calls":lat["ge50ms_calls"],
        "max_call_us":lat["max_call_us"],
        "slow_records":len(calls),
        "guest_scene_inputs":len(inputs),
        "scene_serials_with_ge50_nearby":near_ge50,
        "scene_serials_with_ge40_nearby":[
            x["serial"] for x in observations if x["calls"]
        ],
        "original_sd_acceptance":"REPORTED_BY_SAME_WORKFLOW_VERIFIER",
        "slow_csv_sha256":digest(slow_csv),
    }

def compare_archives(archives: list[Path])->dict:
    if len(archives)<2 or len(archives)>12:
        raise CorrelationError("need 2-12 independent Stage274 archives")
    runs=[audit_archive(path) for path in archives]
    if len({r["run_id"] for r in runs})!=len(runs):
        raise CorrelationError("duplicate workflow run masquerading as independent")
    if len({r["nro_sha256"] for r in runs})!=1:
        raise CorrelationError("different binary NRO: not a controlled comparison")
    scene_sets=[set(r["scene_serials_with_ge50_nearby"]) for r in runs]
    common=set.intersection(*scene_sets)
    return {
        "schema":"vh-nexium-same-nro-verified-slow-runs/v1",
        "result":"MULTIRUN_EXACT_SLOW_CALLS_ARCHIVES_REVERIFIED",
        "nro_sha256":runs[0]["nro_sha256"],
        "runs":runs,
        "common_scene_serials_near_ge50":sorted(common),
        "independent_real_runs":len(runs),
        "original_transient_guest_sd_reopened_now":False,
        "real_original_sd_acceptance_source":"PRIOR_SAME_WORKFLOW_AUDIT_REPORT",
        "slow_call_scene_causality_proven":False,
        "speaker_or_hardware_observations":False,
    }

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path,action="append",required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.is_symlink() or args.output.exists():
            raise CorrelationError("will not overwrite prior comparison")
        report=compare_archives(args.archive)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({"result":report["result"],
                          "runs":report["independent_real_runs"],
                          "common_scene_serials_near_ge50":
                            report["common_scene_serials_near_ge50"],
                          "physical_switch_tested":False},sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,zipfile.BadZipFile) as exc:
        print(json.dumps({"result":"UNVERIFIED_CROSS_RUN_COMPARISON",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
