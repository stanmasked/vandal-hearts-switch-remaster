#!/usr/bin/env python3
"""Stage309: independently re-decode archived NeXium optical PNGs and compare
source-bound guest exit software receipts across different workflow runs.

Archived Stage307 JSON is a *capture-time audited receipt*: absent original
guest SD CSV in an old archive, we cannot claim we re-read its source bytes.
This tool never estimates host PCM/DAC timing or audible music quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from audit_nexium_guest_exit_timeline import OBSERVED, EVENTS, ExitTimelineError, parse_exit_csv
from audit_nexium_guest_optical_exit_clock import (
    BOTH, audit_guest_clocks,
)
from audit_switch_guest_scene_trace import TraceError

SCHEMA = "vh-independent-nexium-guest-software-exit-cohort/v1"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REPORT_NAME = "guest-audio-exit-timeline-stage307.json"
FRAME_NAME = "scene-optical-trace.png"
CROSS_NAME = "guest-optical-exit-clock-stage308.json"


def check_guest_report(guest: dict, raw_original: bytes | None) -> dict:
    if not isinstance(guest,dict) or guest.get("result")!=OBSERVED or (
            guest.get("guest_sd_receipt_observed") is not True):
        raise TraceError("guest exit source not observed and ordered")
    d=guest.get("guest_exit_csv_sha256")
    if not isinstance(d,str) or not DIGEST.fullmatch(d):
        raise TraceError("invalid guest exit CSV source hash")
    if (guest.get("host_PCM_to_guest_timestamp_mapping_verified") is not False
            or guest.get("original_soundtrack_or_audible_dropout_verified") is not False
            or guest.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise TraceError("guest exit receipt overclaims music or DAC")
    if raw_original is not None:
        try:
            fresh=parse_exit_csv(raw_original)
        except ExitTimelineError as exc:
            raise TraceError("original guest exit CSV cannot be re-audited") from exc
        for key,value in fresh.items():
            if key in guest and guest[key]!=value:
                raise TraceError("archived guest exit receipt disagrees with original CSV")
        if hashlib.sha256(raw_original).hexdigest()!=d:
            raise TraceError("guest CSV source SHA256 mismatch")
    times=guest.get("guest_monotonic_timestamps_ns")
    if not isinstance(times,dict) or set(times)!=set(EVENTS):
        raise TraceError("incomplete guest clock fields")
    sequence=[times[k] for k in EVENTS]
    if any(type(v) is not int or not 0<v<=2**64-1 for v in sequence):
        raise TraceError("invalid guest clock readings")
    if any(a>=b for a,b in zip(sequence,sequence[1:])):
        raise TraceError("reversed/duplicate guest exit milestone")
    measured={
        "plus_to_stop_request_ns":sequence[1]-sequence[0],
        "stop_request_to_worker_cleanup_ns":sequence[2]-sequence[1],
        "worker_cleanup_to_audout_close_ns":sequence[3]-sequence[2],
        "audout_close_to_worker_join_ns":sequence[4]-sequence[3],
        "plus_to_join_ns":sequence[-1]-sequence[0],
    }
    map_old={
        "plus_observed_to_stop_requested_ns":"plus_to_stop_request_ns",
        "stop_request_to_worker_cleanup_ns":"stop_request_to_worker_cleanup_ns",
        "worker_cleanup_to_audout_close_ns":"worker_cleanup_to_audout_close_ns",
        "audout_close_to_worker_join_ns":"audout_close_to_worker_join_ns",
    }
    if any(guest.get(k)!=measured[v] for k,v in map_old.items()):
        raise TraceError("guest milestone duration receipt forged")
    return {"sha256":d, "time_ns":times,"durations_ns":measured,
            "original_raw_guest_csv_reverified":raw_original is not None}


def compare_sessions(sessions: list[tuple[int,bytes,dict,bytes | None,dict | None]]) -> dict:
    if not isinstance(sessions,list) or not 2<=len(sessions)<=8:
        raise TraceError("requires two to eight distinct NeXium runs")
    out=[]
    ids=set()
    optical_digests=set()
    exit_digests=set()
    for run,png,guest,raw_exit,stored_stage308 in sessions:
        if type(run) is not int or run<=0 or run in ids:
            raise TraceError("missing or duplicate workflow run")
        ids.add(run)
        v=check_guest_report(guest,raw_exit)
        optical=audit_guest_clocks(png,guest)
        if optical["result"]!=BOTH or optical["guest_exit_order_verified"] is not True:
            raise TraceError("guest/optical source comparison incomplete")
        if stored_stage308 is not None and stored_stage308!=optical:
            raise TraceError("Stage308 archived source receipt disagrees with optical PNG")
        osha=optical["optical_scene_png_sha256"]
        if osha in optical_digests or v["sha256"] in exit_digests:
            raise TraceError("duplicate optical picture or guest exit capture")
        optical_digests.add(osha)
        exit_digests.add(v["sha256"])
        out.append({
            "workflow_run_id":run,
            "optical_scene_png_sha256":osha,
            "guest_exit_csv_sha256":v["sha256"],
            "original_guest_csv_bytes_reverified":v["original_raw_guest_csv_reverified"],
            "last_scene_to_guest_plus_ns":optical["scene_last_event_to_plus_ns"],
            "guest_shutdown_durations_ns":v["durations_ns"],
            "guest_exit_milestones_ordered":True,
            "guest_to_host_PCM_clock_mapping_verified":False,
            "physical_Nintendo_Switch_audio_tested":False,
        })
    keys=out[0]["guest_shutdown_durations_ns"]
    bounds={}
    for key in keys:
        values=[s["guest_shutdown_durations_ns"][key] for s in out]
        bounds[key]={
            "min_ns":min(values),"max_ns":max(values),
            "range_ns":max(values)-min(values),
            "all_guest_software_intervals_positive":all(v>0 for v in values)
        }
    return {
        "schema":SCHEMA,
        "result":"DISTINCT_GUEST_SOFTWARE_EXIT_RUNS_REPLAYED",
        "run_count":len(out),
        "source_bound_rows":out,
        "distinct_workflow_runs":True,
        "distinct_optical_original_png_sha256":True,
        "distinct_exit_receipt_sha256":True,
        "per_milestone_duration_bounds":bounds,
        "all_guest_exit_milestones_observed_in_every_run":True,
        "all_original_guest_csv_bytes_reaudited":
            all(row["original_guest_csv_bytes_reverified"] for row in out),
        "host_pcm_and_guest_monotonic_clocks_not_calibrated":True,
        "guest_shutdown_is_not_audible_dropout_proof":True,
        "original_soundtrack_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def load_capture(run: int, directory: Path) -> tuple:
    if directory.is_symlink() or not directory.is_dir():
        raise TraceError("unavailable capture directory")
    found=list(directory.rglob(FRAME_NAME))
    if len(found)!=1 or found[0].is_symlink():
        raise TraceError("original guest optical PNG missing/ambiguous")
    root=found[0].parent
    report=root/REPORT_NAME
    if report.is_symlink() or not report.is_file():
        raise TraceError("missing actual Stage307 source-bound receipt")
    raw_path=root/"audio-exit-timeline-000.csv"
    raw=raw_path.read_bytes() if raw_path.is_file() and not raw_path.is_symlink() else None
    cross=root/CROSS_NAME
    stored=(json.loads(cross.read_text(encoding="utf-8"))
            if cross.is_file() and not cross.is_symlink() else None)
    return (run,found[0].read_bytes(),
            json.loads(report.read_text(encoding="utf-8")),raw,stored)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture",action="append",required=True,
                        metavar="RUN_ID:ORIGINAL_ARTIFACT_DIR")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse overwrite existing audit")
        sessions=[]
        for x in args.capture:
            rid,sep,path=x.partition(":")
            if not sep or not rid.isdecimal() or not path:
                raise TraceError("invalid run:directory argument")
            sessions.append(load_capture(int(rid),Path(path)))
        output=compare_sessions(sessions)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n",
                               encoding="utf-8")
        print(json.dumps({"result":output["result"],
                          "run_count":output["run_count"],
                          "shutdown_duration_bounds":
                              output["per_milestone_duration_bounds"],
                          "all_original_guest_csv_bytes_reaudited":
                              output["all_original_guest_csv_bytes_reaudited"],
                          "hardware_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE309_GUEST_EXIT_COHORT_NOT_VERIFIED",
                          "error":str(exc)}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
