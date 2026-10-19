#!/usr/bin/env python3
"""Stage363: SHA-pinned independent replay of authentic successful Stage362 host/guest sources.

Audit only original NeXium #39340120727. This is not a new emulator launch,
an exit-time audout queue measurement, or hardware audio. Never treat the
previous run's rejected -771 ms host chronology as retroactively repaired.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_recorder_stop_dual_clock_stage362 import (
    audit as audit_host, parse as parse_host, LEGACY, RESULT as HOST_RESULT,
)
from audit_nexium_guest_exit_probe_context_stage360 import parse_source as audit_probe
from audit_nexium_guest_tail_wait_result_stage357 import parse_source as audit_wait

RUN_ID=39340120727
VERIFIED="STAGE363_AUTHENTIC_DUAL_CLOCK_AND_GUEST_EXIT_SOURCE_REAUDITED"
PATH_PREFIX="sdmc/switch/vandal-hearts-remake/"
PINS={
    "legacy":"4744113fd37a5ee6dff438ad698c2ae313fa690ae8fbf93aecab272fd3a49364",
    "paired":"4695e9c91a74e4c236b7569d60f0d2b98356667ae5280c83980d88bce5d9a76e",
    "stage362":"d1622952c5acdd621e3458ea9a682d5287954d37876b3f9ac7532ae72b47e997",
    "stage303":"cbdbacdf57ed64f4b05be3992ca573ae782ad67def5e17d397da390fdcdc09b0",
    "pcm":"c109bd015f30871e201328c82255ec1a2caeb4da59f99310a2fdbae1c3e437c3",
    "probe":"e923d3c7617f0912d6d753321fe8e1855b6b9b66132809670373a0ba009566d8",
    "stage360":"5aebdbe076f57ffb69f504db7687e1a00af3860925e532199b605de56414e59d",
    "stage313":"912ada9ae3993f177b4c6164b3bf381284a220c51f3cca1455e23a8856317f9e",
    "stage351":"204a34e7068def0d7f2e14d97560c0c1da0416d0ec6cc23f07f13d9a7396a38a",
    "wait":"298997cc46abb7377d106397651b4ed01cd6304690fa6b45b8900231c350d6e0",
    "stage357":"b750ba0129dc467fd551248807da09e095d10bd5bd51ba0fd3dccf6e90ca251b",
    "lease":"2258d2e713bc3325dc51bd41345130fa102373f7cd24d1feeee31cb43ea7aef8",
    "stage348":"c69fb1bbf59a1d2eeb644a508f59ebf56c94c36415ad7aef9795363c039366ad",
    "reason":"6730ef1969efd9535a109db0f4aacb4c0deca9e95080a54da5f1ee04fc0754b3",
}
FILES={
    "legacy":"scene-recorder-stop.csv",
    "paired":"scene-recorder-stop-monotonic.csv",
    "stage362":"scene-recorder-stop-dual-clock-stage362.json",
    "stage303":"pcm-recorder-stop-stage303.json",
    "pcm":"nexium-scenes-s16le-48k.pcm",
    "probe":"audio-exit-probe-context-000.csv",
    "stage360":"guest-exit-probe-context-stage360.json",
    "stage313":"guest-last-audout-release-stage313.json",
    "stage351":"guest-exit-tail-reason-stage351.json",
    "wait":"audio-exit-tail-wait-result-000.csv",
    "stage357":"guest-exit-tail-wait-result-stage357.json",
    "lease":"audio-lease-reconciliation-000.csv",
    "stage348":"guest-lease-reconciliation-stage348.json",
    "reason":"audio-exit-tail-reason-000.csv",
}

def host_source_check(legacy:bytes,paired:bytes,report362:dict,
                      report303:dict,pcm:bytes)->dict:
    host=audit_host(legacy,paired)
    if report362!=host or host["result"]!=HOST_RESULT:
        raise ValueError("Stage362 original host receipt altered")
    snapshots=parse_host(legacy,LEGACY)
    if (not isinstance(report303,dict)
        or report303.get("result")!="SOURCE_BOUND_HOST_RECORDER_STOP_SNAPSHOT_RECONCILED"
        or report303.get("stop_events")!=snapshots
        or report303.get("stop_wall_interval_ms")!=host["host_wall_elapsed_ms"]
        or report303.get("buffered_bytes_appended_during_stop")!=host["pcm_file_size_delta_bytes"]
        or report303.get("scene_pcm_frames")!=len(pcm)//4
        or len(pcm)%4
        or report303.get("scene_pcm_sha256")!=hashlib.sha256(pcm).hexdigest()
        or snapshots[-1]["pcm_bytes"]!=len(pcm)
        or report303.get("stage302_original_zero_run_classes_conserved") is not True
        or report303.get("physical_Nintendo_Switch_audio_tested") is not False
        or report303.get("original_soundtrack_or_audible_dropout_verified") is not False):
        raise ValueError("original strict Stage303 PCM/source reconciliation changed")
    if (host["host_wall_elapsed_ms"]!=21
        or host["host_monotonic_elapsed_ns"]!=20788687
        or host["pcm_file_size_delta_bytes"]!=0
        or host["strict_stage303_chronology_compatible"] is not True
        or host["host_wall_clock_moved_backwards"] is not False
        or host["real_DAC_or_speaker_audio_verified"] is not False):
        raise ValueError("not original successful Stage362 recorder stop")
    return host

def compare_receipt(observed:dict,archived:dict,relative_path:str)->None:
    if not isinstance(archived,dict):
        raise ValueError("nonobject original guest receipt")
    observed={**observed,"original_guest_source_relative_path":relative_path}
    if observed!=archived:
        raise ValueError("independent guest-source parsing disagrees with archive receipt")

def recheck(source:dict[str,bytes])->dict:
    for key,sha in PINS.items():
        if not isinstance(source.get(key),bytes) or hashlib.sha256(source[key]).hexdigest()!=sha:
            raise ValueError("authentic original NeXium SHA pin mismatch: "+key)
    def receipt(key):
        obj=json.loads(source[key].decode("utf-8"))
        if not isinstance(obj,dict):
            raise ValueError("original receipt is not JSON object")
        return obj
    host=host_source_check(source["legacy"],source["paired"],
                           receipt("stage362"),receipt("stage303"),source["pcm"])
    stage313=receipt("stage313")
    stage351=receipt("stage351")
    stage348=receipt("stage348")
    stage357=receipt("stage357")
    stage360=receipt("stage360")
    if (stage351.get("reason_code")!=7
        or stage351.get("original_guest_tail_reason_csv_sha256")!=PINS["reason"]
        or stage351.get("original_guest_stage348_csv_sha256")!=PINS["lease"]
        or stage348.get("original_guest_software_lease_csv_sha256")!=PINS["lease"]
        or stage348.get("lease_pages_acquired")!=1438
        or stage348.get("lease_pages_released")!=1438
        or stage348.get("abandoned_sessions")!=0
        or stage348.get("physical_Nintendo_Switch_audio_tested") is not False
        or stage313.get("tail_bounded_attempt_observed") is not True
        or stage313.get("tail_release_confirmed") is not True):
        raise ValueError("original guest lease/reason receipt changed")
    wait=audit_wait(source["wait"],stage351)
    compare_receipt(wait,stage357,PATH_PREFIX+FILES["wait"])
    probe=audit_probe(source["probe"],stage313,stage351)
    compare_receipt(probe,stage360,PATH_PREFIX+FILES["probe"])
    if (wait.get("audout_wait_result_raw")!=0
        or probe.get("last_pre_submit_probe_attempt")!=1425
        or probe.get("normal_submit_attempts_at_tail")!=1437
        or probe.get("last_pre_submit_probe_queue_count")!=0
        or probe.get("last_pre_submit_probe_age_ns")!=369284375
        or probe.get("last_pre_submit_probe_age_at_tail_end_ns")!=381019843
        or probe.get("tail_elapsed_ns")!=11735468
        or probe.get("direct_exit_time_queue_depth_observed") is not False
        or probe.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("not original success-guest queue-probe age context")
    return {
        "schema":"vh-stage363-original-neXium-guest-host-source-replay/v1",
        "result":VERIFIED,
        "original_neXium_run_id":RUN_ID,
        "exact_original_sha256":PINS,
        "original_strict_stage303_success":True,
        "original_stage362_host_recorder_wall_ms":host["host_wall_elapsed_ms"],
        "original_stage362_host_recorder_monotonic_ns":host["host_monotonic_elapsed_ns"],
        "original_stage362_host_pcm_size_delta_bytes":host["pcm_file_size_delta_bytes"],
        "original_stage303_pcm_bytes":len(source["pcm"]),
        "guest_tail_reason_code":7,
        "guest_audout_wait_raw_result":0,
        "guest_lease_pages_acquired":1438,
        "guest_lease_pages_released":1438,
        "guest_abandoned_sessions":0,
        "prior_pre_submit_probe_attempt":1425,
        "normal_submit_attempts_at_tail":1437,
        "old_probe_age_at_tail_begin_ns":369284375,
        "old_probe_age_at_tail_end_ns_derived":381019843,
        "software_tail_elapsed_ns":11735468,
        "original_guest_exit_queue_depth_directly_measured":False,
        "old_failed_run_host_clocks_retroactively_fixed":False,
        "actual_speaker_or_DAC_audio_measured":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def archive_files(root:Path)->dict[str,bytes]:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("archive root missing or symlinked")
    data={}
    for key,name in FILES.items():
        matches=list(root.rglob(name))
        if len(matches)!=1:
            raise ValueError("missing/ambiguous original archive filename: "+name)
        path=matches[0]
        if (not path.is_file() or any(p.is_symlink() for p in (path,*path.parents))
            or path.stat().st_size>(16_000_000 if key=="pcm" else 128_000)):
            raise ValueError("linked/oversized original NeXium source: "+name)
        data[key]=path.read_bytes()
    return data

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite original source replay report")
        result=recheck(archive_files(a.archive_root))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(path.is_symlink() for path in (a.output,*a.output.parents)):
            raise ValueError("report parent symlinked")
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(result,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,"strict_stage303_passed":True,
            "host_wall_ms":result["original_stage362_host_recorder_wall_ms"],
            "host_monotonic_ns":result["original_stage362_host_recorder_monotonic_ns"],
            "physical_audio_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,TypeError,KeyError) as error:
        print(json.dumps({
            "result":"STAGE363_ORIGINAL_GUEST_HOST_SOURCE_NOT_VERIFIED",
            "error_kind":type(error).__name__,
            "physical_audio_tested":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
