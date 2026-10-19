#!/usr/bin/env python3
"""Stage357: independently validate actual guest post-join audout wait Result.

Reopens original raw Stage351 and Stage357 guest CSV bytes, source-pins
the earlier verified Stage351 receipt and preserves the new original bytes
without changing any original prior-stage source or asserting speaker audio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from audit_nexium_guest_exit_timeline import SUBDIR,ExitTimelineError
from audit_nexium_guest_tail_reason_stage351 import (
    SCHEMA as STAGE351_SCHEMA,VERIFIED as STAGE351_VERIFIED,
    SOURCE as STAGE351_SOURCE,
)
SOURCE="audio-exit-tail-wait-result-000.csv"
SCHEMA="vh-stage357-original-guest-raw-exit-tail-wait-result/v1"
VERIFIED="ORIGINAL_NEIXUM_GUEST_EXIT_TAIL_WAIT_RESULT_SOURCE_VERIFIED"
LABELS=(
    "software_wait_result_only","wait_result_observed",
    "audout_wait_result_raw","stage351_tail_reason_code",
)
def regular(path:Path)->bool:
    return path.is_file() and not any(p.is_symlink() for p in (path,*path.parents))

def parse_source(raw:bytes,receipt:dict)->dict:
    if (not isinstance(raw,bytes) or len(raw)>256
        or not raw.startswith(b"scope,value\n")
        or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw):
        raise ExitTimelineError("invalid canonical guest raw wait Result source")
    lines=raw[len(b"scope,value\n"):].splitlines(keepends=True)
    if len(lines)!=len(LABELS):
        raise ExitTimelineError("wrong number of Stage357 rows")
    vals={}
    for name,line in zip(LABELS,lines):
        prefix=(name+",").encode("ascii")
        if (not line.startswith(prefix) or line.count(b",")!=1
            or not line.endswith(b"\n")):
            raise ExitTimelineError("noncanonical Stage357 original row")
        token=line[len(prefix):-1]
        if (not token or not token.isascii() or not token.isdigit()
            or (len(token)>1 and token.startswith(b"0"))):
            raise ExitTimelineError("Stage357 source integer not canonical")
        n=int(token)
        if n>2**32-1:
            raise ExitTimelineError("Stage357 raw unsigned Result overflow")
        vals[name]=n
    code=vals["stage351_tail_reason_code"]
    observed=vals["wait_result_observed"]
    raw_result=vals["audout_wait_result_raw"]
    if (vals["software_wait_result_only"]!=1 or code>7
        or observed not in (0,1)
        or (code<=3 and (observed!=0 or raw_result!=0))
        or (code>=4 and observed!=1)
        or (code==4 and raw_result==0)
        or (code>=5 and raw_result!=0)):
        raise ExitTimelineError("Stage357 Result contradicts Stage351 wait outcome")
    if (not isinstance(receipt,dict)
        or receipt.get("schema")!=STAGE351_SCHEMA
        or receipt.get("result")!=STAGE351_VERIFIED
        or type(receipt.get("reason_code")) is not int
        or receipt["reason_code"]!=code
        or receipt.get("bound_to_original_stage313_tail_observation") is not True
        or receipt.get("bound_to_original_stage348_lease_observation") is not True
        or receipt.get("prior_stage313_and_stage348_original_bytes_reaudited") is not True
        or receipt.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("Stage357 disagrees with verified Stage351 source")
    return {
        "schema":SCHEMA,"result":VERIFIED,
        "original_guest_wait_result_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "original_guest_wait_result_source_observed":True,
        "original_guest_wait_result_bytes_preserved":True,
        "stage351_reason_code":code,
        "wait_result_observed":bool(observed),
        "audout_wait_result_raw":raw_result,
        "original_stage351_source_sha256":
            receipt["original_guest_tail_reason_csv_sha256"],
        "raw_result_is_software_service_status_only":True,
        "underlying_result_symbolic_meaning_proven":False,
        "audible_dropout_or_DAC_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def audit_guest(root:Path,receipt:dict)->tuple[dict,bytes]:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ExitTimelineError("guest root missing or linked")
    directory=root
    for segment in SUBDIR.parts:
        directory=directory/segment
        if directory.is_symlink() or not directory.is_dir():
            raise ExitTimelineError("guest SD path segment missing or linked")
    matches=list(directory.glob("audio-exit-tail-wait-result-*.csv"))
    target=directory/SOURCE
    if len(matches)!=1 or matches[0]!=target or not regular(target):
        raise ExitTimelineError("Stage357 guest source missing or ambiguous")
    raw=target.read_bytes()
    doc=parse_source(raw,receipt)
    doc["original_guest_source_relative_path"]=str(SUBDIR/SOURCE)
    return doc,raw

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--stage351",type=Path,required=True)
    p.add_argument("--stage351-original",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-original",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output==a.output_original:
            raise ExitTimelineError("output names must differ")
        for dest in (a.output,a.output_original):
            if dest.exists() or dest.is_symlink():
                raise ExitTimelineError("refuse overwrite source evidence")
        for source in (a.guest_root_file,a.stage351,a.stage351_original):
            if not regular(source):
                raise ExitTimelineError("missing or linked verified input")
        root=a.guest_root_file.read_text(encoding="utf-8").strip()
        if not root.startswith("/") or "\n" in root or "\x00" in root:
            raise ExitTimelineError("invalid original guest root locator")
        report=json.loads(a.stage351.read_text(encoding="utf-8"))
        old=a.stage351_original.read_bytes()
        if (not isinstance(report,dict)
            or hashlib.sha256(old).hexdigest()!=
                report.get("original_guest_tail_reason_csv_sha256")
            or not old.startswith(b"scope,value\n")
            or report.get("original_guest_tail_reason_bytes_preserved") is not True):
            raise ExitTimelineError("Stage351 original CSV mismatch")
        doc,raw=audit_guest(Path(root),report)
        for dest in (a.output,a.output_original):
            dest.parent.mkdir(parents=True,exist_ok=True)
            if any(q.is_symlink() for q in (dest,*dest.parents)):
                raise ExitTimelineError("linked verified output destination")
        with a.output_original.open("xb") as out:
            out.write(raw)
        if a.output_original.read_bytes()!=raw:
            raise ExitTimelineError("Stage357 original CSV copy changed")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(doc,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,
            "stage351_reason_code":doc["stage351_reason_code"],
            "audout_wait_result_raw":doc["audout_wait_result_raw"],
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"ORIGINAL_GUEST_EXIT_TAIL_WAIT_RESULT_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
