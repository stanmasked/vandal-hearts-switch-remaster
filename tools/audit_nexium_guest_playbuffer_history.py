#!/usr/bin/env python3
"""Stage322: compare last original PlayBuffer call with up to 15 prior calls.

Reads the ORIGINAL guest-created bounded software call history and the
Stage320 source-validated original final normal PlayBuffer call. No
sampling-clock/DAC mapping; duration is a guest software service call,
not a measurement of audible speaker playback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median_low
import sys

from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError
from audit_nexium_guest_last_playbuffer import (
    VERIFIED as LAST_VERIFIED,
    audit_guest_root as audit_last_playbuffer_guest,
)

FILE="audio-playbuffer-history-000.csv"
SCHEMA="vh-original-last16-PlayBuffer-guest-software-call-history/v1"
VERIFIED="ORIGINAL_GUEST_PLAYBUFFER_HISTORY_REAUDITED"
HEADER=b"total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n"
CAP=16

def audit_source(raw:bytes, final:dict)->dict:
    if (not isinstance(raw,bytes) or len(raw)>2048 or
            not raw.startswith(HEADER) or b"\r" in raw or b"\x00" in raw
            or not raw.endswith(b"\n")):
        raise ExitTimelineError("invalid original bounded PlayBuffer history")
    if final.get("result")!=LAST_VERIFIED:
        raise ExitTimelineError("Stage320 original successful call not source-validated")
    lines=raw[len(HEADER):].splitlines(keepends=True)
    if not 1<=len(lines)<=CAP:
        raise ExitTimelineError("missing or overflowing normal audout history")
    rows=[]
    total=None
    previous_end=None
    for i,line in enumerate(lines):
        if not line.endswith(b"\n"):
            raise ExitTimelineError("unterminated original history row")
        pieces=line[:-1].split(b",")
        if len(pieces)!=5:
            raise ExitTimelineError("original guest PlayBuffer row has wrong width")
        vals=[]
        for part in pieces:
            if (not part or not part.isascii() or not part.isdigit()
                    or (len(part)>1 and part[:1]==b"0")):
                raise ExitTimelineError("noncanonical original audout count/timestamp")
            value=int(part)
            if value>2**64-1:
                raise ExitTimelineError("guest software history integer overflow")
            vals.append(value)
        count,seq,begin,end,returned=vals
        if total is None:
            total=count
        if (count!=total or not count or count< len(lines)
                or len(lines)!=min(count,CAP)
                or seq!=count-len(lines)+i+1
                or not begin or end<begin or returned not in (0,1)
                or (previous_end is not None and begin<previous_end)):
            raise ExitTimelineError("nonconsecutive/overlapping original PlayBuffer history")
        previous_end=end
        rows.append({"sequence":seq,"begin_guest_ns":begin,
                     "end_guest_ns":end,"duration_guest_ns":end-begin,
                     "lease_returned":bool(returned)})
    if total!=final["PlayBuffer_call_attempt_count"]:
        raise ExitTimelineError("rolling history original call count conflicts with Stage320")
    original_last_idx=final["last_successful_PlayBuffer_attempt_index"]
    observed_successes=[r for r in rows if r["lease_returned"]]
    original_success_count=final["successful_PlayBuffer_call_count"]
    if (len(observed_successes)>original_success_count
            or len(rows)-len(observed_successes)>total-original_success_count):
        raise ExitTimelineError("recent retained original calls conflict with global successful/failed counts")
    if (any(r["sequence"]>original_last_idx for r in observed_successes)
            or (original_last_idx>=rows[0]["sequence"] and
                (not observed_successes or
                 observed_successes[-1]["sequence"]!=original_last_idx))):
        raise ExitTimelineError("history original successful call ordering differs from Stage320")
    last_in_window=original_last_idx>=rows[0]["sequence"]
    if (not last_in_window and
            rows[0]["begin_guest_ns"]<
                final["last_successful_PlayBuffer_return_guest_ns"]):
        raise ExitTimelineError("retained calls precede an earlier already-finished last success")
    if last_in_window:
        entry=observed_successes[-1]
        if (entry["begin_guest_ns"]!=final["last_successful_PlayBuffer_begin_guest_ns"]
                or entry["end_guest_ns"]!=final["last_successful_PlayBuffer_return_guest_ns"]
                or entry["duration_guest_ns"]!=
                    final["last_successful_PlayBuffer_software_duration_ns"]):
            raise ExitTimelineError("last successful original guest call differs from Stage320")
        prior_successes=observed_successes[:-1]
    else:
        prior_successes=[]  # Cannot assert prior baseline without the last call.
    baseline=[r["duration_guest_ns"] for r in prior_successes]
    duration=final["last_successful_PlayBuffer_software_duration_ns"]
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "original_guest_history_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "original_last_successful_PlayBuffer_source_sha256":
            final["original_last_playbuffer_csv_sha256"],
        "total_original_normal_PlayBuffer_calls":total,
        "original_recent_call_count":len(rows),
        "original_recent_success_count":len(observed_successes),
        "original_recent_failed_return_count":len(rows)-len(observed_successes),
        "original_call_rows":rows,
        "final_successful_call_in_recent_window":last_in_window,
        "prior_successful_call_count_in_window":len(baseline),
        "prior_successful_duration_min_guest_ns":min(baseline) if baseline else None,
        "prior_successful_duration_lower_median_guest_ns":
            median_low(baseline) if baseline else None,
        "prior_successful_duration_max_guest_ns":max(baseline) if baseline else None,
        "final_call_duration_guest_ns":duration,
        "final_minus_prior_lower_median_guest_ns":
            duration-median_low(baseline) if baseline else None,
        "history_is_not_the_entire_session":True,
        "one_call_is_not_DAC_or_last_audible_sample":True,
        "guest_software_time_not_host_PCM_sample_clock":True,
        "original_PS1_retail_soundtrack_verified":False,
        "plus_caused_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def audit_guest(root:Path)->tuple[dict,bytes|None]:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("invalid guest history source root")
    path=root/SUBDIR/FILE
    if not path.exists():
        return ({
            "schema":SCHEMA,
            "result":"ORIGINAL_PLAYBUFFER_HISTORY_GUEST_SD_NOT_OBSERVED",
            "original_guest_history_source_observed":False,
            "physical_Nintendo_Switch_audio_tested":False,
        },None)
    sources=list((root/SUBDIR).glob("audio-playbuffer-history-*.csv"))
    if len(sources)!=1 or path.is_symlink() or not path.is_file():
        raise ExitTimelineError("ambiguous/symlinked original PlayBuffer history CSV")
    final,_=audit_last_playbuffer_guest(root)
    raw=path.read_bytes()
    result=audit_source(raw,final)
    result["original_guest_history_source_observed"]=True
    result["original_guest_history_source_path"]=str(SUBDIR/FILE)
    return result,raw

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-original",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink() or (
                a.output_original.exists() or a.output_original.is_symlink()):
            raise ExitTimelineError("refuse overwrite original software audio evidence")
        if a.guest_root_file.is_symlink() or not a.guest_root_file.is_file():
            raise ExitTimelineError("original guest SD root locator missing")
        root=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("invalid guest source root locator")
        report,raw=audit_guest(Path(root))
        if raw is not None:
            a.output_original.parent.mkdir(parents=True,exist_ok=True)
            with a.output_original.open("xb") as f:
                f.write(raw)
            if a.output_original.read_bytes()!=raw:
                raise ExitTimelineError("original audout history changed during byte preservation")
            report["original_guest_history_bytes_preserved"]=True
        else:
            report["original_guest_history_bytes_preserved"]=False
        a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({"result":report["result"],
            "last_call_guest_software_ns":report.get("final_call_duration_guest_ns"),
            "prior_lower_median_guest_software_ns":
                report.get("prior_successful_duration_lower_median_guest_ns"),
            "audible_sound_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE322_ORIGINAL_PLAYBUFFER_HISTORY_NOT_VERIFIED",
                          "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
