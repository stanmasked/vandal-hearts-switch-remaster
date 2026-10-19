#!/usr/bin/env python3
"""Stage362: independent host recorder-stop monotonic/wall-clock companion audit.

Do not rescue the strict Stage303 original legacy host CSV. A backward wall
epoch is recorded as a backward wall epoch, even if CLOCK_MONOTONIC advanced.
Recorder sizes are buffered host-file snapshots, not sound-device playback.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

LEGACY=("event","pcm_bytes","host_epoch_ms","signal_success")
PAIRED=("event","pcm_bytes","host_epoch_ms","host_monotonic_ns","signal_success")
EVENTS=("before_sigint","after_wait")
UINT64=(1<<64)-1
RESULT="STAGE362_ORIGINAL_HOST_RECORDER_STOP_DUAL_CLOCKS_RECONCILED"
SCHEMA="vh-stage362-recorder-stop-dual-host-clocks/v1"

class RecorderClocksError(ValueError):
    pass

def parse(raw:bytes, columns:tuple[str,...])->list[dict]:
    if (not isinstance(raw,bytes) or not 0<len(raw)<=2048
        or b"\r" in raw or b"\x00" in raw or not raw.endswith(b"\n")):
        raise RecorderClocksError("host stop source bytes not canonical")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("ascii"),newline=""),strict=True)
        if reader.fieldnames!=list(columns):
            raise RecorderClocksError("host stop columns changed")
        rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise RecorderClocksError("host stop CSV invalid") from exc
    if len(rows)!=len(EVENTS):
        raise RecorderClocksError("host stop event count changed")
    normalized=[]
    for index,row in enumerate(rows):
        if set(row)!=set(columns) or row.get("event")!=EVENTS[index]:
            raise RecorderClocksError("host stop event order or columns invalid")
        values={"event":row["event"]}
        for col in columns[1:]:
            val=row.get(col)
            if (not isinstance(val,str) or not val.isascii()
                or not val.isdecimal() or (len(val)>1 and val[0]=="0")):
                raise RecorderClocksError("host stop integer noncanonical")
            number=int(val)
            if number>UINT64 or (col in ("host_epoch_ms","host_monotonic_ns") and number==0):
                raise RecorderClocksError("host stop clock invalid")
            values[col]=number
        if values["signal_success"] not in (0,1):
            raise RecorderClocksError("invalid host SIGINT success flag")
        normalized.append(values)
    return normalized

def audit(legacy:bytes,paired:bytes)->dict:
    old=parse(legacy,LEGACY)
    dual=parse(paired,PAIRED)
    for a,b in zip(old,dual):
        if any(a[col]!=b[col] for col in LEGACY):
            raise RecorderClocksError("legacy host fields differ from paired original")
    before,after=dual
    wall_delta=after["host_epoch_ms"]-before["host_epoch_ms"]
    monotonic_delta=after["host_monotonic_ns"]-before["host_monotonic_ns"]
    byte_delta=after["pcm_bytes"]-before["pcm_bytes"]
    if monotonic_delta<=0:
        raise RecorderClocksError("host monotonic clock did not increase")
    strict_chronology=(wall_delta>=0 and byte_delta>=0
                       and all(r["signal_success"]==1 for r in dual))
    return {
        "schema":SCHEMA,"result":RESULT,
        "legacy_stop_csv_sha256":hashlib.sha256(legacy).hexdigest(),
        "monotonic_companion_csv_sha256":hashlib.sha256(paired).hexdigest(),
        "events":list(EVENTS),
        "host_wall_elapsed_ms":wall_delta,
        "host_monotonic_elapsed_ns":monotonic_delta,
        "pcm_file_size_delta_bytes":byte_delta,
        "host_wall_clock_moved_backwards":wall_delta<0,
        "host_monotonic_clock_increased":True,
        "strict_stage303_chronology_compatible":strict_chronology,
        "strict_stage303_original_csv_not_modified":True,
        "strict_stage303_source_audit_not_waived":True,
        "wall_and_monotonic_samples_are_host_only":True,
        "clock_delta_does_not_prove_guest_shutdown":True,
        "real_DAC_or_speaker_audio_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def load_regular(path:Path)->bytes:
    if not path.is_file() or any(p.is_symlink() for p in (path,*path.parents)):
        raise RecorderClocksError("host clock input missing or linked")
    return path.read_bytes()

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy",required=True,type=Path)
    parser.add_argument("--paired",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise RecorderClocksError("refuse to replace report")
        if args.legacy==args.paired or args.output in (args.legacy,args.paired):
            raise RecorderClocksError("source/output paths overlap")
        result=audit(load_regular(args.legacy),load_regular(args.paired))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if any(p.is_symlink() for p in (args.output,*args.output.parents)):
            raise RecorderClocksError("output parent linked")
        with args.output.open("x",encoding="utf-8") as out:
            json.dump(result,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":RESULT,
            "wall_delta_ms":result["host_wall_elapsed_ms"],
            "monotonic_delta_ns":result["host_monotonic_elapsed_ns"],
            "strict_stage303_chronology_compatible":result["strict_stage303_chronology_compatible"],
            "physical_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError) as err:
        print(json.dumps({
            "result":"STAGE362_HOST_RECORDER_CLOCKS_NOT_VERIFIED",
            "error_kind":type(err).__name__,
            "original_Stage303_waived":False,
            "physical_audio_tested":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
