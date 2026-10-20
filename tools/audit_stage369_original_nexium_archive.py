#!/usr/bin/env python3
"""Stage369: re-open a finished NeXium run's *original* Stage368 archive.

Input JSON files must be independently fetched from GitHub Actions in the
same CI job, not reconstructed from a prior verification receipt. An
already-green Stage368 step is not, by itself, a replay of preserved bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_stage368_wait_descriptor import parse, compare, NAMES

RUN_ID = 39388027581
EVIDENCE_NAME = "nexium-runtime-evidence"
EXPECTED_368 = "STAGE368_SAME_RUN_ORIGINAL_GUEST_WAIT_DESCRIPTOR_BOUND_TO_351_357_NRO"
VERIFIED = "STAGE369_ORIGINAL_NEXIUM_ARCHIVE_STAGE368_REPLAYED"
STEPS = (
    "Stage351 verify original post-join tail failure cause against old source receipts",
    "Stage357 independently verify original raw audoutWait Result against Stage351",
    "Stage368 bind one original returned-descriptor tuple to same-run NeXium NRO",
)
FILES = {
    "reason": "audio-exit-tail-reason-000.csv",
    "result": "audio-exit-tail-wait-result-000.csv",
    "descriptor": "audio-exit-wait-descriptor-000.csv",
}
REPORTS = {
    "reason": "guest-exit-tail-reason-stage351.json",
    "result": "guest-exit-tail-wait-result-stage357.json",
    "descriptor": "guest-exit-wait-descriptor-stage368.json",
}


def ensure(condition: bool, why: str) -> None:
    if not condition:
        raise ValueError(why)


def regular(path: Path, cap: int) -> bool:
    return (path.is_file() and not any(x.is_symlink() for x in (path,*path.parents))
            and 0 < path.stat().st_size <= cap)


def loaded(path: Path, cap: int=65536) -> dict:
    ensure(regular(path,cap), "missing, linked or oversized metadata/receipt")
    value=json.loads(path.read_text(encoding="utf-8"))
    ensure(type(value) is dict,"metadata/receipt not a JSON object")
    return value


def original(root: Path, filename: str, cap: int=1024) -> bytes:
    p=root/"runtime-evidence"/filename
    ensure(regular(p,cap),"missing, linked or oversized original evidence: "+filename)
    return p.read_bytes()


def verify(archive:Path, run:dict, jobs:dict, artifact:dict)->dict:
    ensure(archive.is_dir() and not any(p.is_symlink() for p in (archive,*archive.parents)),
           "missing or linked original artifact directory")
    ensure(run.get("id")==RUN_ID and type(run.get("id")) is int
           and run.get("status")=="completed"
           and run.get("repository",{}).get("full_name") ==
                "stanmasked/vandal-hearts-switch-remaster"
           and type(run.get("run_attempt")) is int
           and run["run_attempt"]>0
           and type(run.get("head_sha")) is str
           and len(run["head_sha"])==40
           and all(c in "0123456789abcdef" for c in run["head_sha"]),
           "original run not completed, source identity invalid")
    ensure(type(jobs.get("jobs")) is list,"missing current-run GitHub job steps")
    names={}
    for job in jobs["jobs"]:
        if type(job) is not dict: raise ValueError("invalid GitHub job")
        name=job.get("name")
        ensure(type(name) is str and name not in names,"duplicated/unnamed GitHub job")
        names[name]=job
    build=names.get("Build libnx NRO for runtime smoke test")
    nexi=names.get("Launch current-workflow audout NRO in NeXium")
    ensure(type(build) is dict and build.get("conclusion")=="success"
           and type(nexi) is dict and nexi.get("run_id")==RUN_ID
           and type(nexi.get("steps")) is list
           and nexi.get("status")=="completed",
           "original build/NeXium job identity not verified")
    steps={}
    for step in nexi["steps"]:
        ensure(type(step) is dict and type(step.get("name")) is str
               and step["name"] not in steps,"missing/duplicated step name")
        steps[step["name"]]=step
    for name in STEPS:
        ensure(steps.get(name,{}).get("conclusion")=="success",
               "original service guest capture evidence step not successful: "+name)
    ensure(artifact.get("name")==EVIDENCE_NAME
           and type(artifact.get("id")) is int and artifact["id"]>0
           and artifact.get("expired") is False
           and type(artifact.get("size_in_bytes")) is int
           and artifact["size_in_bytes"]>0
           and type(artifact.get("digest")) is str
           and artifact["digest"].startswith("sha256:")
           and len(artifact["digest"])==71
           and type(artifact.get("workflow_run")) is dict
           and artifact["workflow_run"].get("id")==RUN_ID
           and artifact["workflow_run"].get("head_sha")==run["head_sha"],
           "wrong/orphaned GitHub Actions archive metadata")
    preflight=loaded(archive/"integrated-nro-preflight.json")
    ensure(preflight.get("result")=="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
           and preflight.get("git_sha")==run["head_sha"]
           and type(preflight.get("run_id")) is int
           and preflight["run_id"]==RUN_ID
           and type(preflight.get("run_attempt")) is int
           and preflight["run_attempt"]==run["run_attempt"]
           and type(preflight.get("nro_sha256")) is str
           and len(preflight["nro_sha256"])==64
           and type(preflight.get("nro_bytes")) is int
           and preflight["nro_bytes"]>=1024,
           "NeXium original archive preflight not bound to same build/run")
    orig={}
    parsed={}
    hashes={}
    for kind,name in FILES.items():
        raw=original(archive,name)
        orig[kind]=raw
        parsed[kind]=parse(raw,kind)
        hashes[kind]=hashlib.sha256(raw).hexdigest()
    checked=compare(parsed["reason"],parsed["result"],parsed["descriptor"])
    claims={kind:loaded(archive/"runtime-evidence"/fname)
            for kind,fname in REPORTS.items()}
    a,b,c=claims["reason"],claims["result"],claims["descriptor"]
    ensure(a.get("result")=="ORIGINAL_GUEST_EXIT_TAIL_CAUSE_SOURCE_VERIFIED"
           and a.get("prior_stage313_and_stage348_original_bytes_reaudited") is True
           and a.get("original_guest_tail_reason_csv_sha256")==hashes["reason"]
           and a.get("physical_Nintendo_Switch_audio_tested") is False
           and b.get("result")=="ORIGINAL_NEIXUM_GUEST_EXIT_TAIL_WAIT_RESULT_SOURCE_VERIFIED"
           and b.get("original_guest_wait_result_csv_sha256")==hashes["result"]
           and b.get("original_stage351_source_sha256")==hashes["reason"]
           and b.get("physical_Nintendo_Switch_audio_tested") is False
           and c.get("result")==EXPECTED_368
           and c.get("stage368_guest_original_source_bound_to_verified_prior_originals") is True
           and c.get("original_neXium_archive_proven") is True
           and c.get("source_sha256")==hashes
           and c.get("neXium_original_guest_run_id")==RUN_ID
           and c.get("neXium_nro_git_sha")==run["head_sha"]
           and c.get("neXium_nro_sha256")==preflight["nro_sha256"]
           and c.get("neXium_nro_run_attempt")==run["run_attempt"]
           and c.get("raw_wait_result")==checked["raw_wait_result"]
           and c.get("reported_released_count")==checked["reported_released_count"]
           and c.get("returned_pointer_present")==checked["returned_pointer_present"]
           and c.get("returned_pointer_matches_submitted")==
                    checked["returned_pointer_matches_submitted"]
           and c.get("old_0xEA01_cause_proven") is False
           and c.get("physical_Nintendo_Switch_audio_tested") is False
           and c.get("kernel_wait_subcall_uniquely_proven") is False
           and c.get("actual_queue_depth_measured") is False,
           "Stage368 receipt contradicts the independently reopened original bytes")
    ensure(type(a.get("reason_code")) is int
           and a["reason_code"]==checked["tail_reason_code"]
           and type(b.get("stage351_reason_code")) is int
           and b["stage351_reason_code"]==checked["tail_reason_code"]
           and type(b.get("audout_wait_result_raw")) is int
           and b["audout_wait_result_raw"]==checked["raw_wait_result"],
           "prior attested Stage351/357 receipt contradictions")
    return {
        "schema":"vh-stage369-independent-github-original-stage368-artifact/v1",
        "result":VERIFIED,
        "source_run_id":RUN_ID,
        "source_attempt":run["run_attempt"],
        "source_git_sha":run["head_sha"],
        "source_artifact_id":artifact["id"],
        "github_reported_archive_digest":artifact["digest"],
        "same_run_nro_sha256":preflight["nro_sha256"],
        "independently_reopened_original_csv_sha256":hashes,
        "stage351_reason_code":checked["tail_reason_code"],
        "service_result_raw":checked["raw_wait_result"],
        "service_returned_descriptor_count":checked["reported_released_count"],
        "returned_pointer_present":checked["returned_pointer_present"],
        "returned_pointer_matches_submitted":checked["returned_pointer_matches_submitted"],
        "original_stage368_step_succeeded":True,
        "whole_runtime_run_succeeded":run.get("conclusion")=="success",
        "physical_Switch_sound_tested":False,
        "old_0xEA01_cause_proven":False,
        "exit_queue_depth_measured":False,
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-archive",type=Path,required=True)
    p.add_argument("--run-json",type=Path,required=True)
    p.add_argument("--jobs-json",type=Path,required=True)
    p.add_argument("--artifact-json",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        ensure(not a.output.exists() and not a.output.is_symlink(),
               "refuse overwriting previous verdict")
        result=verify(a.original_archive,loaded(a.run_json),
               loaded(a.jobs_json),loaded(a.artifact_json))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        ensure(not any(x.is_symlink() for x in (a.output,*a.output.parents)),
               "linked verdict location")
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":VERIFIED,
              "service_result_raw":result["service_result_raw"],
              "service_returned_descriptor_count":result["service_returned_descriptor_count"],
              "physical_switch_sound_tested":False},sort_keys=True))
        return 0
    except (OSError,UnicodeError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({"result":"STAGE369_ORIGINAL_ARTIFACT_NOT_VERIFIED",
              "error_kind":type(exc).__name__,"old_timeout_cause_proven":False},
              sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
