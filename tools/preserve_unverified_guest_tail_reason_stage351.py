#!/usr/bin/env python3
"""Stage351 failure-only guest diagnostic quarantine, never source verification.

Preserves at most 512 printable ASCII bytes from the unverified original guest
SD CSV if strict cross-audit fails. It does NOT decode/endorse a reason code or
override the failed audit. No original PCM/music data can enter this artifact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_guest_exit_timeline import SUBDIR, ExitTimelineError
from audit_nexium_guest_tail_reason_stage351 import SOURCE

SCHEMA="vh-stage351-failure-only-original-guest-source-quarantine/v1"
RESULT="UNVERIFIED_GUEST_STAGE351_CSV_BYTES_QUARANTINED"
MAX_BYTES=512

def _safe_existing_file(p:Path)->bool:
    return p.is_file() and not any(q.is_symlink() for q in (p,*p.parents))

def capture(locator:Path, csv_dest:Path, report_dest:Path, run_id:int)->dict:
    if type(run_id) is not int or run_id<=0:
        raise ExitTimelineError("require a positive original workflow run ID")
    if not _safe_existing_file(locator):
        raise ExitTimelineError("missing or linked guest SD locator")
    for p in (csv_dest,report_dest):
        if p.exists() or p.is_symlink():
            raise ExitTimelineError("refuse overwrite unverified forensic source")
    if csv_dest==report_dest:
        raise ExitTimelineError("cannot reuse forensic output path")
    text=locator.read_text(encoding="utf-8")
    if (not text or text!=text.strip() or "\r" in text or
        "\n" in text or "\x00" in text):
        raise ExitTimelineError("invalid original guest root locator")
    root=Path(text)
    if not root.is_absolute() or not root.is_dir() or any(
        part.is_symlink() for part in (root,*root.parents)
    ):
        raise ExitTimelineError("missing or linked original guest root")
    directory=root
    for part in SUBDIR.parts:
        directory=directory/part
        if not directory.is_dir() or directory.is_symlink():
            raise ExitTimelineError("missing or linked guest SD segment")
    matches=list(directory.glob("audio-exit-tail-reason-*.csv"))
    source=directory/SOURCE
    if len(matches)!=1 or matches[0]!=source or not _safe_existing_file(source):
        raise ExitTimelineError("ambiguous/missing original Stage351 guest CSV")
    size=source.stat().st_size
    if size==0 or size>MAX_BYTES:
        raise ExitTimelineError("refuse oversized/empty unknown guest bytes")
    raw=source.read_bytes()
    # Only a tiny ASCII diagnostic CSV, not arbitrary guest memory or PCM.
    if (len(raw)!=size or len(raw)>MAX_BYTES or
        not raw.startswith(b"scope,value\n") or
        not raw.endswith(b"\n") or
        any(b not in range(32,127) and b not in (10,13) for b in raw)):
        raise ExitTimelineError("untrusted source is not printable diagnostics")
    for p in (csv_dest,report_dest):
        p.parent.mkdir(parents=True,exist_ok=True)
        if any(q.is_symlink() for q in (p,*p.parents)):
            raise ExitTimelineError("linked quarantine destination")
    receipt={
        "schema":SCHEMA,
        "result":RESULT,
        "workflow_run_id":run_id,
        "original_guest_relative_path":str(SUBDIR/SOURCE),
        "quarantined_guest_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "quarantined_guest_byte_size":len(raw),
        "bounded_printable_source_only":True,
        "guest_source_authenticated_against_stage313_and_348":False,
        "stage351_reason_code_validated":False,
        "one_to_one_failure_cause_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "DAC_or_speaker_playback_verified":False,
    }
    with csv_dest.open("xb") as out:
        out.write(raw)
    if csv_dest.read_bytes()!=raw:
        raise ExitTimelineError("original quarantine copy changed")
    with report_dest.open("x",encoding="utf-8") as out:
        json.dump(receipt,out,sort_keys=True,indent=2)
        out.write("\n")
    return receipt

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--output-original",type=Path,required=True)
    p.add_argument("--output-report",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    a=p.parse_args(argv)
    try:
        doc=capture(a.guest_root_file,a.output_original,a.output_report,a.run_id)
        print(json.dumps({
            "result":RESULT,
            "sha256":doc["quarantined_guest_csv_sha256"],
            "stage351_reason_code_validated":False,
            "physical_Nintendo_Switch_audio_tested":False
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError) as exc:
        print(json.dumps({
            "result":"NO_UNVERIFIED_GUEST_CSV_QUARANTINED",
            "error_kind":type(exc).__name__,
            "stage351_reason_code_validated":False,
            "physical_Nintendo_Switch_audio_tested":False
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
