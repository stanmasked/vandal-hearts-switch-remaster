#!/usr/bin/env python3
"""Stage313: guest software RELEASED audout PCM pages vs Plus/worker exit.

A released page is not audible output, DAC timing or a measurement of
host PulseAudio file-size frames. Missing guest SD remains NOT_OBSERVED.
"""
from __future__ import annotations
import argparse,csv,hashlib,json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    OBSERVED, SUBDIR, audit_guest_root, ExitTimelineError,
)

SCHEMA="vh-guest-last-audout-page-release-versus-exit/v1"
FIELDS=("page_return_count","last_page_return_guest_ns","last_page_frames",
        "tail_attempt_guest_ns","tail_success_return_guest_ns")
ORIGINAL="audio-exit-output-000.csv"
NOT_OBSERVED="GUEST_LAST_AUDOUT_RELEASE_NOT_OBSERVED"
COMPLETE="GUEST_LAST_AUDOUT_RELEASE_SOFTWARE_TIMING_VALIDATED"

def audit_source(raw:bytes,exit_report:dict)->dict:
    if (not raw or b"\r" in raw or b"\x00" in raw
            or not raw.endswith(b"\n") or len(raw)>1024):
        raise ExitTimelineError("noncanonical audout witness")
    try:
        decoded=raw.decode("ascii")
        reader=csv.DictReader(decoded.splitlines(),strict=True)
        if reader.fieldnames!=["event","value"]:
            raise ExitTimelineError("audout witness header mismatch")
        records=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ExitTimelineError("invalid audout source CSV") from exc
    if len(records)!=5 or tuple(r.get("event") for r in records)!=FIELDS:
        raise ExitTimelineError("missing/duplicate last-page fields")
    vals=[]
    for r in records:
        if set(r)!={"event","value"}:
            raise ExitTimelineError("malformed audout CSV row")
        value=r["value"]
        if (not value or not value.isascii() or not value.isdecimal()
                or (len(value)>1 and value[0]=="0")):
            raise ExitTimelineError("noncanonical page software clock")
        n=int(value)
        if n>2**64-1:
            raise ExitTimelineError("audout page counter overflow")
        vals.append(n)
    pages,last,frames,tail_attempt,tail_return=vals
    if ((pages==0)!=(last==0) or (pages==0)!=(frames==0)
            or frames>4096 or pages>2**63):
        raise ExitTimelineError("incoherent last page count/source")
    if (tail_attempt==0 and tail_return!=0) or (
            tail_attempt>0 and tail_return>0 and tail_return<tail_attempt):
        raise ExitTimelineError("invalid bounded tail release")
    if exit_report.get("result")!=OBSERVED:
        raise ExitTimelineError("missing original observed guest exit chronology")
    times=exit_report["guest_monotonic_timestamps_ns"]
    plus,stop,cleanup,closed,joined=(times[k] for k in (
        "plus_observed","stop_requested","worker_cleanup_entered",
        "audout_closed","worker_joined"))
    if not 0<plus<stop<cleanup<closed<joined:
        raise ExitTimelineError("guest shutdown clock reversed")
    if last>closed or (tail_attempt and not cleanup<=tail_attempt<=closed) or (
            tail_return>closed):
        raise ExitTimelineError("last release/taper after audout closed")
    if last==0:
        category="no_successfully_returned_PCM_page_observed"
    elif last<plus:
        category="last_page_returned_before_Plus_observed"
    elif last<stop:
        category="last_page_returned_after_Plus_before_stop"
    elif last<cleanup:
        category="last_page_returned_after_stop_before_cleanup"
    else:
        category="last_page_returned_during_cleanup"
    return {
        "schema":SCHEMA,
        "result":COMPLETE,
        "original_guest_page_witness_sha256":hashlib.sha256(raw).hexdigest(),
        "original_guest_exit_csv_sha256":exit_report["guest_exit_csv_sha256"],
        "page_return_count":pages,
        "last_page_frames":frames,
        "last_page_return_guest_ns":last if last else None,
        "last_page_relative_to_Plus_ns":last-plus if last else None,
        "last_page_position_relative_to_guest_exit":category,
        "tail_bounded_attempt_observed":tail_attempt>0,
        "tail_release_confirmed":tail_return>0,
        "tail_attempt_guest_ns":tail_attempt if tail_attempt else None,
        "tail_success_return_guest_ns":tail_return if tail_return else None,
        "last_page_return_is_not_DAC_or_speaker_output":True,
        "normal_exit_taper_is_not_PS1_SPU_rendered_music":True,
        "host_pcm_to_guest_clock_calibrated":False,
        "audible_dropout_verified":False,
        "hardware_Nintendo_Switch_audio_tested":False,
    }

def audit_guest(root:Path)->dict:
    exit_report=audit_guest_root(root)
    source=root/SUBDIR/ORIGINAL
    if not source.exists():
        return {
            "schema":SCHEMA,"result":NOT_OBSERVED,
            "original_guest_page_witness_observed":False,
            "host_pcm_to_guest_clock_calibrated":False,
            "audible_dropout_verified":False,
            "hardware_Nintendo_Switch_audio_tested":False,
        }
    if source.is_symlink() or not source.is_file():
        raise ExitTimelineError("unsafe guest last page source")
    all_sources=list((root/SUBDIR).glob("audio-exit-output-*.csv"))
    if len(all_sources)!=1:
        raise ExitTimelineError("multiple source CSV files for guest page return")
    report=audit_source(source.read_bytes(),exit_report)
    report["original_guest_page_witness_observed"]=True
    report["guest_source_path"]=str(SUBDIR/ORIGINAL)
    return report

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ExitTimelineError("refuse overwrite")
        if a.guest_root_file.is_symlink() or not a.guest_root_file.is_file():
            raise ExitTimelineError("missing guest SD root evidence")
        root=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("untrusted guest root locator")
        result=audit_guest(Path(root))
        a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"result":result["result"],
                          "last_page_position_relative_to_guest_exit":
                              result.get("last_page_position_relative_to_guest_exit"),
                          "audible_sound_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE313_LAST_AUDOUT_RELEASE_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
