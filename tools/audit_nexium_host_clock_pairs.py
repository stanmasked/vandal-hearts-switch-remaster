#!/usr/bin/env python3
"""Stage325 independent host wall-clock/monotonic Plus-control evidence.

Only writes tiny CSV timing witnesses: no PCM samples, original game assets,
guest timestamps or measured speaker latency. The Stage304 legacy CSV schema
and strict Stage304 audit remain unchanged. Monotonic timestamps are taken
within the same Python process as each original-format wall-clock snapshot.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import time

EVENTS=("before_plus_down","after_plus_up","control_sequence_end")
LEGACY_HEADER=("event","pcm_bytes","host_epoch_ms")
DUAL_HEADER=(*LEGACY_HEADER,"host_monotonic_ns")
MAX_BYTES=4096
UINT64=(1<<64)-1
SCHEMA="vh-stage325-host-control-dual-clock-deltas/v1"


class ClockPairError(ValueError):
    pass


def _rows(raw:bytes,header:tuple[str,...],*,complete:bool)->list[dict]:
    if (not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES
            or b"\r" in raw or b"\x00" in raw or not raw.endswith(b"\n")):
        raise ClockPairError("noncanonical host control CSV")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("ascii")),strict=True)
        if reader.fieldnames!=list(header):
            raise ClockPairError("host control columns changed")
        records=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ClockPairError("invalid host control CSV encoding") from exc
    if len(records)>(len(EVENTS)) or (complete and len(records)!=len(EVENTS)):
        raise ClockPairError("unexpected host control event count")
    for index,row in enumerate(records):
        if row.get("event")!=EVENTS[index] or set(row)!=set(header):
            raise ClockPairError("host control event sequence changed")
        for name in header[1:]:
            value=row[name]
            if (not isinstance(value,str) or not value.isascii()
                    or not value.isdecimal() or
                    (len(value)>1 and value.startswith("0"))):
                raise ClockPairError("noncanonical host control integer")
            if int(value)>UINT64:
                raise ClockPairError("host control integer exceeds uint64")
        if int(row["host_epoch_ms"])==0 or (
                "host_monotonic_ns" in row and
                int(row["host_monotonic_ns"])==0):
            raise ClockPairError("zero host clock")
    return records


def _read(path:Path,header:tuple[str,...],*,complete:bool)->tuple[bytes,list[dict]]:
    if path.is_symlink() or not path.is_file():
        raise ClockPairError("missing or symlink host control source")
    raw=path.read_bytes()
    return raw,_rows(raw,header,complete=complete)


def _paired(legacy:list[dict],dual:list[dict])->None:
    if len(legacy)!=len(dual):
        raise ClockPairError("legacy/monotonic host control row count differs")
    for a,b in zip(legacy,dual):
        if any(a[k]!=b[k] for k in LEGACY_HEADER):
            raise ClockPairError("legacy and monotonic host observations diverge")


def record(label:str,pcm:Path,legacy:Path,dual:Path,
           *,wall_ns=None,mono_ns=None)->None:
    if label not in EVENTS:
        raise ClockPairError("unrecognized host control event")
    if pcm.is_symlink() or not pcm.is_file():
        raise ClockPairError("PCM source must be an existing regular file")
    if pcm==legacy or pcm==dual or legacy==dual:
        raise ClockPairError("overlapping host evidence paths")
    _,old=_read(legacy,LEGACY_HEADER,complete=False)
    _,pairs=_read(dual,DUAL_HEADER,complete=False)
    _paired(old,pairs)
    if len(old)!=EVENTS.index(label):
        raise ClockPairError("duplicate or out-of-order host control event")
    wall_ns=wall_ns or time.time_ns
    mono_ns=mono_ns or time.monotonic_ns
    # Three observations from one host process; not an atomic sampling
    # of the recorder or a guest-to-host sample clock conversion.
    size=pcm.stat().st_size
    mono_before=mono_ns()
    epoch_ms=wall_ns()//1_000_000
    monotonic=mono_ns()
    if (not all(type(v) is int and 0<=v<=UINT64
                for v in (size,mono_before,epoch_ms,monotonic))
            or epoch_ms==0 or monotonic==0 or monotonic<mono_before):
        raise ClockPairError("invalid sampled host clocks or size")
    if pairs and monotonic<=int(pairs[-1]["host_monotonic_ns"]):
        raise ClockPairError("host monotonic clock did not advance")
    legacy_row=f"{label},{size},{epoch_ms}\n".encode("ascii")
    paired_row=f"{label},{size},{epoch_ms},{monotonic}\n".encode("ascii")
    # Fail closed if interrupted between appends: subsequent record/audit
    # will reject the mismatched files; never fabricate missing rows.
    with legacy.open("ab") as f:
        f.write(legacy_row)
    with dual.open("ab") as f:
        f.write(paired_row)


def audit(legacy_bytes:bytes,dual_bytes:bytes)->dict:
    legacy=_rows(legacy_bytes,LEGACY_HEADER,complete=True)
    pair=_rows(dual_bytes,DUAL_HEADER,complete=True)
    _paired(legacy,pair)
    gaps=[]
    for before,after in zip(pair,pair[1:]):
        wall_delta=int(after["host_epoch_ms"])-int(before["host_epoch_ms"])
        mono_delta=int(after["host_monotonic_ns"])-int(before["host_monotonic_ns"])
        byte_delta=int(after["pcm_bytes"])-int(before["pcm_bytes"])
        if mono_delta<=0:
            raise ClockPairError("non-increasing host monotonic clock")
        gaps.append({
            "first_event":before["event"],
            "second_event":after["event"],
            "pcm_file_size_delta_bytes":byte_delta,
            "host_wall_delta_ms":wall_delta,
            "host_monotonic_delta_ns":mono_delta,
            "wall_backward":wall_delta<0,
            "wall_equal":wall_delta==0,
            "pcm_size_decreased":byte_delta<0,
        })
    return {
        "schema":SCHEMA,
        "result":"ORIGINAL_HOST_DUAL_CLOCK_CSVS_INDEPENDENTLY_MATCHED",
        "legacy_csv_sha256":hashlib.sha256(legacy_bytes).hexdigest(),
        "paired_clock_csv_sha256":hashlib.sha256(dual_bytes).hexdigest(),
        "adjacent_host_clock_deltas":gaps,
        "all_monotonic_intervals_positive":True,
        "wall_epoch_backwards_pair_count":sum(g["wall_backward"] for g in gaps),
        "wall_epoch_equal_pair_count":sum(g["wall_equal"] for g in gaps),
        "pcm_size_regression_pair_count":sum(g["pcm_size_decreased"] for g in gaps),
        "legacy_stage304_strict_ordering_not_relaxed":True,
        "guest_to_host_clock_conversion_verified":False,
        "audio_dropout_or_speaker_latency_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="mode",required=True)
    for name in ("record","audit"):
        cmd=sub.add_parser(name)
        cmd.add_argument("--legacy",required=True,type=Path)
        cmd.add_argument("--dual",required=True,type=Path)
        if name=="record":
            cmd.add_argument("--event",required=True,choices=EVENTS)
            cmd.add_argument("--pcm",required=True,type=Path)
        else:
            cmd.add_argument("--output",required=True,type=Path)
    options=parser.parse_args()
    try:
        if options.mode=="record":
            record(options.event,options.pcm,options.legacy,options.dual)
        else:
            if options.output.exists() or options.output.is_symlink():
                raise ClockPairError("refuse overwrite original clock evidence")
            old,_=_read(options.legacy,LEGACY_HEADER,complete=True)
            paired,_=_read(options.dual,DUAL_HEADER,complete=True)
            result=audit(old,paired)
            with options.output.open("x",encoding="utf-8") as f:
                json.dump(result,f,sort_keys=True,indent=2)
                f.write("\n")
            print(json.dumps({
                "result":result["result"],
                "wall_backwards":result["wall_epoch_backwards_pair_count"],
                "monotonic_positive":True,
                "physical_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError) as exc:
        print(json.dumps({
            "result":"HOST_DUAL_CLOCK_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
