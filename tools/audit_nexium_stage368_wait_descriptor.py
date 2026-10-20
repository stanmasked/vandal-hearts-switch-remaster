#!/usr/bin/env python3
"""Stage368: source-only cross-check of three files from ONE future guest directory.

Synthetic tests do not establish an authentic NeXium run. Independent archive
attestation is required before calling these values genuine guest evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

NAMES = {
    "reason": "audio-exit-tail-reason-000.csv",
    "result": "audio-exit-tail-wait-result-000.csv",
    "descriptor": "audio-exit-wait-descriptor-000.csv",
}
LABELS = {
    "reason": (
        "software_exit_tail_reason_only", "tail_reason_code", "tail_attempted",
        "tail_descriptor_return_confirmed", "tail_lease_acquired",
        "lease_pages_acquired", "lease_pages_released", "abandoned_sessions",
    ),
    "result": (
        "software_wait_result_only", "wait_result_observed",
        "audout_wait_result_raw", "stage351_tail_reason_code",
    ),
    "descriptor": (
        "software_wait_descriptor_only", "wait_observed",
        "audout_wait_result_raw", "released_count_reported",
        "returned_pointer_present", "returned_pointer_matches_submitted",
        "stage351_tail_reason_code", "stage357_raw_result_crosschecked",
    ),
}
VERDICT="STAGE368_SAME_DIRECTORY_SOFTWARE_WAIT_TUPLE_INTERNALLY_CONSISTENT_UNATTESTED"

def parse(raw: bytes, kind: str) -> dict:
    if (type(raw) is not bytes or not 0 < len(raw) <= 512
        or not raw.startswith(b"scope,value\n")
        or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw):
        raise ValueError("noncanonical guest CSV bytes")
    rows=raw[len(b"scope,value\n"):].splitlines(keepends=True)
    if len(rows)!=len(LABELS[kind]):
        raise ValueError("wrong number of original rows")
    values={}
    for key,line in zip(LABELS[kind],rows):
        prefix=(key+",").encode("ascii")
        if not line.startswith(prefix) or line.count(b",")!=1 or not line.endswith(b"\n"):
            raise ValueError("wrong row label/order or extra columns")
        n=line[len(prefix):-1]
        if (not n or not n.isascii() or not n.isdigit() or
            (len(n)>1 and n.startswith(b"0"))):
            raise ValueError("noncanonical unsigned integer")
        val=int(n)
        if val>(2**64-1 if key in ("lease_pages_acquired", "lease_pages_released")
                else 2**32-1):
            raise ValueError("unsigned guest field overflow")
        values[key]=val
    return values

def compare(reason:dict,wait:dict,desc:dict)->dict:
    code=reason["tail_reason_code"]
    a=reason["lease_pages_acquired"]
    r=reason["lease_pages_released"]
    b=reason["abandoned_sessions"]
    seen=int(code>=4)
    if (code>7 or reason["software_exit_tail_reason_only"]!=1
        or reason["tail_attempted"]!=int(code!=0)
        or reason["tail_descriptor_return_confirmed"]!=int(code==7)
        or reason["tail_lease_acquired"]!=int(code>=3)
        or a==0 or a==2**64-1 or r==2**64-1 or
        r>a or a-r!=b or b==2**32-1
        or (3<=code<=6 and not b)
        or wait["software_wait_result_only"]!=1
        or wait["wait_result_observed"]!=seen
        or wait["stage351_tail_reason_code"]!=code
        or desc["software_wait_descriptor_only"]!=1
        or desc["stage357_raw_result_crosschecked"]!=1
        or desc["stage351_tail_reason_code"]!=code
        or desc["wait_observed"]!=seen
        or wait["audout_wait_result_raw"]!=desc["audout_wait_result_raw"]
        or desc["returned_pointer_present"] not in (0,1)
        or desc["returned_pointer_matches_submitted"] not in (0,1)
        or desc["returned_pointer_matches_submitted"] >
            desc["returned_pointer_present"]
        or (code<=3 and (wait["audout_wait_result_raw"]!=0 or
                         desc["released_count_reported"]!=0 or
                         desc["returned_pointer_present"]!=0))
        or (code==4 and wait["audout_wait_result_raw"]==0)
        or (code>=5 and wait["audout_wait_result_raw"]!=0)
        or (code==5 and desc["released_count_reported"]!=0)
        or (code==6 and desc["released_count_reported"]==0)
        or (code==7 and (desc["released_count_reported"]==0 or
                         desc["returned_pointer_matches_submitted"]!=1))):
        raise ValueError("three original-schema software sources disagree")
    return {
        "schema":"vh-stage368-same-directory-guest-wait-tuple/v1",
        "result":VERDICT,
        "tail_reason_code":code,
        "raw_wait_result":wait["audout_wait_result_raw"],
        "reported_released_count":desc["released_count_reported"] if seen else None,
        "returned_pointer_present":bool(desc["returned_pointer_present"]) if seen else None,
        "returned_pointer_matches_submitted":
            bool(desc["returned_pointer_matches_submitted"]) if seen else None,
        "source_is_same_directory_only":True,
        "original_neXium_archive_proven":False,
        "old_0xEA01_cause_proven":False,
        "actual_queue_depth_measured":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def audit_directory(root:Path)->dict:
    if not root.is_dir() or any(q.is_symlink() for q in (root,*root.parents)):
        raise ValueError("invalid guest root")
    # Search the full one-source extraction; never pick the first hit
    # among duplicates or pair a file from another run's directory.
    files={}
    for kind,name in NAMES.items():
        matches=list(root.rglob(name))
        if len(matches)!=1 or not matches[0].is_file() or any(
            q.is_symlink() for q in (matches[0],*matches[0].parents)
        ):
            raise ValueError("missing, duplicated or linked same-run source: "+name)
        files[kind]=matches[0]
    parents={p.parent.resolve() for p in files.values()}
    if len(parents)!=1:
        raise ValueError("different guest output directories cannot be paired")
    values={}
    hashes={}
    for kind,path in files.items():
        raw=path.read_bytes()
        values[kind]=parse(raw,kind)
        hashes[kind]=hashlib.sha256(raw).hexdigest()
    result=compare(values["reason"],values["result"],values["descriptor"])
    result["source_sha256"]=hashes
    return result

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-original-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("existing verdict cannot be overwritten")
        report=audit_directory(a.guest_original_root)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(q.is_symlink() for q in (a.output,*a.output.parents)):
            raise ValueError("linked output")
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":VERDICT,
                          "original_archive_attested":False,
                          "old_timeout_cause_proven":False},sort_keys=True))
        return 0
    except (ValueError,TypeError,OSError,UnicodeError,KeyError) as exc:
        print(json.dumps({"result":"STAGE368_GUEST_TUPLE_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "actual_audio_proven":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
