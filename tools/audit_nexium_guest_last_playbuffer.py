#!/usr/bin/env python3
"""Stage320: audit ORIGINAL guest last PlayBuffer service call bracket.

The audoutPlayBuffer begin/end timestamps existed in the Stage269
service telemetry already. Stage320 only retains the LAST successful
call on the guest monotonic SOFTWARE clock. It is not a DAC/speaker
audio interval and doesn't establish which part of the Plus->join
duration was causally due to this one syscall.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    SUBDIR, ExitTimelineError, audit_guest_root as audit_exit,
)
from audit_nexium_guest_last_buffer_return import audit_guest as audit_last_page
from audit_nexium_guest_worker_stop_observed import (
    VERIFIED as WORKER_VERIFIED, audit_worker_source_root,
)

FILE="audio-last-playbuffer-000.csv"
SCHEMA="vh-guest-last-successful-PlayBuffer-software-bracket/v1"
VERIFIED="ORIGINAL_GUEST_LAST_PLAYBUFFER_BRACKET_VERIFIED"
NAMES=("attempts","successes","failures","last_success_attempt",
       "last_success_begin_guest_ns","last_success_end_guest_ns",
       "nonmonotonic_rejected")


def audit_original(raw:bytes, exit_doc:dict, page_doc:dict, worker_doc:dict)->dict:
    if not isinstance(raw,bytes) or len(raw)>512 or b"\x00" in raw or b"\r" in raw:
        raise ExitTimelineError("invalid original audout call source")
    lines=raw.splitlines(keepends=True)
    if len(lines)!=8 or lines[0]!=b"event,value\n" or any(
            not line.endswith(b"\n") for line in lines):
        raise ExitTimelineError("noncanonical audout call source")
    vals=[]
    for name,line in zip(NAMES,lines[1:]):
        key,sep,value=line[:-1].partition(b",")
        if not sep or key!=name.encode("ascii") or not value or (
                not value.isascii() or not value.isdigit() or
                len(value)>1 and value[:1]==b"0"):
            raise ExitTimelineError("invalid audout call source field/order")
        val=int(value)
        if val>2**64-1:
            raise ExitTimelineError("uint64 original audout field overflow")
        vals.append(val)
    count,success,failures,index,begin,end,clock_rejected=vals
    if (not count or not success or success+failures!=count
            or index>count or not index or clock_rejected
            or not 0<begin<=end):
        raise ExitTimelineError("no trustworthy final successful audout service call")
    if (worker_doc.get("result")!=WORKER_VERIFIED or
            page_doc.get("original_guest_exit_csv_sha256")!=
                exit_doc.get("guest_exit_csv_sha256") or
            worker_doc.get("source_last_page_csv_sha256")!=
                page_doc.get("original_guest_page_witness_sha256") or
            worker_doc.get("source_guest_exit_csv_sha256")!=
                exit_doc.get("guest_exit_csv_sha256")):
        raise ExitTimelineError("worker/last page/exit original source chain mismatch")
    t=exit_doc["guest_monotonic_timestamps_ns"]
    stop=t["stop_requested"]
    cleanup=t["worker_cleanup_entered"]
    page=page_doc["last_page_return_guest_ns"]
    observed=worker_doc["worker_stop_observation_guest_ns"]
    if not all(type(x) is int and x>0 for x in (stop,cleanup,page,observed)):
        raise ExitTimelineError("original guest software timestamps incomplete")
    if not begin<=end<=page<=observed<=cleanup or not stop<=page:
        raise ExitTimelineError("PlayBuffer bracket outside verified guest shutdown timeline")
    overlap=max(0,end-max(begin,stop))
    if end<=stop:
        category="last_successful_PlayBuffer_returned_before_stop_request"
    elif begin<stop:
        category="last_successful_PlayBuffer_spanned_stop_request"
    else:
        category="last_successful_PlayBuffer_started_after_stop_request"
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "original_last_playbuffer_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "original_guest_exit_csv_sha256":exit_doc["guest_exit_csv_sha256"],
        "original_guest_last_page_csv_sha256":
            page_doc["original_guest_page_witness_sha256"],
        "original_guest_worker_stop_csv_sha256":
            worker_doc["original_guest_worker_stop_csv_sha256"],
        "successful_PlayBuffer_call_count":success,
        "PlayBuffer_call_attempt_count":count,
        "last_successful_PlayBuffer_attempt_index":index,
        "last_successful_PlayBuffer_begin_guest_ns":begin,
        "last_successful_PlayBuffer_return_guest_ns":end,
        "last_successful_PlayBuffer_software_duration_ns":end-begin,
        "last_successful_call_relative_to_stop_request":category,
        "portion_of_last_call_after_stop_request_ns":overlap,
        "last_successful_PlayBuffer_return_to_page_witness_ns":page-end,
        "last_page_witness_to_worker_stop_observed_ns":observed-page,
        "audout_PlayBuffer_return_not_audible_speaker_or_DAC":True,
        "one_call_does_not_explain_entire_stop_delay_automatically":True,
        "guest_clock_not_synchronized_to_host_PCM":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "audible_dropout_verified":False,
    }


def audit_guest_root(root:Path)->tuple[dict,bytes|None]:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("invalid original guest SD root")
    p=root/SUBDIR/FILE
    if not p.exists():
        return ({"schema":SCHEMA,
                 "result":"ORIGINAL_LAST_PLAYBUFFER_GUEST_SD_NOT_OBSERVED",
                 "original_source_bytes_preserved":False,
                 "audible_dropout_verified":False},None)
    if p.is_symlink() or not p.is_file() or len(
            list((root/SUBDIR).glob("audio-last-playbuffer-*.csv")))!=1:
        raise ExitTimelineError("ambiguous or symlinked original PlayBuffer source")
    exit_doc=audit_exit(root)
    page_doc=audit_last_page(root)
    worker_doc,worker_raw=audit_worker_source_root(root)
    if worker_raw is None:
        raise ExitTimelineError("original worker stop CSV unavailable")
    raw=p.read_bytes()
    report=audit_original(raw,exit_doc,page_doc,worker_doc)
    report["original_guest_playbuffer_source_observed"]=True
    report["original_guest_playbuffer_source_path"]=str(SUBDIR/FILE)
    return report,raw


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--output-original",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if any(q.exists() or q.is_symlink() for q in (a.output,a.output_original)):
            raise ExitTimelineError("refuse overwrite original audout source")
        if a.guest_root_file.is_symlink() or not a.guest_root_file.is_file():
            raise ExitTimelineError("missing original SD root locator")
        r=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not r.startswith("/") or "\n" in r or "\x00" in r:
            raise ExitTimelineError("untrusted original guest SD path")
        report,raw=audit_guest_root(Path(r))
        if raw is not None:
            a.output_original.parent.mkdir(parents=True,exist_ok=True)
            with a.output_original.open("xb") as f:
                f.write(raw)
            if a.output_original.read_bytes()!=raw:
                raise ExitTimelineError("source changed after byte-exact copy")
            report["original_source_bytes_preserved"]=True
        else:
            report["original_source_bytes_preserved"]=False
        a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                            encoding="utf-8")
        print(json.dumps({"result":report["result"],
                          "last_call_software_ns":
                              report.get("last_successful_PlayBuffer_software_duration_ns"),
                          "overlap_with_main_stop_request_ns":
                              report.get("portion_of_last_call_after_stop_request_ns"),
                          "audible_speaker_proof":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE320_GUEST_AUDOUT_LAST_CALL_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
