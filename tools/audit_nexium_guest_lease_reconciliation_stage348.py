#!/usr/bin/env python3
"""Stage348: strictly source-validate the separate Stage347 guest PCM lease CSV.

Guest software owner counts only; never a DAC queue sample, timestamp mapping
or proof of audible playback. Preserve exact guest source bytes and SHA256.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError

FILE="audio-lease-reconciliation-000.csv"
SCHEMA="vh-stage348-original-software-lease-reconciliation/v1"
VERIFIED="ORIGINAL_GUEST_SOFTWARE_PCM_LEASE_BALANCE_SOURCE_VERIFIED"
KEYS=("software_lease_only","lease_pages_acquired","lease_pages_released",
      "abandoned_sessions","busy_begin_rejections","mismatched_releases",
      "accepted_pages_submitted","submit_failures")
HEADER=b"scope,value\n"
MAX64=2**64-1
MAX32=2**32-1

def audit_source(raw:bytes)->dict:
    if (not isinstance(raw,bytes) or len(raw)>640 or not raw.startswith(HEADER)
        or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw):
        raise ExitTimelineError("invalid guest software lease source encoding")
    lines=raw[len(HEADER):].splitlines(keepends=True)
    if len(lines)!=len(KEYS):
        raise ExitTimelineError("wrong original guest software lease row count")
    values={}
    for label,line in zip(KEYS,lines):
        if not line.endswith(b"\n"):
            raise ExitTimelineError("unterminated original lease row")
        expected=(label+",").encode("ascii")
        if not line.startswith(expected) or line.count(b",")!=1:
            raise ExitTimelineError("noncanonical original lease event order")
        number=line[len(expected):-1]
        if (not number or not number.isascii() or not number.isdigit()
            or (len(number)>1 and number.startswith(b"0"))):
            raise ExitTimelineError("noncanonical software lease source integer")
        value=int(number)
        maximum=MAX64 if label in ("lease_pages_acquired","lease_pages_released",
                                     "accepted_pages_submitted") else MAX32
        if value>maximum:
            raise ExitTimelineError("original lease counter overflow")
        values[label]=value
    a=values["lease_pages_acquired"]
    r=values["lease_pages_released"]
    ab=values["abandoned_sessions"]
    accepted=values["accepted_pages_submitted"]
    if (values["software_lease_only"]!=1
        or a in (0,MAX64) or r==MAX64 or ab==MAX32
        or r>a or a-r!=ab or accepted>r):
        raise ExitTimelineError("original guest software lease lifecycle not balanced")
    return {
        "schema":SCHEMA,"result":VERIFIED,
        "original_guest_software_lease_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "original_guest_software_lease_source_observed":True,
        "original_guest_software_lease_bytes_preserved":True,
        "lease_pages_acquired":a,
        "lease_pages_released":r,
        "abandoned_sessions":ab,
        "busy_begin_rejections":values["busy_begin_rejections"],
        "mismatched_releases":values["mismatched_releases"],
        "accepted_pages_submitted":accepted,
        "submit_failures":values["submit_failures"],
        "only_software_owner_counters_checked":True,
        "playback_at_DAC_or_speaker_verified":False,
        "original_PS1_soundtrack_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def audit_guest(root:Path)->tuple[dict,bytes]:
    if root.is_symlink() or not root.is_dir():
        raise ExitTimelineError("original guest source root missing or linked")
    # Reject indirect symlink escapes anywhere in the guest SD path,
    # not only at the target filename.
    directory=root
    for part in SUBDIR.parts:
        directory=directory/part
        if directory.is_symlink() or not directory.is_dir():
            raise ExitTimelineError("original guest SD directory missing or linked")
    target=directory/FILE
    siblings=list(directory.glob("audio-lease-reconciliation-*.csv"))
    if len(siblings)!=1 or target.is_symlink() or not target.is_file():
        raise ExitTimelineError("missing/ambiguous original lease guest source")
    raw=target.read_bytes()
    d=audit_source(raw)
    d["original_guest_source_relative_path"]=str(SUBDIR/FILE)
    return d,raw

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--output-original",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink() or a.output_original.exists() or a.output_original.is_symlink():
            raise ExitTimelineError("refuse overwrite original lease evidence")
        if a.guest_root_file.is_symlink() or not a.guest_root_file.is_file():
            raise ExitTimelineError("guest root locator missing")
        path=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not path.startswith("/") or "\n" in path or "\x00" in path:
            raise ExitTimelineError("invalid guest root locator")
        doc,raw=audit_guest(Path(path))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output_original.parent.mkdir(parents=True,exist_ok=True)
        with a.output_original.open("xb") as out:out.write(raw)
        if a.output_original.read_bytes()!=raw:
            raise ExitTimelineError("original guest lease evidence mutated")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(doc,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({"result":doc["result"],
                          "software_lease_balance_verified":True,
                          "physical_Nintendo_Switch_audio_tested":False}))
        return 0
    except (ValueError,TypeError,KeyError,UnicodeError,OSError) as exc:
        print(json.dumps({"result":"ORIGINAL_GUEST_SOFTWARE_LEASE_SOURCE_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "physical_Nintendo_Switch_audio_tested":False}))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
