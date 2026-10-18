#!/usr/bin/env python3
"""Stage316: independently compare two authentic guest audout-release captures.

The older NeXium run retained source-audited JSON but not the original
guest-created audout last-page CSV. The later run has original CSV bytes
independently replayed by Stage315 on a separate GitHub runner.
Never promote these unequal evidence tiers into one raw-byte claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_switch_guest_scene_trace import TraceError
from audit_nexium_guest_exit_timeline import OBSERVED
from audit_nexium_guest_optical_exit_clock import BOTH, audit_guest_clocks
from audit_nexium_guest_last_buffer_return import COMPLETE
from replay_nexium_original_audout_exit_archive import (
    read_original_archive, independent_original_audout_replay,
)

SCHEMA="vh-nexium-two-run-last-audout-release-provenance/v1"
RESULT="TWO_INDEPENDENT_GUEST_LAST_PAGE_RELEASES_COMPARED"
HASH=re.compile(r"^[0-9a-f]{64}$")
EXPECTED_CLASS="last_page_returned_after_stop_before_cleanup"


def validate_guest_last_page(run_id:int, optical_png:bytes, exit_report:dict,
                             optical_report:dict, page_report:dict) -> dict:
    if type(run_id) is not int or run_id<=0:
        raise TraceError("invalid originating NeXium workflow id")
    if (not isinstance(exit_report,dict) or exit_report.get("result")!=OBSERVED
            or exit_report.get("guest_sd_receipt_observed") is not True):
        raise TraceError("missing capture-time original guest exit source receipt")
    optical=audit_guest_clocks(optical_png,exit_report)
    if optical["result"]!=BOTH or optical!=optical_report:
        raise TraceError("original optical PNG/guest exit witness cannot be replayed")
    if (not isinstance(page_report,dict)
            or page_report.get("result")!=COMPLETE
            or page_report.get("original_guest_page_witness_observed") is not True):
        raise TraceError("missing original guest audout source witness")
    page_sha=page_report.get("original_guest_page_witness_sha256")
    exit_sha=page_report.get("original_guest_exit_csv_sha256")
    if (not isinstance(page_sha,str) or not HASH.fullmatch(page_sha)
            or exit_sha!=exit_report.get("guest_exit_csv_sha256")):
        raise TraceError("original guest page source not bound to guest exit source")
    if (page_report.get("last_page_return_is_not_DAC_or_speaker_output") is not True
            or page_report.get("normal_exit_taper_is_not_PS1_SPU_rendered_music") is not True
            or page_report.get("host_pcm_to_guest_clock_calibrated") is not False
            or page_report.get("audible_dropout_verified") is not False
            or page_report.get("hardware_Nintendo_Switch_audio_tested") is not False):
        raise TraceError("audout source claims playback hardware or wrong clock")
    timestamps=exit_report["guest_monotonic_timestamps_ns"]
    labels=("plus_observed","stop_requested","worker_cleanup_entered",
            "audout_closed","worker_joined")
    vals=[timestamps[x] for x in labels]
    if any(type(x) is not int or x<=0 for x in vals) or not all(
            a<b for a,b in zip(vals,vals[1:])):
        raise TraceError("guest exit timestamps not strictly ordered")
    plus,stop,cleanup,closed,joined=vals
    page=page_report.get("last_page_return_guest_ns")
    count=page_report.get("page_return_count")
    frames=page_report.get("last_page_frames")
    if (any(type(x) is not int for x in (page,count,frames)) or
            not page>0 or not count>0 or not 0<frames<=4096 or page>closed):
        raise TraceError("guest audout last returned source is missing")
    if page<plus:
        expected="last_page_returned_before_Plus_observed"
    elif page<stop:
        expected="last_page_returned_after_Plus_before_stop"
    elif page<cleanup:
        expected="last_page_returned_after_stop_before_cleanup"
    else:
        expected="last_page_returned_during_cleanup"
    if (page_report.get("last_page_position_relative_to_guest_exit")!=expected
            or page_report.get("last_page_relative_to_Plus_ns")!=page-plus):
        raise TraceError("last guest audout release class/frame time not source-consistent")
    tail_attempt=page_report.get("tail_attempt_guest_ns")
    tail_return=page_report.get("tail_success_return_guest_ns")
    if page_report.get("tail_bounded_attempt_observed") is not (tail_attempt is not None):
        raise TraceError("tail attempt witness inconsistent")
    if page_report.get("tail_release_confirmed") is not (tail_return is not None):
        raise TraceError("tail release witness inconsistent")
    if tail_attempt is not None and (type(tail_attempt) is not int
                                    or not cleanup<=tail_attempt<=closed):
        raise TraceError("tail attempt outside cleanup")
    if tail_return is not None and (type(tail_return) is not int
                                    or tail_attempt is None
                                    or not tail_attempt<=tail_return<=closed):
        raise TraceError("tail buffer return outside cleanup")
    return {
        "original_workflow_run_id":run_id,
        "original_optical_png_sha256":optical["optical_scene_png_sha256"],
        "original_exit_csv_sha256":exit_sha,
        "original_last_page_csv_sha256":page_sha,
        "last_page_return_after_Plus_ns":page-plus,
        "last_page_return_guest_ns":page,
        "last_page_position_relative_to_exit":expected,
        "successful_normal_page_returns":count,
        "last_returned_page_frames":frames,
        "bounded_exit_tail_attempted":tail_attempt is not None,
        "bounded_exit_tail_release_confirmed":tail_return is not None,
        "original_last_page_csv_bytes_independently_reaudited":False,
    }


def compare_two(old:tuple,new:tuple,
                independent_stage315:dict) -> dict:
    if (not isinstance(old,tuple) or len(old)!=5
            or not isinstance(new,tuple) or len(new)!=3
            or not isinstance(independent_stage315,dict)):
        raise TraceError("requires older optical/page JSON and later original bytes")
    old_id, old_png, old_exit, old_optical, old_page=old
    new_id, new_inputs, new_replay_id = new
    if type(new_replay_id) is not int or new_replay_id!=new_id or new_id==old_id:
        raise TraceError("duplicate or mismatched original NeXium workflow IDs")
    if not isinstance(new_inputs,tuple) or len(new_inputs)!=8:
        raise TraceError("new capture requires all eight ORIGINAL source files")
    first=validate_guest_last_page(old_id,old_png,old_exit,old_optical,old_page)
    raw_exit,raw_page,png,guest307,guest308,guest310,guest313,guest314=new_inputs
    second=validate_guest_last_page(new_id,png,guest307,guest308,guest313)
    independent=independent_original_audout_replay(*new_inputs,new_id)
    if independent!=independent_stage315:
        raise TraceError("separate Stage315 original-byte source runner receipt mismatched")
    if (second["original_last_page_csv_sha256"]!=
            independent["original_guest_audout_page_csv_sha256"]
            or second["original_exit_csv_sha256"]!=
            independent["original_guest_exit_csv_sha256"]
            or second["original_optical_png_sha256"]!=
            independent["optical_original_PNG_sha256"]
            or second["last_page_return_after_Plus_ns"]!=
            independent["last_page_relative_to_guest_Plus_observed_ns"]
            or not independent["both_original_guest_created_CSVs_reaudited_byte_exact"]):
        raise TraceError("new source guest last page/Stage315 replay mismatch")
    second["original_last_page_csv_bytes_independently_reaudited"]=True
    if (first["original_optical_png_sha256"]==
            second["original_optical_png_sha256"]
            or first["original_exit_csv_sha256"]==
            second["original_exit_csv_sha256"]
            or first["original_last_page_csv_sha256"]==
            second["original_last_page_csv_sha256"]):
        raise TraceError("original optical/guest exit/page sources are not independent")
    nums=[first["last_page_return_after_Plus_ns"],
          second["last_page_return_after_Plus_ns"]]
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "run_count":2,
        "source_runs":[first,second],
        "capture_time_JSON_only_audout_run_ids":[old_id],
        "byte_original_independently_reaudited_audout_run_ids":[new_id],
        "separate_stage315_original_source_replay_identical":True,
        "all_original_optical_scene_PNGs_independently_CRC_replayed":True,
        "all_successful_last_page_returns_after_stop_before_cleanup":all(
            row["last_page_position_relative_to_exit"]==EXPECTED_CLASS
            for row in (first,second)),
        "all_bounded_taper_buffer_returns_confirmed":all(
            row["bounded_exit_tail_release_confirmed"] for row in (first,second)),
        "last_page_after_Plus_guest_software_interval_ns":{
            "minimum":min(nums),
            "maximum":max(nums),
            "range":max(nums)-min(nums),
            "observations":[
                {"run_id":row["original_workflow_run_id"],
                 "guest_software_ns":row["last_page_return_after_Plus_ns"]}
                for row in (first,second)],
        },
        "first_capture_original_audout_bytes_NOT_reaudited":True,
        "audout_return_is_NOT_speaker_or_DAC_sample_time":True,
        "guest_clock_NOT_calibrated_to_host_pcm_frames":True,
        "Plus_caused_audible_dropout_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def read_old(root:Path,run_id:int)->tuple:
    if root.is_symlink() or not root.is_dir():
        raise TraceError("unsafe old source archive")
    names=("scene-optical-trace.png",
           "guest-audio-exit-timeline-stage307.json",
           "guest-optical-exit-clock-stage308.json",
           "guest-last-audout-release-stage313.json")
    sources=[]
    for name in names:
        matches=list(root.rglob(name))
        if len(matches)!=1 or matches[0].is_symlink() or not matches[0].is_file():
            raise TraceError("old optical/frame guest exit source absent or ambiguous")
        sources.append(matches[0])
    if len({p.parent for p in sources})!=1:
        raise TraceError("old source files not co-located")
    return (
        run_id,sources[0].read_bytes(),
        *(json.loads(p.read_text(encoding="utf-8")) for p in sources[1:]),
    )


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--legacy-workflow",type=int,required=True)
    p.add_argument("--legacy-archive",type=Path,required=True)
    p.add_argument("--original-workflow",type=int,required=True)
    p.add_argument("--original-archive",type=Path,required=True)
    p.add_argument("--stage315-independent-receipt",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse overwrite Stage316 result")
        if (args.stage315_independent_receipt.is_symlink() or
                not args.stage315_independent_receipt.is_file()):
            raise TraceError("independent Stage315 source receipt missing")
        old=read_old(args.legacy_archive,args.legacy_workflow)
        second=(args.original_workflow,
                read_original_archive(args.original_archive),
                args.original_workflow)
        stage315=json.loads(args.stage315_independent_receipt.read_text(
            encoding="utf-8"))
        result=compare_two(old,second,stage315)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                               encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "guest_software_last_return_intervals_ns":
                result["last_page_after_Plus_guest_software_interval_ns"],
            "older_original_bytes_reaudited":False,
            "audible_audio_fault_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE316_SOURCE_BOUND_COMPARISON_NOT_VERIFIED",
                          "error":str(exc)},sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
