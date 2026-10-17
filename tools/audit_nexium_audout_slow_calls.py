#!/usr/bin/env python3
"""Stage274: check exact guest >=40ms audout calls against original SD and scenes.

Absolute begin/end timestamps are software observations only, not DAC timing.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from audit_nexium_audout_queue import stable_guest_bytes,bind_export_receipt
from audit_nexium_audout_latency import parse_latency
from audit_nexium_audout_scene_correlation import (
    CorrelationError,audit as audit_clock,parse_scene_inputs,
    read_json,
)

HEADER=["scope","index","attempt","begin_ns","end_ns","duration_ns",
        "returned","total_slow_calls","dropped_slow_calls"]
CAP=128
NS_SECOND=1_000_000_000
THRESHOLD=40_000_000


def number(value: str,allow_negative_one: bool=False) -> int:
    if allow_negative_one and value=="-1":
        return -1
    if not value or not value.isascii() or not value.isdecimal() or (
            len(value)>1 and value[0]=="0"):
        raise CorrelationError("noncanonical slow-call integer")
    return int(value)


def parse_slow(raw: bytes, origin: int, latency: dict) -> list[dict]:
    if (len(raw)>64_000 or b"\r" in raw or not raw.endswith(b"\n")):
        raise CorrelationError("oversized or noncanonical slow-call CSV")
    try:
        rows=list(csv.reader(io.StringIO(raw.decode("ascii"),newline=""),
                             strict=True))
    except (csv.Error,UnicodeError) as exc:
        raise CorrelationError("malformed slow-call CSV") from exc
    if len(rows)<2 or rows[0]!=HEADER:
        raise CorrelationError("unexpected slow-call CSV columns")
    if any(len(r)!=len(HEADER) for r in rows[1:]):
        raise CorrelationError("wrong slow-call column count")
    summary=rows[1]
    if (summary[:7]!=["TOTAL","-1","0","0","0","0","0"]):
        raise CorrelationError("invalid total slow-call row")
    declared=number(summary[7])
    dropped=number(summary[8])
    if dropped:
        raise CorrelationError("bounded slow-call capture overflow")
    if declared!=len(rows)-2 or declared>CAP:
        raise CorrelationError("slow-call total does not match recorded rows")
    expected=latency["from40to50ms_calls"]+latency["ge50ms_calls"]
    if declared!=expected:
        raise CorrelationError("slow calls disagree with independent histogram")
    if origin<=0 or latency["windows"]<50:
        raise CorrelationError("missing guest clock origin or sustained capture")
    bucket_expected=latency["per_second_call_bands"]
    actual=[{"ge40":0,"ge50":0,"max_duration_ns":0}
            for _ in range(len(bucket_expected))]
    # A slow event's attempt index must belong to its particular
    # second's complete sequential call range, not just the full session.
    prior_attempts=[]
    cumulative=0
    for window in bucket_expected:
        prior_attempts.append(cumulative)
        cumulative+=window["attempts"]
    if cumulative!=latency["attempts"]:
        raise CorrelationError("bad latency window attempt accounting")
    calls=[]
    last_attempt=0
    last_begin=0
    for index,fields in enumerate(rows[2:]):
        if fields[0]!="CALL" or number(fields[1])!=index:
            raise CorrelationError("slow call rows duplicated or misordered")
        attempt,begin,end,duration,returned=(
            number(fields[pos]) for pos in (2,3,4,5,6))
        if (fields[7:]!=["0","0"] or attempt<=last_attempt
                or attempt>latency["attempts"] or begin<=last_begin
                or begin<origin or end<begin or end-begin!=duration
                or duration<THRESHOLD or returned not in (0,1)):
            raise CorrelationError("slow-call index/timestamp/duration invalid")
        second=(begin-origin)//NS_SECOND
        if second>=len(bucket_expected):
            raise CorrelationError("slow call begins outside audout windows")
        if bucket_expected[second]["second"]!=second:
            raise CorrelationError("incorrect audout bucket numbering")
        if not (prior_attempts[second] < attempt <=
                prior_attempts[second]+bucket_expected[second]["attempts"]):
            raise CorrelationError("slow-call attempt index outside timestamped second")
        if not returned and latency["failed_attempts"]==0:
            raise CorrelationError("reported failed slow call contradicts zero failures")
        group=actual[second]
        group["ge40"]+=1
        group["ge50"]+=duration>=50_000_000
        group["max_duration_ns"]=max(group["max_duration_ns"],duration)
        calls.append({
            "attempt":attempt,"begin_ns":begin,"end_ns":end,
            "duration_ns":duration,"returned":bool(returned),
            "audio_second":second,
        })
        last_begin,last_attempt=begin,attempt
    for bucket,check in zip(bucket_expected,actual):
        if (check["ge40"] != bucket["from40to50ms"]+bucket["ge50ms"]
                or check["ge50"]!=bucket["ge50ms"]):
            raise CorrelationError("slow-call per-second histogram mismatch")
        if check["ge40"] and (
                check["max_duration_ns"]//1000!=bucket["max_call_us"]):
            raise CorrelationError("slow timestamp misses second-window maximum")
        if not check["ge40"] and bucket["max_call_us"]>=40_000:
            raise CorrelationError("slow-call maximum missing from detailed capture")
    if calls:
        if max(c["duration_ns"] for c in calls)//1000!=latency["max_call_us"]:
            raise CorrelationError("full-session slow maximum differs")
    elif latency["max_call_us"]>=40_000:
        raise CorrelationError("missing slow calls with large global maximum")
    return calls


def relate(calls: list[dict], inputs: list[dict]) -> list[dict]:
    if len(inputs)!=10:
        raise CorrelationError("expected exactly ten guest INPUT events")
    observations=[]
    for event in inputs:
        stamp=event["timestamp_ns"]
        near=[c for c in calls if abs(c["begin_ns"]-stamp)<=500_000_000]
        before=sum(c["end_ns"]<=stamp for c in near)
        after=sum(c["begin_ns"]>=stamp for c in near)
        overlap=sum(c["begin_ns"]<stamp<c["end_ns"] for c in near)
        if before+after+overlap!=len(near):
            raise CorrelationError("slow call temporal order ambiguous")
        observations.append({
            "serial":event["serial"],"scene":event["scene"],
            "input_monotonic_ns":stamp,
            "slow_calls_start_within_500ms":len(near),
            "fully_ended_before_input":before,
            "began_after_input":after,
            "straddled_input":overlap,
            "calls":[{
                "attempt":c["attempt"],"begin_ns":c["begin_ns"],
                "end_ns":c["end_ns"],"duration_ns":c["duration_ns"],
                "begin_minus_input_ns":c["begin_ns"]-stamp,
                "end_minus_input_ns":c["end_ns"]-stamp,
                "relation":(
                    "END_BEFORE_INPUT" if c["end_ns"]<=stamp
                    else "BEGIN_AFTER_INPUT" if c["begin_ns"]>=stamp
                    else "CALL_OVERLAPS_INPUT"
                ),
            } for c in near],
        })
    return observations


def audit(*,slow_csv:Path,slow_locations:Path,slow_receipt:Path,
          clock_csv:Path,clock_locations:Path,clock_receipt:Path,
          latency_csv:Path,latency_verification:Path,scene_csv:Path,
          scene_verification:Path,queue_verification:Path,
          previous_correlation:Path,sd_root:Path)->dict:
    previous=audit_clock(
        clock_csv=clock_csv,clock_locations=clock_locations,
        clock_receipt=clock_receipt,latency_csv=latency_csv,
        latency_verification=latency_verification,scene_csv=scene_csv,
        scene_verification=scene_verification,
        queue_verification=queue_verification,sd_root=sd_root)
    earlier=read_json(previous_correlation)
    # Exactly the same source data and result as the original stage-273 audit.
    if earlier!=previous:
        raise CorrelationError("stored stage273 correlation differs from reaudited original SD")
    directory=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if sd_root.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise CorrelationError("missing original isolated guest SD directory")
    originals=list(directory.glob("audio-audout-slow-*.csv"))
    if len(originals)!=1 or originals[0].is_symlink():
        raise CorrelationError("expected single regular guest slow-call file")
    if slow_locations.is_symlink() or (
            slow_locations.read_text(encoding="utf-8").splitlines()
            != [str(originals[0])]):
        raise CorrelationError("slow-call file location not bound")
    if slow_csv.is_symlink() or slow_csv.resolve()==originals[0].resolve():
        raise CorrelationError("slow call copy cannot alias original")
    original=stable_guest_bytes(originals[0])
    copy=stable_guest_bytes(slow_csv)
    if original!=copy or stable_guest_bytes(originals[0])!=copy:
        raise CorrelationError("original and copied slow-call bytes differ")
    receipt=bind_export_receipt(slow_receipt,len(copy))
    latency=parse_latency(stable_guest_bytes(latency_csv))
    if (latency["attempts"]!=previous["audout_attempts"]
            or latency["windows"]!=previous["audout_windows"]):
        raise CorrelationError("slow audit not bound to verified audio session")
    calls=parse_slow(copy,previous["guest_monotonic_origin_ns"],latency)
    inputs=parse_scene_inputs(stable_guest_bytes(scene_csv))
    observations=relate(calls,inputs)
    return {
        "schema":"vh-nexium-audout-exact-slow-call/v1",
        "result":"GUEST_SD_EXACT_AUDOUT_SLOW_CALLS_VERIFIED",
        "nro_sha256":previous["source_nro_sha256"],
        "stage273_result":previous["result"],
        "audio_origin_ns":previous["guest_monotonic_origin_ns"],
        "audout_attempts":previous["audout_attempts"],
        "audout_seconds":previous["audout_windows"],
        "slow_call_threshold_ns":THRESHOLD,
        "slow_calls_captured":len(calls),
        "slow_calls_dropped":0,
        "slow_ge50ms_count":sum(c["duration_ns"]>=50_000_000 for c in calls),
        "slow_calls":calls,
        "scene_input_timings":observations,
        "guest_sd_slow_sha256":hashlib.sha256(original).hexdigest(),
        "slow_copy_sha256":hashlib.sha256(copy).hexdigest(),
        "slow_receipt_sha256":receipt["guest_export_receipt_sha256"],
        "clock_binds_to_input":True,
        "exact_call_order_relative_to_guest_input_known":True,
        "scene_to_slow_call_causality_proven":False,
        "guest_to_host_pcm_clock_alignment_proven":False,
        "audible_underruns_measured":False,
        "physical_switch_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("slow-csv","slow-locations","slow-receipt",
                 "clock-csv","clock-locations","clock-receipt",
                 "latency-csv","latency-verification",
                 "scene-csv","scene-verification","queue-verification",
                 "previous-correlation","sd-root","output"):
        p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise CorrelationError("refuse overwrite of earlier slow-call audit")
        report=audit(
            slow_csv=a.slow_csv,slow_locations=a.slow_locations,
            slow_receipt=a.slow_receipt,
            clock_csv=a.clock_csv,clock_locations=a.clock_locations,
            clock_receipt=a.clock_receipt,latency_csv=a.latency_csv,
            latency_verification=a.latency_verification,
            scene_csv=a.scene_csv,scene_verification=a.scene_verification,
            queue_verification=a.queue_verification,
            previous_correlation=a.previous_correlation,sd_root=a.sd_root)
        a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "slow_calls_captured":report["slow_calls_captured"],
            "slow_ge50ms_count":report["slow_ge50ms_count"],
            "slow_calls_dropped":report["slow_calls_dropped"],
            "hardware_tested":False},sort_keys=True))
        return 0
    except (CorrelationError,OSError,ValueError,UnicodeError,csv.Error) as exc:
        print(json.dumps({"result":"GUEST_EXACT_SLOW_CALLS_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
