#!/usr/bin/env python3
"""Stage365: separately authenticate old NeXium 0xEA01 and new successful guest run.

This is a provenance-safe comparison of TWO DIFFERENT original executions.
No matched Stage360 queue probe exists for the old timeout capture, so no
causal queue-depth, kernel call-site, host epoch, or physical audio inference.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from audit_nexium_stage352_three_original_tail_sources import reaudited_archive
from audit_nexium_stage358_original_kernel_timeout import (
    SOURCES as TIMEOUT_SOURCES, RUN_ID as TIMEOUT_RUN,
    TAPER as TIMEOUT_TAIL_SHA, LEASE as TIMEOUT_LEASE_SHA,
    REASON as TIMEOUT_REASON_SHA, WAIT as TIMEOUT_WAIT_SHA,
    verify as verify_timeout, VERIFIED as TIMEOUT_VERIFIED,
)
from audit_nexium_stage364_guest_host_triple import (
    original_archive as verify_success, RUN_ID as SUCCESS_RUN,
    VERIFIED as SUCCESS_VERIFIED, TRIPLE_PINS as SUCCESS_PINS,
)

VERIFIED="STAGE365_DISTINCT_AUTHENTIC_KERNEL_TIMEOUT_AND_SUCCESS_REAUDITED_NO_CAUSAL_PAIR"
MISSING_PROBE_NAMES=(
    "audio-exit-probe-context-000.csv",
    "guest-exit-probe-context-stage360.json",
)

def safe_files(root:Path, names:dict[str,str])->dict[str,Path]:
    if not root.is_dir() or any(x.is_symlink() for x in (root,*root.parents)):
        raise ValueError("missing or linked original NeXium artifact root")
    found={}
    for key,name in names.items():
        hits=list(root.rglob(name))
        if len(hits)!=1:
            raise ValueError("missing or ambiguous original timeout source: "+name)
        item=hits[0]
        if (not item.is_file() or any(x.is_symlink() for x in (item,*item.parents))
            or item.stat().st_size>128_000):
            raise ValueError("unsafe original source for "+key)
        found[key]=item
    return found

def old_capture(root:Path)->dict:
    files=safe_files(root,TIMEOUT_SOURCES)
    # Explicitly establish that NO pairable Stage360 old-queue reading exists.
    # Treat missing evidence as unknown, NEVER infer zero or inherit data
    # from the separately successful guest run.
    for name in MISSING_PROBE_NAMES:
        if list(root.rglob(name)):
            raise ValueError("old timeout archive unexpectedly has a Stage360 source")
    old=reaudited_archive(
        {key:files[key] for key in
         ("tail","lease","reason","stage313","stage314","stage348","stage351")},
        {"tail":TIMEOUT_TAIL_SHA,"lease":TIMEOUT_LEASE_SHA,
         "reason":TIMEOUT_REASON_SHA},TIMEOUT_RUN
    )
    reason=json.loads(files["stage351"].read_text(encoding="utf-8"))
    observed=json.loads(files["stage357"].read_text(encoding="utf-8"))
    if not isinstance(reason,dict) or not isinstance(observed,dict):
        raise ValueError("invalid archived timeout receipt")
    checked=verify_timeout(old,reason,observed,files["wait"].read_bytes())
    if (checked.get("result")!=TIMEOUT_VERIFIED
        or checked.get("source_sha256")!={
            "stage313":TIMEOUT_TAIL_SHA,"stage348":TIMEOUT_LEASE_SHA,
            "stage351":TIMEOUT_REASON_SHA,"stage357":TIMEOUT_WAIT_SHA,
        }
        or checked.get("stage357_audout_wait_raw_result_decimal")!=59905
        or checked.get("stage357_audout_wait_raw_result_hex")!="0xEA01"
        or checked.get("software_lease_pages_acquired")!=1414
        or checked.get("software_lease_pages_released")!=1413
        or checked.get("software_abandoned_sessions")!=1
        or checked.get("underlying_event_wait_call_site_uniquely_proven") is not False
        or checked.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("authentic old kernel timeout source not independently proven")
    return checked

def compare(timeout:dict,success:dict)->dict:
    if not isinstance(timeout,dict) or not isinstance(success,dict):
        raise ValueError("comparison requires two distinct source reports")
    if (type(timeout.get("original_neXium_run_id")) is not int
        or timeout["original_neXium_run_id"]!=TIMEOUT_RUN
        or type(success.get("original_neXium_run_id")) is not int
        or success["original_neXium_run_id"]!=SUCCESS_RUN
        or TIMEOUT_RUN==SUCCESS_RUN
        or timeout.get("result")!=TIMEOUT_VERIFIED
        or success.get("result")!=SUCCESS_VERIFIED
        or timeout.get("source_sha256")!={
            "stage313":TIMEOUT_TAIL_SHA,"stage348":TIMEOUT_LEASE_SHA,
            "stage351":TIMEOUT_REASON_SHA,"stage357":TIMEOUT_WAIT_SHA,
        }
        or success.get("stage313_original_tail_csv_sha256")!=SUCCESS_PINS["tail"]
        or success.get("stage348_original_lease_csv_sha256")!=SUCCESS_PINS["lease"]
        or success.get("stage351_original_reason_csv_sha256")!=SUCCESS_PINS["reason"]
        or success.get("original_three_guest_families_independently_replayed") is not True
        or type(timeout.get("stage351_reason_code")) is not int
        or timeout["stage351_reason_code"]!=4
        or type(timeout.get("stage357_audout_wait_raw_result_decimal")) is not int
        or timeout["stage357_audout_wait_raw_result_decimal"]!=59905
        or type(success.get("guest_tail_reason_code")) is not int
        or success["guest_tail_reason_code"]!=7
        or type(success.get("guest_raw_audout_wait_result")) is not int
        or success["guest_raw_audout_wait_result"]!=0
        or timeout.get("software_lease_pages_acquired")!=1414
        or timeout.get("software_lease_pages_released")!=1413
        or timeout.get("software_abandoned_sessions")!=1
        or success.get("guest_audio_lease_acquired")!=1438
        or success.get("guest_audio_lease_released")!=1438
        or success.get("guest_audio_abandoned_sessions")!=0
        or success.get("original_three_guest_families_independently_replayed") is not True
        or success.get("original_stage363_host_and_guest_source_replayed") is not True
        or success.get("host_strict_stage303_success") is not True
        or success.get("host_recorder_stop_wall_delta_ms")!=21
        or success.get("host_recorder_stop_monotonic_delta_ns")!=20788687
        or timeout.get("underlying_event_wait_call_site_uniquely_proven") is not False
        or timeout.get("physical_Nintendo_Switch_audio_tested") is not False
        or success.get("physical_Nintendo_Switch_audio_tested") is not False
        or success.get("guest_to_host_clock_sync_proven") is not False
        or success.get("old_host_wall_regression_cause_proven") is not False
        or success.get("older_timeout_has_matched_stage360_probe") is not False
        or success.get("direct_exit_time_queue_depth_observed") is not False):
        raise ValueError("old and new authentic cohorts did not separately verify")
    return {
        "schema":"vh-stage365-two-distinct-original-neXium-guest-exit-cohorts/v1",
        "result":VERIFIED,
        "timeout_original_run_id":TIMEOUT_RUN,
        "success_original_run_id":SUCCESS_RUN,
        "two_distinct_original_archives_reaudited":True,
        "timeout_stage313_348_351_357_sha256":timeout["source_sha256"],
        "success_stage313_348_351_sha256":{
            "stage313":success["stage313_original_tail_csv_sha256"],
            "stage348":success["stage348_original_lease_csv_sha256"],
            "stage351":success["stage351_original_reason_csv_sha256"],
        },
        "timeout_software_wait_raw_result":59905,
        "timeout_software_wait_raw_hex":"0xEA01",
        "timeout_kernel_result_module":1,
        "timeout_kernel_result_description":117,
        "timeout_software_acquired_released_abandoned":[1414,1413,1],
        "success_software_wait_raw_result":0,
        "success_software_acquired_released_abandoned":[1438,1438,0],
        "timeout_old_stage360_queue_probe_recorded":False,
        "timeout_old_pre_submit_queue_depth":None,
        "timeout_old_pre_submit_probe_age_ns":None,
        "success_stage360_queue_at_exit_directly_measured":False,
        "timeout_and_success_have_same_schema_queue_telemetry":False,
        "queue_depth_at_timeout_construed_as_zero":False,
        "timeout_root_cause_unique_to_kernel_callsite_proven":False,
        "causal_inference_about_old_timeout_proven":False,
        "old_failed_host_wall_epoch_clock_explained":False,
        "guest_host_clock_alignment_proven":False,
        "real_hardware_Nintendo_Switch_speaker_or_DAC_verified":False,
        "original_retail_PS1_soundtrack_audibility_verified":False,
    }

def audit_two(timeout_root:Path,success_root:Path)->dict:
    if timeout_root.resolve()==success_root.resolve():
        raise ValueError("same original source directory supplied twice")
    failed=old_capture(timeout_root)
    passed=verify_success(success_root)
    return compare(failed,passed)

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--timeout-original-root",required=True,type=Path)
    p.add_argument("--success-original-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite original-source verdict")
        result=audit_two(a.timeout_original_root,a.success_original_root)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(x.is_symlink() for x in (a.output,*a.output.parents)):
            raise ValueError("linked output path")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(result,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,"old_timeout_0xEA01_authenticated":True,
            "new_success_result_zero_authenticated":True,
            "paired_old_stage360_probe":False,
            "real_hardware_audio":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as err:
        print(json.dumps({
            "result":"STAGE365_DISTINCT_AUTHENTIC_COHORTS_NOT_VERIFIED",
            "error_kind":type(err).__name__,
            "causal_claim_proven":False,
            "real_hardware_audio":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
