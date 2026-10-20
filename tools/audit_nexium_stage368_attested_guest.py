#!/usr/bin/env python3
"""Stage368: provenance-bound current NeXium guest descriptor tuple.

The Stage351 and Stage357 original guests must already have passed their
independent source audits. This additional receipt cross-checks the same
isolated SD directory and source-bound NRO without reclassifying older runs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_stage368_wait_descriptor import audit_directory, VERDICT as FORMAT_VERDICT

VERDICT = "STAGE368_SAME_RUN_ORIGINAL_GUEST_WAIT_DESCRIPTOR_BOUND_TO_351_357_NRO"
EXPECTED_S351 = "ORIGINAL_GUEST_EXIT_TAIL_CAUSE_SOURCE_VERIFIED"
EXPECTED_S357 = "ORIGINAL_NEIXUM_GUEST_EXIT_TAIL_WAIT_RESULT_SOURCE_VERIFIED"
EXPECTED_NRO = "SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"

def demand(condition: bool, explanation: str) -> None:
    if not condition:
        raise ValueError(explanation)

def regular(path: Path) -> bool:
    return path.is_file() and not any(p.is_symlink() for p in (path,*path.parents))

def load_json(path: Path) -> dict:
    demand(regular(path) and path.stat().st_size<8192,"missing/linked/oversized receipt")
    v=json.loads(path.read_text(encoding="utf-8"))
    demand(type(v) is dict,"invalid source receipt JSON")
    return v

def attest(source_root: Path, guest_root: Path, run_id: int,
           git_sha: str, attempt: int, preflight: dict, stage351: dict,
           stage357: dict, reason_copy: bytes, wait_copy: bytes) -> dict:
    demand(type(run_id) is int and run_id>0 and
           type(attempt) is int and attempt>0 and
           type(git_sha) is str and len(git_sha)==40 and
           all(c in "0123456789abcdef" for c in git_sha),
           "missing exact current source/run identity")
    demand(guest_root==source_root/"sdmc/switch/vandal-hearts-remake" and
           not any(p.is_symlink() for p in (source_root,*source_root.parents)) and
           source_root.name==f"vh-nexium-stage266-{run_id}",
           "wrong isolated NeXium original guest root")
    demand(preflight.get("result")==EXPECTED_NRO and
           preflight.get("git_sha")==git_sha and
           type(preflight.get("run_id")) is int and preflight["run_id"]==run_id and
           type(preflight.get("run_attempt")) is int and
           preflight["run_attempt"]==attempt and
           type(preflight.get("nro_bytes")) is int and
           preflight["nro_bytes"]>=1024 and
           type(preflight.get("nro_sha256")) is str and
           len(preflight["nro_sha256"])==64,
           "current same-run NRO preflight was not verified")
    demand(stage351.get("result")==EXPECTED_S351 and
           stage351.get("original_guest_tail_reason_bytes_preserved") is True and
           stage351.get("prior_stage313_and_stage348_original_bytes_reaudited") is True and
           stage351.get("physical_Nintendo_Switch_audio_tested") is False and
           stage357.get("result")==EXPECTED_S357 and
           stage357.get("original_guest_wait_result_bytes_preserved") is True and
           stage357.get("physical_Nintendo_Switch_audio_tested") is False,
           "prior independent original guest audits incomplete")
    parsed=audit_directory(guest_root)
    demand(parsed.get("result")==FORMAT_VERDICT and
           parsed.get("original_neXium_archive_proven") is False,
           "unexpected Stage368 format report scope")
    hashes=parsed["source_sha256"]
    demand(type(reason_copy) is bytes and type(wait_copy) is bytes and
           hashlib.sha256(reason_copy).hexdigest()==hashes["reason"] and
           hashlib.sha256(wait_copy).hexdigest()==hashes["result"] and
           stage351.get("original_guest_tail_reason_csv_sha256")==hashes["reason"] and
           stage357.get("original_guest_wait_result_csv_sha256")==hashes["result"] and
           stage357.get("original_stage351_source_sha256")==hashes["reason"] and
           type(stage351.get("reason_code")) is int and
           stage351["reason_code"]==parsed["tail_reason_code"] and
           type(stage357.get("stage351_reason_code")) is int and
           stage357["stage351_reason_code"]==parsed["tail_reason_code"] and
           type(stage357.get("audout_wait_result_raw")) is int and
           stage357["audout_wait_result_raw"]==parsed["raw_wait_result"] and
           stage357.get("original_guest_wait_result_source_observed") is True and
           stage351.get("original_guest_tail_reason_source_observed") is True,
           "Stage368 raw source not corroborated by original Stage351/357 bytes")
    return {
        **parsed,
        "schema":"vh-stage368-neXium-same-run-original-guest-wait-descriptor/v1",
        "result":VERDICT,
        "neXium_original_guest_run_id":run_id,
        "neXium_nro_git_sha":git_sha,
        "neXium_nro_sha256":preflight["nro_sha256"],
        "neXium_nro_run_attempt":attempt,
        "independent_stage351_original_bytes_reaudited":True,
        "independent_stage357_original_bytes_reaudited":True,
        "stage368_guest_original_source_bound_to_verified_prior_originals":True,
        "original_neXium_archive_proven":True,
        "old_0xEA01_cause_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "kernel_wait_subcall_uniquely_proven":False,
        "actual_queue_depth_measured":False,
    }

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file",type=Path,required=True)
    p.add_argument("--runner-temp",type=Path,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--run-attempt",type=int,required=True)
    p.add_argument("--git-sha",required=True)
    p.add_argument("--nro-preflight",type=Path,required=True)
    p.add_argument("--stage351",type=Path,required=True)
    p.add_argument("--stage357",type=Path,required=True)
    p.add_argument("--stage351-original",type=Path,required=True)
    p.add_argument("--stage357-original",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--stage368-original",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        for file in (args.stage351_original,args.stage357_original,
                     args.guest_root_file):
            demand(regular(file),"original inputs missing or linked")
        target_root=args.runner_temp/f"vh-nexium-stage266-{args.run_id}"
        name=args.guest_root_file.read_text(encoding="utf-8").strip()
        demand(name==str(target_root),"guest source root not current isolated run")
        root=target_root/"sdmc/switch/vandal-hearts-remake"
        for output in (args.output,args.stage368_original):
            demand(not output.exists() and not output.is_symlink(),
                   "refuse overwrite prior original/report")
            demand(not any(p.is_symlink() for p in output.parents),
                   "linked output directory")
        result=attest(target_root,root,args.run_id,args.git_sha,
            args.run_attempt,load_json(args.nro_preflight),
            load_json(args.stage351),load_json(args.stage357),
            args.stage351_original.read_bytes(),args.stage357_original.read_bytes())
        original=root/"audio-exit-wait-descriptor-000.csv"
        raw=original.read_bytes()
        demand(hashlib.sha256(raw).hexdigest()==result["source_sha256"]["descriptor"],
               "original descriptor source changed after audit")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.stage368_original.parent.mkdir(parents=True,exist_ok=True)
        with args.stage368_original.open("xb") as f: f.write(raw)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({"result":VERDICT,"raw_wait_result":result["raw_wait_result"],
           "kernel_timeout_cause_proven":False,"physical_audio":False},sort_keys=True))
        return 0
    except (OSError,TypeError,ValueError,UnicodeError,KeyError) as exc:
        print(json.dumps({"result":"STAGE368_ORIGINAL_GUEST_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "causal_timeout_claim_proven":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
