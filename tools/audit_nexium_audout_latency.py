#!/usr/bin/env python3
"""Stage 272: independently verify guest per-CALL latency bands from original SD.

Each band counts individually measured blocking audoutPlayBuffer calls.
No audible-output, DAC starvation or actual console timing is measured.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

from audit_nexium_audout_queue import (
    stable_guest_bytes, bind_export_receipt, parse_telemetry,
    HEADER as QUEUE_HEADER,
)

HEADER = [
    "scope", "second", "attempts", "lt25ms", "from25to40ms",
    "from40to50ms", "ge50ms", "failures", "max_call_us",
    "overwritten_windows", "clock_errors",
]
BANDS = HEADER[3:7]

def parse_latency(raw: bytes) -> dict:
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError("latency CSV has noncanonical newline")
    try:
        rows=list(csv.reader(io.StringIO(raw.decode("ascii"),newline=""),
                             strict=True))
    except (UnicodeError,csv.Error) as exc:
        raise ValueError("malformed latency CSV") from exc
    if not rows or rows[0]!=HEADER or len(rows)<52:
        raise ValueError("invalid latency histogram header or window count")
    decoded=[]
    for fields in rows[1:]:
        if len(fields)!=len(HEADER) or fields[0] not in ("TOTAL","SECOND"):
            raise ValueError("unexpected latency histogram row")
        row={"scope":fields[0]}
        for key,value in zip(HEADER[1:],fields[1:]):
            if key=="second" and fields[0]=="TOTAL" and value=="-1":
                row[key]=-1
                continue
            if not value.isascii() or not value.isdecimal() or (
                len(value)>1 and value[0]=="0"):
                raise ValueError("invalid or noncanonical histogram integer")
            row[key]=int(value)
        decoded.append(row)
    total,*seconds=decoded
    if total["scope"]!="TOTAL" or total["second"]!=-1:
        raise ValueError("missing unique latency TOTAL")
    if (len(seconds)<50 or
        any(r["scope"]!="SECOND" or r["second"]!=index
            for index,r in enumerate(seconds))):
        raise ValueError("latency seconds missing, repeated or reordered")
    if total["overwritten_windows"] or total["clock_errors"]:
        raise ValueError("guest histogram lost windows or has clock errors")
    if total["attempts"]<100 or total["attempts"] != sum(
            total[name] for name in BANDS):
        raise ValueError("whole-run per-call band conservation broken")
    for row in decoded:
        if row["attempts"]!=sum(row[key] for key in BANDS):
            raise ValueError("per-call band count does not match attempts")
        if row["failures"]>row["attempts"]:
            raise ValueError("invalid failures")
        if row["attempts"]==0 or (row["max_call_us"]==0 and
                (row["from25to40ms"] or row["from40to50ms"] or row["ge50ms"])):
            raise ValueError("unmeasured or inconsistent latency maximum")
        if row["scope"]=="SECOND" and (
                row["overwritten_windows"] or row["clock_errors"]):
            raise ValueError("invalid per-second histogram metadata")
        # Nanoseconds are used to classify; CSV duration truncates to us.
        # 24.999999 ms rounds down to 24999us.
        if row["ge50ms"] and row["max_call_us"]<50_000:
            raise ValueError(">=50ms call without matching maximum")
        if row["from40to50ms"] and row["max_call_us"]<40_000:
            raise ValueError(">=40ms call without matching maximum")
        if row["from25to40ms"] and row["max_call_us"]<25_000:
            raise ValueError(">=25ms call without matching maximum")
    for key in ["attempts",*BANDS,"failures"]:
        if sum(r[key] for r in seconds)!=total[key]:
            raise ValueError("latency total differs from per-second windows: "+key)
    if max(r["max_call_us"] for r in seconds)!=total["max_call_us"]:
        raise ValueError("whole-run latency maximum differs")
    return {
        "schema":"vh-nexium-audout-call-bands/v1",
        "result":"GUEST_AUDOUT_PER_CALL_BANDS_VERIFIED",
        "windows":len(seconds),
        "attempts":total["attempts"],
        "returned":total["attempts"]-total["failures"],
        "failed_attempts":total["failures"],
        "lt25ms_calls":total["lt25ms"],
        "from25to40ms_calls":total["from25to40ms"],
        "from40to50ms_calls":total["from40to50ms"],
        "ge50ms_calls":total["ge50ms"],
        "max_call_us":total["max_call_us"],
        "per_second_call_bands":[
            {"second":r["second"],"attempts":r["attempts"],
             "lt25ms":r["lt25ms"],"from25to40ms":r["from25to40ms"],
             "from40to50ms":r["from40to50ms"],"ge50ms":r["ge50ms"],
             "failures":r["failures"],"max_call_us":r["max_call_us"]} for r in seconds
        ],
        "measures_every_individual_blocking_call":True,
        "physical_switch_tested":False,
        "audible_underruns_measured":False,
    }

def bind_guest_latency(source: Path, locations: Path,
                       receipt: Path, sd_root: Path, queue_report: Path,
                       queue_csv: Path) -> dict:
    if sd_root.is_symlink() or not sd_root.is_dir():
        raise ValueError("missing or symlinked isolated SD root")
    directory=sd_root/"sdmc"/"switch"/"vandal-hearts-remake"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("missing or symlinked guest SD folder")
    originals=sorted(directory.glob("audio-audout-latency-*.csv"))
    if len(originals)!=1:
        raise ValueError("expected exactly one guest original latency CSV")
    path=originals[0]
    if path.is_symlink() or source.is_symlink() or locations.is_symlink():
        raise ValueError("symlinked latency evidence rejected")
    if locations.read_text(encoding="utf-8").splitlines()!=[str(path)]:
        raise ValueError("latency original location list differs")
    if not source.is_file() or source.resolve()==path.resolve():
        raise ValueError("latency copy is not an independent file")
    first=stable_guest_bytes(path)
    copied=stable_guest_bytes(source)
    if first!=copied or stable_guest_bytes(path)!=copied:
        raise ValueError("guest latency original and copy differ")
    report=parse_latency(copied)
    receipt_report=bind_export_receipt(receipt,len(copied))
    try:
        old=json.loads(stable_guest_bytes(queue_report).decode("ascii"))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError("invalid stage-269 queue report") from exc
    if (old.get("result")!="GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT"
            or old.get("sd_binding")!="GUEST_ORIGINAL_AND_COPY_BYTE_IDENTICAL"
            or old.get("attempts")!=report["attempts"]
            or old.get("releases")!=report["returned"]
            or old.get("failed_attempts")!=report["failed_attempts"]
            or old.get("windows")!=report["windows"]
            or old.get("max_call_us")!=report["max_call_us"]):
        raise ValueError("latency histogram differs from existing guest queue audit")
    # Cross-check EVERY second against the separately verified queue CSV,
    # not only the session totals. Maxima share the same nanosecond timer
    # and must be exactly equal after truncation to microseconds.
    queue_bytes=stable_guest_bytes(queue_csv)
    queue_parsed=parse_telemetry(queue_bytes)
    queue_digest=hashlib.sha256(queue_bytes).hexdigest()
    if (old.get("sd_copy_sha256")!=queue_digest
            or old.get("sd_original_sha256")!=queue_digest
            or queue_parsed["attempts"]!=report["attempts"]
            or queue_parsed["windows"]!=report["windows"]):
        raise ValueError("stage-269 copied CSV is not the audited queue evidence")
    queue_rows=list(csv.DictReader(
        io.StringIO(queue_bytes.decode("ascii"),newline=""),strict=True))
    if not queue_rows or list(queue_rows[0])!=QUEUE_HEADER:
        raise ValueError("stage-269 queue CSV columns differ")
    windows=[row for row in queue_rows if row["scope"]=="SECOND"]
    if len(windows)!=report["windows"]:
        raise ValueError("stage-269 and latency second counts differ")
    for queue_window,latency_window in zip(windows,report["per_second_call_bands"]):
        if (int(queue_window["second"])!=latency_window["second"]
                or int(queue_window["attempts"])!=latency_window["attempts"]
                or int(queue_window["failures"])!=latency_window["failures"]
                or int(queue_window["max_call_us"])!=latency_window["max_call_us"]):
            raise ValueError("stage-269 and latency per-second timestamps/counts differ")
    report.update(receipt_report)
    report["guest_sd_original_name"]=path.name
    report["sd_binding"]="ORIGINAL_SD_AND_COPY_MATCHED"
    report["original_csv_sha256"]=hashlib.sha256(first).hexdigest()
    report["copied_csv_sha256"]=hashlib.sha256(copied).hexdigest()
    report["csv_bytes"]=len(copied)
    report["queue_stage269_csv_sha256"]=old["sd_original_sha256"]
    return report

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","locations","receipt","sd-root","queue-verification",
                 "output","queue-csv"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    try:
        if args.output.is_symlink() or args.output.exists():
            raise ValueError("refuse overwrite of prior audout latency verification")
        report=bind_guest_latency(args.source,args.locations,args.receipt,
                                  args.sd_root,args.queue_verification,args.queue_csv)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({k:report[k] for k in (
            "result","windows","attempts","ge50ms_calls",
            "max_call_us","physical_switch_tested")},sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,csv.Error) as exc:
        print(json.dumps({"result":"GUEST_AUDOUT_LATENCY_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
