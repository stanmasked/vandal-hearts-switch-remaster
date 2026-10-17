#!/usr/bin/env python3
"""Stage 273: bind observed guest scene INPUT times to audout SECOND windows.

The same Nintendo Switch guest monotonic nanosecond counter is used in both
producers. An event falling within one second of a slow-call window is only
temporal co-occurrence, NOT a sample-accurate association or causal link.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from audit_nexium_audout_queue import stable_guest_bytes, bind_export_receipt
from audit_nexium_audout_latency import parse_latency


class CorrelationError(ValueError):
    pass


CLOCK_HEADER = ("schema,origin_ns,attempts,last_second,clock_errors\n")
CLOCK_SCHEMA = "vh-audout-guest-clock-origin/v1"
SCENE_HEADER = "index,event,serial,scene,monotonic_ns,dropped_total"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path) -> dict:
    raw = stable_guest_bytes(path)
    if len(raw) > 128_000:
        raise CorrelationError("oversized audit JSON")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CorrelationError("duplicate JSON property")
            result[key] = value
        return result
    try:
        document = json.loads(raw.decode("ascii"), object_pairs_hook=unique)
    except (ValueError,UnicodeError) as exc:
        raise CorrelationError("invalid audit JSON") from exc
    if not isinstance(document, dict):
        raise CorrelationError("invalid audit JSON root")
    return document


def integer(cell: str, *, allow_zero: bool = True) -> int:
    if (not cell or not cell.isascii() or not cell.isdecimal()
            or (len(cell)>1 and cell[0]=="0")):
        raise CorrelationError("noncanonical unsigned integer")
    number=int(cell)
    if not allow_zero and number==0:
        raise CorrelationError("zero where positive integer required")
    return number


def parse_clock(raw: bytes) -> dict:
    if len(raw)>1024 or not raw.startswith(CLOCK_HEADER.encode("ascii")):
        raise CorrelationError("invalid guest clock anchor header/size")
    try:
        lines=raw.decode("ascii").splitlines(keepends=True)
    except UnicodeError as exc:
        raise CorrelationError("invalid clock anchor encoding") from exc
    if len(lines)!=2 or not lines[1].endswith("\n") or "\r" in lines[1]:
        raise CorrelationError("clock anchor must have exactly one LF row")
    fields=lines[1][:-1].split(",")
    if len(fields)!=5 or fields[0]!=CLOCK_SCHEMA:
        raise CorrelationError("unexpected guest clock origin schema")
    values=[integer(x,allow_zero=(i==2 or i==3))
            for i,x in enumerate(fields[1:])]
    origin,attempts,last_second,clock_errors=values
    if clock_errors or attempts < 100 or last_second >= 128:
        raise CorrelationError("invalid session clock or missed timing windows")
    return {"origin_ns":origin,"attempts":attempts,
            "last_second":last_second,"clock_errors":clock_errors}


def parse_scene_inputs(raw: bytes) -> list[dict]:
    if not raw.endswith(b"\n") or b"\r" in raw or len(raw)>16_384:
        raise CorrelationError("scene event CSV malformed or oversized")
    try:
        rows=list(csv.DictReader(
            io.StringIO(raw.decode("ascii"),newline=""),strict=True))
    except (csv.Error,UnicodeError) as exc:
        raise CorrelationError("invalid scene event CSV") from exc
    if not rows or list(rows[0])!=SCENE_HEADER.split(",") or len(rows)!=53:
        raise CorrelationError("unexpected scene trace header or event count")
    before=-1
    inputs=[]
    for index,row in enumerate(rows):
        if set(row)!=set(SCENE_HEADER.split(",")):
            raise CorrelationError("unexpected scene trace fields")
        if integer(row["index"])!=index:
            raise CorrelationError("noncanonical scene trace index")
        stamp=integer(row["monotonic_ns"],allow_zero=False)
        serial=integer(row["serial"])
        scene=integer(row["scene"])
        if stamp<=before or scene not in (1,2):
            raise CorrelationError("scene clock not monotonic or scene invalid")
        before=stamp
        if integer(row["dropped_total"])!=0:
            raise CorrelationError("dropped scene trace events")
        if row["event"]=="INPUT":
            if serial!=len(inputs)+1 or scene!=(2 if serial%2 else 1):
                raise CorrelationError("scene INPUT serial/order mismatch")
            inputs.append({"serial":serial,"scene":scene,"timestamp_ns":stamp})
        elif row["event"] not in (
                "POST","ACCEPT","SUBMIT_CALL","RELEASE_RETURN"):
            raise CorrelationError("unrecognized scene event")
    if len(inputs)!=10:
        raise CorrelationError("expected ten guest INPUT events")
    return inputs


def join(guest_origin: dict, scene_csv: bytes,
         latency_raw: bytes) -> dict:
    """Pure analysis: deterministic second-window lookup, no I/O."""
    source=parse_latency(latency_raw)
    inputs=parse_scene_inputs(scene_csv)
    if (guest_origin["attempts"]!=source["attempts"]
            or guest_origin["last_second"]!=source["windows"]-1):
        raise CorrelationError("guest origin and audout windows disagree")
    windows=source["per_second_call_bands"]
    if len(windows)!=source["windows"]:
        raise CorrelationError("invalid latency bucket collection")
    result=[]
    for event in inputs:
        offset_ns=event["timestamp_ns"]-guest_origin["origin_ns"]
        if offset_ns<0:
            raise CorrelationError("scene input happened before first audio call")
        second=offset_ns//1_000_000_000
        if second>=len(windows):
            raise CorrelationError("scene input beyond measured audio windows")
        hit=windows[second]
        if hit["second"]!=second:
            raise CorrelationError("latency window second number mismatch")
        neighbours=[
            windows[i] for i in range(max(0,second-1),
                                     min(len(windows),second+2))
        ]
        result.append({
            "serial":event["serial"],
            "scene":event["scene"],
            "guest_input_ns":event["timestamp_ns"],
            "relative_audio_second":int(second),
            "position_in_second_ms":round(
                (offset_ns%1_000_000_000)/1_000_000,3),
            "same_second_attempts":hit["attempts"],
            "same_second_ge40ms_calls":hit["from40to50ms"]+hit["ge50ms"],
            "same_second_ge50ms_calls":hit["ge50ms"],
            "adjacent_one_second_window_indices": [
                w["second"] for w in neighbours],
            "adjacent_ge50ms_call_count":sum(w["ge50ms"] for w in neighbours),
            "association":"GUEST_SECOND_COOCCURRENCE_ONLY",
        })
    return {
        "schema":"vh-nexium-audout-scene-correlation/v1",
        "result":"GUEST_CLOCK_BOUND_SCENE_AND_AUDOUT_WINDOWS",
        "guest_monotonic_origin_ns":guest_origin["origin_ns"],
        "audout_windows":source["windows"],
        "audout_attempts":source["attempts"],
        "guest_scene_input_count":len(inputs),
        "all_guest_ge50ms_calls":source["ge50ms_calls"],
        "input_seconds_with_ge50ms_calls":sum(
            row["same_second_ge50ms_calls"]>0 for row in result),
        "scene_inputs":result,
        "guest_clock_alignment_proven":True,
        "individual_slow_call_start_time_known":False,
        "same_second_does_not_prove_scene_causality":True,
        "host_pcm_clock_alignment_proven":False,
        "audible_underruns_measured":False,
        "hardware_tested":False,
    }


def audit(*, clock_csv: Path, clock_locations: Path, clock_receipt: Path,
          latency_csv: Path, latency_verification: Path,
          scene_csv: Path, scene_verification: Path,
          queue_verification: Path, sd_root: Path) -> dict:
    folder=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if sd_root.is_symlink() or folder.is_symlink() or not folder.is_dir():
        raise CorrelationError("missing or symlinked guest SD directory")
    original=list(folder.glob("audio-audout-clock-*.csv"))
    if len(original)!=1 or original[0].is_symlink():
        raise CorrelationError("expected one regular original guest clock file")
    if clock_locations.is_symlink() or clock_locations.read_text(
            encoding="utf-8").splitlines()!=[str(original[0])]:
        raise CorrelationError("guest clock original path binding differs")
    if clock_csv.is_symlink() or clock_csv.resolve()==original[0].resolve():
        raise CorrelationError("missing independent guest clock copy")
    src=stable_guest_bytes(original[0])
    duplicate=stable_guest_bytes(clock_csv)
    if src!=duplicate or stable_guest_bytes(original[0])!=duplicate:
        raise CorrelationError("original and copied guest clock bytes differ")
    bind_export_receipt(clock_receipt,len(duplicate))
    anchor=parse_clock(duplicate)
    scene=read_json(scene_verification)
    latency=read_json(latency_verification)
    queue=read_json(queue_verification)
    scene_raw=stable_guest_bytes(scene_csv)
    guest_scenes=list(folder.glob("audio-scene-trace-*.csv"))
    if len(guest_scenes)!=1 or stable_guest_bytes(guest_scenes[0])!=scene_raw:
        raise CorrelationError("scene original and optical/SD audit copy differ")
    latency_raw=stable_guest_bytes(latency_csv)
    if (scene.get("result")!="TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED"
            or scene.get("guest_csv_sha256")!=digest(scene_raw)
            or scene.get("guest_sd_csv_sha256")!=digest(scene_raw)
            or scene.get("guest_event_rows")!=53
            or scene.get("hardware_status")!="HARDWARE NOT TESTED"
            or latency.get("result")!="GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED"
            or latency.get("sd_binding")!="ORIGINAL_SD_AND_COPY_MATCHED"
            or latency.get("copied_csv_sha256")!=digest(latency_raw)
            or latency.get("attempts")!=anchor["attempts"]
            or queue.get("result")!="GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT"
            or queue.get("attempts")!=anchor["attempts"]
            or queue.get("windows")!=anchor["last_second"]+1
            or latency.get("queue_stage269_csv_sha256")!=queue.get("sd_copy_sha256")):
        raise CorrelationError("verified scene/latency/queue evidence does not bind")
    report=join(anchor,scene_raw,latency_raw)
    report["guest_clock_original_csv_sha256"]=digest(src)
    report["guest_clock_copy_sha256"]=digest(duplicate)
    report["guest_clock_receipt_sha256"]=digest(stable_guest_bytes(clock_receipt))
    report["scene_csv_sha256"]=digest(scene_raw)
    report["latency_csv_sha256"]=digest(latency_raw)
    report["source_nro_sha256"]=scene["guest_nro_sha256"]
    report["original_guest_sd_reopened"]=True
    return report


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in (
        "clock-csv","clock-locations","clock-receipt",
        "latency-csv","latency-verification",
        "scene-csv","scene-verification",
        "queue-verification","sd-root","output"
    ):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.exists() or args.output.is_symlink():
            raise CorrelationError("refuse overwrite prior guest temporal audit")
        report=audit(clock_csv=args.clock_csv,clock_locations=args.clock_locations,
                     clock_receipt=args.clock_receipt,
                     latency_csv=args.latency_csv,
                     latency_verification=args.latency_verification,
                     scene_csv=args.scene_csv,scene_verification=args.scene_verification,
                     queue_verification=args.queue_verification,sd_root=args.sd_root)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "audout_attempts":report["audout_attempts"],
            "guest_scene_input_count":report["guest_scene_input_count"],
            "input_seconds_with_ge50ms_calls":
                report["input_seconds_with_ge50ms_calls"],
            "physical_switch_tested":False
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,csv.Error) as exc:
        print(json.dumps({"result":"GUEST_CLOCK_SCENE_CORRELATION_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
