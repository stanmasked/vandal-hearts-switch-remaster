#!/usr/bin/env python3
"""Stage360 independent original guest pre-submit-probe AGE source audit.

Last periodic normal-PlayBuffer pre-submit query is NOT queue-at-exit. Reuse
original Stage313 and Stage351 receipts, without fabricated queue depth,
kernel event time or physical speaker output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError
from audit_nexium_guest_tail_reason_stage351 import (
    SCHEMA as REASON_SCHEMA,VERIFIED as REASON_VERIFIED,
)
from audit_nexium_guest_last_buffer_return import (
    SCHEMA as TAIL_SCHEMA,COMPLETE as TAIL_VERIFIED,
)
SOURCE="audio-exit-probe-context-000.csv"
SCHEMA="vh-stage360-original-guest-last-pre-submit-probe-context/v1"
VERIFIED="ORIGINAL_NEIXUM_EXIT_PRE_SUBMIT_PROBE_AGE_SOURCE_VERIFIED"
FIELDS=(
    "software_exit_probe_context_only","tail_observed",
    "tail_begin_guest_ns","tail_end_guest_ns","tail_elapsed_ns",
    "normal_submit_attempts_at_tail","last_pre_submit_probe_observed",
    "last_pre_submit_probe_attempt","last_pre_submit_probe_queue_status",
    "last_pre_submit_probe_queue_count","last_pre_submit_probe_age_ns",
    "last_pre_submit_probe_dropped_count","stage351_tail_reason_code",
)
def regular(path:Path)->bool:
    return path.is_file() and not any(x.is_symlink() for x in (path,*path.parents))
def parse_source(raw:bytes,stage313:dict,stage351:dict)->dict:
    if (not isinstance(raw,bytes) or len(raw)>1024
        or not raw.startswith(b"scope,value\n")
        or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw):
        raise ExitTimelineError("missing/noncanonical original Stage360 CSV")
    rows=raw[len(b"scope,value\n"):].splitlines(keepends=True)
    if len(rows)!=len(FIELDS):
        raise ExitTimelineError("wrong original Stage360 source row count")
    values={}
    for key,line in zip(FIELDS,rows):
        prefix=(key+",").encode()
        if (not line.startswith(prefix) or line.count(b",")!=1
            or not line.endswith(b"\n")):
            raise ExitTimelineError("Stage360 CSV columns reordered/altered")
        token=line[len(prefix):-1]
        if (not token or not token.isascii() or not token.isdigit()
            or (len(token)>1 and token.startswith(b"0"))):
            raise ExitTimelineError("noncanonical Stage360 number")
        n=int(token)
        if n>2**64-1 or (key in (
            "software_exit_probe_context_only","tail_observed",
            "last_pre_submit_probe_observed","last_pre_submit_probe_queue_status",
            "last_pre_submit_probe_queue_count","stage351_tail_reason_code"
        ) and n>2**32-1):
            raise ExitTimelineError("original source numeric overflow")
        values[key]=n
    tail=values["tail_observed"]
    begin=values["tail_begin_guest_ns"]
    end=values["tail_end_guest_ns"]
    reason=values["stage351_tail_reason_code"]
    present=values["last_pre_submit_probe_observed"]
    attempt=values["last_pre_submit_probe_attempt"]
    age=values["last_pre_submit_probe_age_ns"]
    status=values["last_pre_submit_probe_queue_status"]
    count=values["last_pre_submit_probe_queue_count"]
    if (values["software_exit_probe_context_only"]!=1
        or tail not in (0,1) or present not in (0,1)
        or status not in (0,1) or reason>7
        or tail!=int(reason!=0)
        or (tail and (begin==0 or end<begin))
        or (not tail and any(values[k] for k in (
            "tail_begin_guest_ns","tail_end_guest_ns","tail_elapsed_ns",
            "normal_submit_attempts_at_tail","last_pre_submit_probe_observed",
            "last_pre_submit_probe_dropped_count")))
        or values["tail_elapsed_ns"]!=end-begin
        or (present and (not tail or attempt==0
            or attempt>values["normal_submit_attempts_at_tail"]
            or age>begin))
        or (not present and (attempt or age or status or count))
        or (present and not status and count)):
        raise ExitTimelineError("Stage360 original context logically inconsistent")
    if (not isinstance(stage313,dict) or not isinstance(stage351,dict)
        or stage313.get("schema")!=TAIL_SCHEMA
        or stage313.get("result")!=TAIL_VERIFIED
        or stage313.get("original_guest_page_witness_observed") is not True
        or stage313.get("tail_bounded_attempt_observed") is not bool(tail)
        or stage313.get("tail_release_confirmed") is not bool(reason==7)
        or stage313.get("hardware_Nintendo_Switch_audio_tested") is not False
        or stage351.get("schema")!=REASON_SCHEMA
        or stage351.get("result")!=REASON_VERIFIED
        or type(stage351.get("reason_code")) is not int
        or stage351["reason_code"]!=reason
        or stage351.get("prior_stage313_and_stage348_original_bytes_reaudited") is not True
        or stage351.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("original Stage313/351 receipts disagree with Stage360")
    expected_begin=stage313.get("tail_attempt_guest_ns")
    expected_end=stage313.get("tail_success_return_guest_ns")
    if (expected_begin!=(begin if tail else None)
        or expected_end!=(end if reason==7 else None)):
        raise ExitTimelineError("original Stage313 tail guest clocks disagree")
    return {
        "schema":SCHEMA,"result":VERIFIED,
        "original_guest_context_sha256":hashlib.sha256(raw).hexdigest(),
        "original_guest_context_bytes_preserved":True,
        "tail_observed":bool(tail),"tail_elapsed_ns":values["tail_elapsed_ns"],
        "normal_submit_attempts_at_tail":values["normal_submit_attempts_at_tail"],
        "last_pre_submit_probe_observed":bool(present),
        "last_pre_submit_probe_attempt":attempt,
        "last_pre_submit_probe_query_succeeded":bool(present and status),
        "last_pre_submit_probe_queue_count":count if present and status else None,
        "last_pre_submit_probe_age_ns":age if present else None,
        "last_pre_submit_probe_dropped_count":values["last_pre_submit_probe_dropped_count"],
        "stage351_tail_reason_code":reason,
        "direct_exit_time_queue_depth_observed":False,
        "scheduler_latency_measured":False,
        "unobserved_queue_never_construed_as_zero":True,
        "queue_probe_timestamp_is_pre_submit_not_query_timestamp":True,
        "audible_dropout_or_DAC_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }
def audit_guest(root:Path,stage313:dict,stage351:dict)->tuple[dict,bytes]:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ExitTimelineError("original guest root missing/linked")
    directory=root
    for segment in SUBDIR.parts:
        directory=directory/segment
        if not directory.is_dir() or directory.is_symlink():
            raise ExitTimelineError("original guest SD directory unsafe")
    files=list(directory.glob("audio-exit-probe-context-*.csv"))
    source=directory/SOURCE
    if len(files)!=1 or files[0]!=source or not regular(source):
        raise ExitTimelineError("missing/ambiguous original Stage360 guest context CSV")
    raw=source.read_bytes()
    doc=parse_source(raw,stage313,stage351)
    doc["original_guest_source_relative_path"]=str(SUBDIR/SOURCE)
    return doc,raw
def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--stage313",type=Path,required=True)
    p.add_argument("--stage351",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-original",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output==a.output_original:
            raise ExitTimelineError("output paths overlap")
        for path in (a.output,a.output_original):
            if path.exists() or path.is_symlink():
                raise ExitTimelineError("refuse overwrite original guest context")
        if not all(regular(p) for p in (a.guest_root_file,a.stage313,a.stage351)):
            raise ExitTimelineError("prior original source receipts missing/linked")
        root=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("guest locator invalid")
        old313=json.loads(a.stage313.read_text(encoding="utf-8"))
        old351=json.loads(a.stage351.read_text(encoding="utf-8"))
        result,raw=audit_guest(Path(root),old313,old351)
        for path in (a.output,a.output_original):
            path.parent.mkdir(parents=True,exist_ok=True)
            if any(x.is_symlink() for x in (path,*path.parents)):
                raise ExitTimelineError("linked report output")
        with a.output_original.open("xb") as out:out.write(raw)
        if a.output_original.read_bytes()!=raw:
            raise ExitTimelineError("original guest CSV bytes not preserved")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(result,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,"reason_code":result["stage351_tail_reason_code"],
            "tail_elapsed_ns":result["tail_elapsed_ns"],
            "probe_age_ns":result["last_pre_submit_probe_age_ns"],
            "direct_exit_queue_depth_observed":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,KeyError,TypeError) as exc:
        print(json.dumps({
            "result":"ORIGINAL_GUEST_EXIT_PROBE_CONTEXT_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested":False
        },sort_keys=True))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
