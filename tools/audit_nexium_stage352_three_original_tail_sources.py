#!/usr/bin/env python3
"""Stage352: independently re-open three SHA-pinned original guest CSVs.

Stage313 tail evidence, Stage348 software PCM ownership and Stage351 actual
bounded exit-tail reason must agree on the SAME real NeXium run.  Replaying
archived originals does not claim DAC/speaker audio or uniquely explain a
different older run's abandoned lease.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_stage350_original_tail_vs_lease import read_tail_original, safe_file
from compare_nexium_stage349_original_lease_cohorts import read_original
from audit_nexium_guest_tail_reason_stage351 import (
    audit_source as audit_tail_reason,
    audit_existing_original_sources,
    SCHEMA as STAGE351_SCHEMA,
    VERIFIED as STAGE351_VERIFIED,
)

SCHEMA="vh-stage352-triple-original-guest-lease-tail-reason/v1"
VERIFIED="THREE_ORIGINAL_GUEST_PCM_TAIL_SOFTWARE_SOURCES_REAUDITED"
FALSE_FLAGS=(
    "one_to_one_causal_attribution_proven",
    "physical_Nintendo_Switch_audio_tested",
    "DAC_or_speaker_audio_verified",
)
TRUE_FLAGS=(
    "original_guest_tail_reason_bytes_preserved",
    "original_guest_tail_reason_source_observed",
    "bound_to_original_stage313_tail_observation",
    "bound_to_original_stage348_lease_observation",
)
FIELDS=(
    "reason_code","reason_name","tail_attempted",
    "tail_descriptor_return_confirmed","tail_lease_acquired",
    "lease_pages_acquired","lease_pages_released","abandoned_sessions",
)


def reaudited_archive(paths: dict[str,Path], pins: dict[str,str], run_id: int)->dict:
    if not isinstance(run_id,int) or run_id<=0:
        raise ValueError("require original valid NeXium run id")
    for key in ("tail","lease","reason"):
        if not re.fullmatch(r"[a-f0-9]{64}",pins[key]):
            raise ValueError("original SHA-256 must be pinned")
    for p in paths.values():
        safe_file(p)
    tail=read_tail_original(
        paths["tail"],paths["stage313"],paths["stage314"],pins["tail"]
    )
    lease=read_original(paths["lease"],paths["stage348"],pins["lease"])
    raw=paths["reason"].read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pins["reason"]:
        raise ValueError("Stage351 original reason CSV differs from SHA pin")
    report313=json.loads(paths["stage313"].read_text(encoding="utf-8"))
    report348=json.loads(paths["stage348"].read_text(encoding="utf-8"))
    report351=json.loads(paths["stage351"].read_text(encoding="utf-8"))
    if not all(isinstance(v,dict) for v in (report313,report348,report351)):
        raise ValueError("source receipts must be structured JSON objects")
    linked=audit_existing_original_sources(
        paths["tail"].read_bytes(),paths["lease"].read_bytes(),
        report313,report348,
    )
    observed=audit_tail_reason(raw,report313,report348)
    if (report351.get("schema")!=STAGE351_SCHEMA
        or report351.get("result")!=STAGE351_VERIFIED
        or report351.get("original_guest_tail_reason_csv_sha256")!=pins["reason"]):
        raise ValueError("Stage351 original reason receipt identity mismatch")
    for key in FIELDS:
        if (type(report351.get(key)) is not type(observed[key])
            or report351[key]!=observed[key]):
            raise ValueError("Stage351 original guest field differs from receipt: "+key)
    for key in TRUE_FLAGS:
        if report351.get(key) is not True:
            raise ValueError("Stage351 receipt source-preservation flag missing")
    for key in FALSE_FLAGS:
        if report351.get(key) is not False:
            raise ValueError("Stage351 receipt has fabricated causal/hardware proof")
    if (observed["lease_pages_acquired"]!=lease["lease_pages_acquired"]
        or observed["lease_pages_released"]!=lease["lease_pages_released"]
        or observed["abandoned_sessions"]!=lease["abandoned_sessions"]
        or observed["tail_attempted"]!=tail["bounded_exit_tail_attempted"]
        or observed["tail_descriptor_return_confirmed"]!=
           tail["bounded_exit_tail_return_confirmed"]
        or not linked["prior_stage313_and_stage348_original_bytes_reaudited"]):
        raise ValueError("three independent original guest source families disagree")
    return {
        "schema":SCHEMA,
        "result":VERIFIED,
        "original_neXium_run_id":run_id,
        "original_guest_csv_sha256":{
            "stage313_last_audio_page_and_tail":pins["tail"],
            "stage348_software_PCM_lease":pins["lease"],
            "stage351_exit_tail_reason":pins["reason"],
        },
        "tail_reason_code":observed["reason_code"],
        "tail_reason_name":observed["reason_name"],
        "tail_attempted":observed["tail_attempted"],
        "tail_descriptor_return_confirmed":observed["tail_descriptor_return_confirmed"],
        "lease_pages_acquired":observed["lease_pages_acquired"],
        "lease_pages_released":observed["lease_pages_released"],
        "abandoned_sessions":observed["abandoned_sessions"],
        "exact_archived_original_CSV_bytes_reaudited":True,
        "three_distinct_guest_source_receipts_matched":True,
        "independent_of_any_other_neXium_run":True,
        "older_unconfirmed_tail_failure_cause_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "DAC_or_speaker_audio_verified":False,
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("tail","lease","reason"):
        p.add_argument("--"+key+"-csv",required=True,type=Path)
        p.add_argument("--"+key+"-sha256",required=True)
    for key in ("stage313","stage314","stage348","stage351"):
        p.add_argument("--"+key,required=True,type=Path)
    p.add_argument("--original-run-id",required=True,type=int)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite original run report")
        paths={key:getattr(a,key+"_csv") for key in ("tail","lease","reason")}
        paths.update({key:getattr(a,key) for key in (
            "stage313","stage314","stage348","stage351"
        )})
        pins={key:getattr(a,key+"_sha256") for key in ("tail","lease","reason")}
        result=reaudited_archive(paths,pins,a.original_run_id)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":VERIFIED,
            "reason":result["tail_reason_name"],
            "acquired":result["lease_pages_acquired"],
            "released":result["lease_pages_released"],
            "abandoned":result["abandoned_sessions"],
            "older_run_cause_proven":False,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE352_TRIPLE_ORIGINAL_SOURCE_REAUDIT_FAILED",
            "error_kind":type(exc).__name__,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
