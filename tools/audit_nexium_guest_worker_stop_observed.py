#!/usr/bin/env python3
"""Stage317: independently verify when audio worker observed stop mailbox.

Guest observed Plus, main stop request, final successful audout page
RETURN and worker stop observation all share guest software monotonic ns.
This is NOT the host PCM, audout DAC or audible speaker playback clock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    ExitTimelineError, OBSERVED, SUBDIR, audit_guest_root,
)
from audit_nexium_guest_last_buffer_return import (
    COMPLETE, audit_guest as audit_last_page,
)

SCHEMA="vh-guest-worker-stop-mailbox-observation/v1"
FILE="audio-exit-worker-stop-000.csv"
HEADER=b"event,guest_monotonic_ns\nworker_stop_observed,"
NOT_OBSERVED="GUEST_WORKER_STOP_MARKER_NOT_OBSERVED"
VERIFIED="GUEST_WORKER_STOP_OBSERVED_BETWEEN_LAST_PAGE_AND_CLEANUP"


def audit_worker_stop_csv(raw:bytes, exit_report:dict,
                          last_page_report:dict) -> dict:
    if not isinstance(raw,bytes) or not raw.startswith(HEADER) or (
            len(raw)>128 or not raw.endswith(b"\n") or
            b"\r" in raw or b"\x00" in raw):
        raise ExitTimelineError("noncanonical original guest worker stop marker")
    b=raw[len(HEADER):-1]
    if not b or not b.isascii() or not b.isdigit() or (
            len(b)>1 and b[:1]==b"0"):
        raise ExitTimelineError("noncanonical guest monotonic stop timestamp")
    stamp=int(b)
    if stamp>2**64-1:
        raise ExitTimelineError("worker stop clock exceeds uint64")
    if exit_report.get("result")!=OBSERVED or (
            last_page_report.get("result")!=COMPLETE):
        raise ExitTimelineError("authentic exit or last page source not observed")
    if (last_page_report.get("original_guest_exit_csv_sha256")!=
            exit_report.get("guest_exit_csv_sha256")):
        raise ExitTimelineError("last-page source bound to different exit witness")
    times=exit_report["guest_monotonic_timestamps_ns"]
    plus,stop,cleanup,closed,joined=(
        times[k] for k in ("plus_observed","stop_requested",
                            "worker_cleanup_entered","audout_closed",
                            "worker_joined"))
    if not 0<plus<stop<cleanup<closed<joined:
        raise ExitTimelineError("guest exit software timestamps out of order")
    page=last_page_report.get("last_page_return_guest_ns")
    if (type(page) is not int or page<=0 or page>cleanup
            or last_page_report.get("last_page_relative_to_Plus_ns")!=page-plus):
        raise ExitTimelineError("no validated guest audout final buffer return")

    result={
        "schema":SCHEMA,
        "original_guest_worker_stop_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "source_guest_exit_csv_sha256":exit_report["guest_exit_csv_sha256"],
        "source_last_page_csv_sha256":
            last_page_report["original_guest_page_witness_sha256"],
        "worker_stop_observation_guest_ns":stamp if stamp else None,
        "last_audout_buffer_return_guest_ns":page,
        "guest_stop_requested_ns":stop,
        "guest_worker_cleanup_entered_ns":cleanup,
        "guest_stop_requested_to_last_page_return_ns":page-stop,
        "guest_software_stop_observation_not_DAC_audio_drain":True,
        "last_buffer_return_not_speaker_playback":True,
        "guest_to_host_PCM_sample_clock_calibrated":False,
        "audible_dropout_or_original_soundtrack_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }
    if not stamp:
        result.update({
            "result":NOT_OBSERVED,
            "stop_request_to_worker_observation_ns":None,
            "last_page_return_to_worker_observation_ns":None,
            "worker_observation_to_cleanup_ns":None,
        })
        return result
    if not stop<=page<=stamp<=cleanup:
        raise ExitTimelineError("guest worker stop marker not after last page and before cleanup")
    result.update({
        "result":VERIFIED,
        "stop_request_to_worker_observation_ns":stamp-stop,
        "last_page_return_to_worker_observation_ns":stamp-page,
        "worker_observation_to_cleanup_ns":cleanup-stamp,
    })
    return result


def audit_guest_root(root:Path) -> tuple[dict,bytes | None]:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("unsafe guest SD root")
    source=root/SUBDIR/FILE
    if not source.exists():
        return ({
            "schema":SCHEMA,
            "result":"GUEST_WORKER_STOP_SD_NOT_OBSERVED",
            "original_worker_stop_source_observed":False,
            "guest_to_host_PCM_sample_clock_calibrated":False,
            "audible_dropout_or_original_soundtrack_verified":False,
            "physical_Nintendo_Switch_audio_tested":False,
        },None)
    if source.is_symlink() or not source.is_file() or (
            len(list((root/SUBDIR).glob("audio-exit-worker-stop-*.csv")))!=1):
        raise ExitTimelineError("ambiguous or symlinked original guest worker stop")
    exit_r=audit_guest_root_exit(root)
    page_r=audit_last_page(root)
    raw=source.read_bytes()
    r=audit_worker_stop_csv(raw,exit_r,page_r)
    r["original_worker_stop_source_observed"]=True
    r["original_worker_stop_source_path"]=str(SUBDIR/FILE)
    return r,raw


# Separate alias avoids shadowing the auditor entrypoint's name.
audit_guest_root_exit=audit_guest_root  # replaced below by source import
from audit_nexium_guest_exit_timeline import audit_guest_root as audit_guest_root_exit


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-original",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if (a.output.exists() or a.output.is_symlink() or
                a.output_original.exists() or a.output_original.is_symlink()):
            raise ExitTimelineError("refuse to overwrite original guest software evidence")
        if a.guest_root_file.is_symlink() or not a.guest_root_file.is_file():
            raise ExitTimelineError("original NeXium guest root locator missing")
        root=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("invalid guest SD root locator")
        report,raw=audit_guest_root(Path(root))
        if raw is not None:
            a.output_original.parent.mkdir(parents=True,exist_ok=True)
            with a.output_original.open("xb") as out:
                out.write(raw)
            if a.output_original.read_bytes()!=raw:
                raise ExitTimelineError("original guest worker stop CSV copy changed")
            report["original_worker_stop_csv_bytes_preserved"]=True
        else:
            report["original_worker_stop_csv_bytes_preserved"]=False
        a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":report["result"],
            "original_guest_stop_source_saved":bool(raw is not None),
            "guest_software_stop_verified":report["result"]==VERIFIED,
            "audible_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as e:
        print(json.dumps({"result":"STAGE317_WORKER_STOP_OBSERVATION_NOT_VERIFIED",
                          "error":str(e)},sort_keys=True),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
