#!/usr/bin/env python3
"""Stage370: cross-check two independent *archived* audit verdicts, non-causally.

Stage365 establishes one original timeout and a DIFFERENT successful run.
Stage369 establishes a THIRD, later original success with Stage368 descriptor
data. Archived report evidence is NOT a paired device or kernel experiment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

OLD_RUN=39325440778
PREVIOUS_SUCCESS_RUN=39340120727
LATEST_SUCCESS_RUN=39388027581
STAGE365_RUN=39351366143
STAGE369_RUN=39390450645
ARTIFACTS={
 "stage365":(12233871696,"stage365-authentic-distinct-timeout-and-success",
   "sha256:95568de3a02c115dd8f74046926211824d7048971ba1b1c24a714e6ce3df2771"),
 "stage369":(12250010822,"stage369-independent-original-nexium-wait-replay",
   "sha256:02559b59b1a220151ee80f701d65578ac2b239c879b29f1960f3ac9e62fd11bf"),
}
OLD_VERDICT="STAGE365_DISTINCT_AUTHENTIC_KERNEL_TIMEOUT_AND_SUCCESS_REAUDITED_NO_CAUSAL_PAIR"
LATEST_VERDICT="STAGE369_ORIGINAL_NEXIUM_ARCHIVE_STAGE368_REPLAYED"
VERDICT="STAGE370_THREE_DISTINCT_AUTHENTIC_EXIT_RUNS_NONCAUSAL_GAP_AUDITED"

def require(ok:bool, why:str)->None:
    if not ok:raise ValueError(why)

def read_json(path:Path,limit=100000)->dict:
    require(path.is_file() and not any(q.is_symlink() for q in (path,*path.parents))
            and 0<path.stat().st_size<=limit,"missing, linked or oversized original audit receipt")
    value=json.loads(path.read_text(encoding="utf-8"))
    require(type(value) is dict,"invalid JSON document shape")
    return value

def check_meta(meta:dict, key:str)->dict:
    ident,name,expected_digest=ARTIFACTS[key]
    original_run=STAGE365_RUN if key=="stage365" else STAGE369_RUN
    require(type(meta.get("id")) is int and meta["id"]==ident
            and meta.get("name")==name
            and meta.get("digest")==expected_digest
            and meta.get("expired") is False
            and type(meta.get("size_in_bytes")) is int
            and meta["size_in_bytes"]>0,
            "archived independent audit artifact metadata mismatch: "+key)
    source=meta.get("workflow_run")
    require(type(source) is dict
            and type(source.get("id")) is int and source["id"]==original_run
            and type(source.get("head_sha")) is str and
            len(source["head_sha"])==40
            and all(c in "0123456789abcdef" for c in source["head_sha"]),
            "wrong original independent audit workflow: "+key)
    return {"run_id":original_run,"artifact_id":ident,
            "artifact_digest":expected_digest,"source_head_sha":source["head_sha"]}

def compare(old:dict,latest:dict,meta365:dict,meta369:dict)->dict:
    proof365=check_meta(meta365,"stage365")
    proof369=check_meta(meta369,"stage369")
    require(OLD_RUN!=PREVIOUS_SUCCESS_RUN and OLD_RUN!=LATEST_SUCCESS_RUN
            and PREVIOUS_SUCCESS_RUN!=LATEST_SUCCESS_RUN,
            "three distinct authenticated original runs required")
    require(old.get("result")==OLD_VERDICT
            and type(old.get("timeout_original_run_id")) is int
            and old["timeout_original_run_id"]==OLD_RUN
            and type(old.get("success_original_run_id")) is int
            and old["success_original_run_id"]==PREVIOUS_SUCCESS_RUN
            and old.get("two_distinct_original_archives_reaudited") is True
            and type(old.get("timeout_software_wait_raw_result")) is int
            and old["timeout_software_wait_raw_result"]==59905
            and old.get("timeout_software_wait_raw_hex")=="0xEA01"
            and type(old.get("success_software_wait_raw_result")) is int
            and old["success_software_wait_raw_result"]==0
            and old.get("timeout_software_acquired_released_abandoned")==[1414,1413,1]
            and old.get("success_software_acquired_released_abandoned")==[1438,1438,0]
            and old.get("timeout_old_stage360_queue_probe_recorded") is False
            and old.get("timeout_old_pre_submit_queue_depth") is None
            and old.get("timeout_old_pre_submit_probe_age_ns") is None
            and old.get("timeout_and_success_have_same_schema_queue_telemetry") is False
            and old.get("causal_inference_about_old_timeout_proven") is False
            and old.get("timeout_root_cause_unique_to_kernel_callsite_proven") is False
            and old.get("real_hardware_Nintendo_Switch_speaker_or_DAC_verified") is False,
            "historical independently verified timeout and prior success were altered")
    for key,expected_keys in (
        ("timeout_stage313_348_351_357_sha256",
         {"stage313","stage348","stage351","stage357"}),
        ("timeout_original_guest_receipt_sha256",
         {"stage313","stage314","stage348","stage351","stage357"}),
    ):
        obj=old.get(key)
        require(type(obj) is dict and set(obj)==expected_keys
                and all(type(x) is str and len(x)==64 and
                        all(c in "0123456789abcdef" for c in x)
                        for x in obj.values()),"historical original-source SHA provenance missing")
    require(latest.get("result")==LATEST_VERDICT
            and type(latest.get("source_run_id")) is int
            and latest["source_run_id"]==LATEST_SUCCESS_RUN
            and type(latest.get("source_artifact_id")) is int
            and latest["source_artifact_id"]==12249301260
            and type(latest.get("source_attempt")) is int
            and latest["source_attempt"]>0
            and type(latest.get("source_git_sha")) is str
            and len(latest["source_git_sha"])==40
            and type(latest.get("same_run_nro_sha256")) is str
            and len(latest["same_run_nro_sha256"])==64
            and latest.get("original_stage368_step_succeeded") is True
            and latest.get("whole_runtime_run_succeeded") is True
            and type(latest.get("stage351_reason_code")) is int
            and latest["stage351_reason_code"]==7
            and type(latest.get("service_result_raw")) is int
            and latest["service_result_raw"]==0
            and type(latest.get("service_returned_descriptor_count")) is int
            and latest["service_returned_descriptor_count"]==1
            and latest.get("returned_pointer_present") is True
            and latest.get("returned_pointer_matches_submitted") is True
            and latest.get("old_0xEA01_cause_proven") is False
            and latest.get("exit_queue_depth_measured") is False
            and latest.get("physical_Switch_sound_tested") is False,
            "later independently replayed descriptor source altered")
    fingerprints=latest.get("independently_reopened_original_csv_sha256")
    require(type(fingerprints) is dict and
            set(fingerprints)=={"reason","result","descriptor"} and
            all(type(v) is str and len(v)==64 and
                all(c in "0123456789abcdef" for c in v)
                for v in fingerprints.values()),"later original CSV SHA-256 missing")
    old_sha=set(old["timeout_stage313_348_351_357_sha256"].values())
    require(not old_sha.intersection(set(fingerprints.values())),
            "historical timeout CSV substituted into new NeXium guest artifact")
    return {
        "schema":"vh-stage370-three-distinct-authentic-audout-exit-runs/v1",
        "result":VERDICT,
        "independent_stage365_artifact":proof365,
        "independent_stage369_artifact":proof369,
        "earlier_original_timeout_run":OLD_RUN,
        "older_original_success_run":PREVIOUS_SUCCESS_RUN,
        "latest_original_success_with_descriptor_run":LATEST_SUCCESS_RUN,
        "old_authentic_timeout_service_result":59905,
        "old_authentic_timeout_service_result_hex":"0xEA01",
        "old_software_acquired_released_abandoned":[1414,1413,1],
        "old_timeout_stage368_descriptor_count":None,
        "old_timeout_stage368_pointer_match":None,
        "old_timeout_stage360_probe_status":None,
        "older_success_service_result":0,
        "older_success_stage368_descriptor_count":None,
        "latest_success_service_result":0,
        "latest_success_reported_released_count":1,
        "latest_success_pointer_matches_submitted":True,
        "latest_verified_three_guest_csv_sha256":fingerprints,
        "old_timeout_kernel_callsite_identified":False,
        "independent_guest_cohorts_not_matched":True,
        "old_timeout_direct_exit_queue_depth_known":False,
        "physical_switch_dac_or_speaker_tested":False,
        "old_0xEA01_causality_proven":False,
    }

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("stage365","stage369","meta365","meta369","output"):
        parser.add_argument("--"+name,required=True,type=Path)
    a=parser.parse_args(argv)
    try:
        require(not a.output.exists() and not a.output.is_symlink(),
                "refuse overwrite prior audit verdict")
        # Hard bind both independent original artifact identities.
        result=compare(read_json(a.stage365),read_json(a.stage369),
                       read_json(a.meta365),read_json(a.meta369))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        require(not any(q.is_symlink() for q in (a.output,*a.output.parents)),
                "linked output destination")
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({"result":VERDICT,"original_timeout":59905,
                          "new_success_returned_descriptors":1,
                          "old_descriptor_count_known":False,
                          "kernel_timeout_cause_proven":False},sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError,KeyError) as exc:
        print(json.dumps({"result":"STAGE370_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "kernel_timeout_cause_proven":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
