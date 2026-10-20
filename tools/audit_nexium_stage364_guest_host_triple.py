#!/usr/bin/env python3
"""Stage364: replay original Stage313+314/348/351 raw-guest evidence together with Stage363.

Use the exact preserved original NRO/NeXium #39340120727 artifact. Old
Stage352's independent source parsers reproduce all three originals; a new
cross-stage control binds these to independently replayed Stage303/362/357/360
from the very same artifact. Not a guest-clock/host-clock correlation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_stage352_three_original_tail_sources import (
    reaudited_archive, VERIFIED as TRIPLE_VERIFIED,
)
from audit_nexium_stage363_authentic_guest_host_dual import (
    archive_files, recheck, PINS as STAGE363_PINS, RUN_ID,
)

VERIFIED="STAGE364_SAME_ORIGINAL_RUN_TRIPLE_GUEST_LEASE_EXIT_AND_HOST_CLOCKS_REAUDITED"
EXTRA={
    "tail":("audio-exit-output-000.csv",
            "c234be43860581ab47a7fc7760054d77767e0fcbeb38d72631d50e87df931cf3"),
    "stage314":("guest-original-audout-last-page-stage314.json",
                "7e6f360bda821110191c323acdc6e5e2f0041833dc7b6d39b530da55bb267b27"),
}
FILENAMES={
    "tail":EXTRA["tail"][0],
    "lease":"audio-lease-reconciliation-000.csv",
    "reason":"audio-exit-tail-reason-000.csv",
    "stage313":"guest-last-audout-release-stage313.json",
    "stage314":EXTRA["stage314"][0],
    "stage348":"guest-lease-reconciliation-stage348.json",
    "stage351":"guest-exit-tail-reason-stage351.json",
}
TRIPLE_PINS={
    "tail":EXTRA["tail"][1],
    "lease":STAGE363_PINS["lease"],
    "reason":STAGE363_PINS["reason"],
}

def bind_independent_reports(triple:dict,stage363:dict)->dict:
    if (not isinstance(triple,dict) or not isinstance(stage363,dict)
        or triple.get("result")!=TRIPLE_VERIFIED
        or type(triple.get("original_neXium_run_id")) is not int
        or triple["original_neXium_run_id"]!=RUN_ID
        or triple.get("original_guest_csv_sha256")!={
            "stage313_last_audio_page_and_tail":TRIPLE_PINS["tail"],
            "stage348_software_PCM_lease":TRIPLE_PINS["lease"],
            "stage351_exit_tail_reason":TRIPLE_PINS["reason"],
        }
        or type(triple.get("tail_reason_code")) is not int
        or triple["tail_reason_code"]!=7
        or triple.get("tail_reason_name")!="return_confirmed"
        or triple.get("tail_attempted") is not True
        or triple.get("tail_descriptor_return_confirmed") is not True
        or type(triple.get("lease_pages_acquired")) is not int
        or triple["lease_pages_acquired"]!=1438
        or type(triple.get("lease_pages_released")) is not int
        or triple["lease_pages_released"]!=1438
        or type(triple.get("abandoned_sessions")) is not int
        or triple["abandoned_sessions"]!=0
        or triple.get("exact_archived_original_CSV_bytes_reaudited") is not True
        or triple.get("three_distinct_guest_source_receipts_matched") is not True
        or triple.get("independent_of_any_other_neXium_run") is not True
        or triple.get("older_unconfirmed_tail_failure_cause_proven") is not False
        or triple.get("physical_Nintendo_Switch_audio_tested") is not False
        or triple.get("DAC_or_speaker_audio_verified") is not False):
        raise ValueError("original three guest PCM/tail original sources not reproduced")
    if (stage363.get("result")!=
        "STAGE363_AUTHENTIC_DUAL_CLOCK_AND_GUEST_EXIT_SOURCE_REAUDITED"
        or type(stage363.get("original_neXium_run_id")) is not int
        or stage363["original_neXium_run_id"]!=RUN_ID
        # Bind to the *entire* Stage363 pinned original-source set,
        # not just to its displayed counters or human-readable run ID.
        # A forged wrapper with the same 1438/1438/0 counts is not proof.
        or stage363.get("exact_original_sha256")!=STAGE363_PINS
        or type(stage363.get("original_stage303_pcm_bytes")) is not int
        or stage363["original_stage303_pcm_bytes"]!=8804896
        or type(stage363.get("original_stage362_host_pcm_size_delta_bytes")) is not int
        or stage363["original_stage362_host_pcm_size_delta_bytes"]!=0
        or type(stage363.get("software_tail_elapsed_ns")) is not int
        or stage363["software_tail_elapsed_ns"]!=11735468
        or type(stage363.get("old_probe_age_at_tail_begin_ns")) is not int
        or stage363["old_probe_age_at_tail_begin_ns"]!=369284375
        or type(stage363.get("old_probe_age_at_tail_end_ns_derived")) is not int
        or stage363["old_probe_age_at_tail_end_ns_derived"]!=381019843
        or stage363.get("guest_tail_reason_code")!=triple["tail_reason_code"]
        or stage363.get("guest_audout_wait_raw_result")!=0
        or stage363.get("guest_lease_pages_acquired")!=triple["lease_pages_acquired"]
        or stage363.get("guest_lease_pages_released")!=triple["lease_pages_released"]
        or stage363.get("guest_abandoned_sessions")!=triple["abandoned_sessions"]
        or stage363.get("original_strict_stage303_success") is not True
        or stage363.get("original_stage362_host_recorder_wall_ms")!=21
        or stage363.get("original_stage362_host_recorder_monotonic_ns")!=20788687
        or stage363.get("original_guest_exit_queue_depth_directly_measured") is not False
        or stage363.get("old_failed_run_host_clocks_retroactively_fixed") is not False
        or stage363.get("actual_speaker_or_DAC_audio_measured") is not False
        or stage363.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("independent host/guest paired Stage363 disagrees with triple guest source")
    return {
        "schema":"vh-stage364-triple-original-guest-and-host-run-identity/v1",
        "result":VERIFIED,
        "original_neXium_run_id":RUN_ID,
        "stage313_original_tail_csv_sha256":TRIPLE_PINS["tail"],
        "stage314_original_source_receipt_sha256":EXTRA["stage314"][1],
        "stage348_original_lease_csv_sha256":TRIPLE_PINS["lease"],
        "stage351_original_reason_csv_sha256":TRIPLE_PINS["reason"],
        "original_three_guest_families_independently_replayed":True,
        "original_stage363_host_and_guest_source_replayed":True,
        "guest_audio_lease_acquired":triple["lease_pages_acquired"],
        "guest_audio_lease_released":triple["lease_pages_released"],
        "guest_audio_abandoned_sessions":triple["abandoned_sessions"],
        "guest_tail_reason_code":triple["tail_reason_code"],
        "guest_bounded_tail_return_confirmed":True,
        "guest_raw_audout_wait_result":0,
        "host_strict_stage303_success":True,
        "host_recorder_stop_wall_delta_ms":21,
        "host_recorder_stop_monotonic_delta_ns":20788687,
        "guest_to_host_clock_sync_proven":False,
        "old_host_wall_regression_cause_proven":False,
        "old_0xEA01_guest_kernel_event_callsite_uniquely_proven":False,
        "older_timeout_has_matched_stage360_probe":False,
        "direct_exit_time_queue_depth_observed":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "audible_DAC_or_speaker_audio_tested":False,
    }

def exact_guest_paths(root:Path)->dict[str,Path]:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("original artifact root missing or symlinked")
    paths={}
    for key,name in FILENAMES.items():
        matches=list(root.rglob(name))
        if len(matches)!=1:
            raise ValueError("missing/ambiguous archived original guest source: "+name)
        path=matches[0]
        if (not path.is_file() or any(p.is_symlink() for p in (path,*path.parents))
            or path.stat().st_size>128_000):
            raise ValueError("original guest source linked or oversized: "+name)
        paths[key]=path
    for key in ("tail","stage314","lease","reason"):
        pin=(EXTRA[key][1] if key in EXTRA else TRIPLE_PINS[key])
        if hashlib.sha256(paths[key].read_bytes()).hexdigest()!=pin:
            raise ValueError("original guest source SHA changed: "+key)
    return paths

def original_archive(root:Path)->dict:
    # Two independently reusable audit paths on the identical archive root.
    stage363=recheck(archive_files(root))
    triple=reaudited_archive(exact_guest_paths(root),TRIPLE_PINS,RUN_ID)
    return bind_independent_reports(triple,stage363)

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    a=parser.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite Stage364 prior report")
        doc=original_archive(a.archive_root)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        if any(p.is_symlink() for p in (a.output,*a.output.parents)):
            raise ValueError("report destination linked")
        with a.output.open("x",encoding="utf-8") as output:
            json.dump(doc,output,indent=2,sort_keys=True)
            output.write("\n")
        print(json.dumps({"result":VERIFIED,"original_run":RUN_ID,
            "original_sources_replayed":True,"physical_audio_tested":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps({"result":"STAGE364_ORIGINAL_GUEST_HOST_TRIPLE_NOT_VERIFIED",
            "error_kind":type(error).__name__,"hardware_audio_tested":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
