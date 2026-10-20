#!/usr/bin/env python3
"""Stage361: independently replay SHA-pinned genuine Stage360 successful-exit guest source.

Forensic replay of a previously completed *FAILED overall* NeXium run. The
original guest Stage313/348/351/357/360 source claims are distinguishable
from the separately rejected host Stage303 recorder-stop chronology.
No emulator run is simulated and no speaker/DAC measurement is inferred.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from audit_nexium_stage352_three_original_tail_sources import reaudited_archive
from audit_nexium_guest_tail_wait_result_stage357 import parse_source as audit_wait
from audit_nexium_guest_exit_probe_context_stage360 import parse_source as audit_probe
from audit_nexium_stage358_original_kernel_timeout import STAGE357_FIELDS

RUN_ID=39333759265
VERIFIED="STAGE361_ORIGINAL_SUCCESS_GUEST_CONTEXT_REAUDITED_HOST_STAGE303_FAILED"
PINS={
    "tail":"68c58321b5b2bfeb1fe1dbcab8ac7c5fd4a7f8344b3091d38ba3462d3cab135e",
    "lease":"291a4ce56aff57b230649779ff9f53b170b5a4ee0c5465f14a2ac34cb882f3d1",
    "reason":"cec14c65148460c1424090562ce5890e476cfbd8367932d65f047ab2de6cb457",
    "wait":"298997cc46abb7377d106397651b4ed01cd6304690fa6b45b8900231c350d6e0",
    "probe":"7d02a26ac017898b9f56f863998c2262677ac94f78ec303a03e30991bee30c82",
    "host_stop":"dc3453abfc48043ccd16e9b6b85bbf174761e08f1c1f3f6e44b0de267de5c3a3",
}
FILES={
    "tail":"audio-exit-output-000.csv",
    "lease":"audio-lease-reconciliation-000.csv",
    "reason":"audio-exit-tail-reason-000.csv",
    "wait":"audio-exit-tail-wait-result-000.csv",
    "probe":"audio-exit-probe-context-000.csv",
    "host_stop":"scene-recorder-stop.csv",
    "stage313":"guest-last-audout-release-stage313.json",
    "stage314":"guest-original-audout-last-page-stage314.json",
    "stage348":"guest-lease-reconciliation-stage348.json",
    "stage351":"guest-exit-tail-reason-stage351.json",
    "stage357":"guest-exit-tail-wait-result-stage357.json",
    "stage360":"guest-exit-probe-context-stage360.json",
}
PROBE_PATH="sdmc/switch/vandal-hearts-remake/audio-exit-probe-context-000.csv"
WAIT_PATH="sdmc/switch/vandal-hearts-remake/audio-exit-tail-wait-result-000.csv"

def bound_source(raw:bytes,kind:str)->bytes:
    if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=PINS[kind]:
        raise ValueError("original SHA-256 pin changed: "+kind)
    return raw

def receipt_equals(observed:dict, archived:dict, *, path:str)->None:
    if not isinstance(archived,dict):
        raise ValueError("original receipt not a JSON object")
    if archived.get("original_guest_source_relative_path")!=path:
        raise ValueError("original guest source location receipt changed")
    for key,value in archived.items():
        if key=="original_guest_source_relative_path":
            continue
        if key not in observed or type(observed[key]) is not type(value) or observed[key]!=value:
            raise ValueError("receipt differs from original bytes: "+key)

def parse_failed_host_stop(raw:bytes)->dict:
    bound_source(raw,"host_stop")
    expected=(b"event,pcm_bytes,host_epoch_ms,signal_success\n"
              b"before_sigint,8732688,1792449461974,1\n"
              b"after_wait,8732688,1792449461203,1\n")
    if raw!=expected:
        raise ValueError("host stop original bytes not canonical")
    return {
        "host_wall_clock_regression_ms":-771,
        "host_pcm_bytes_delta":0,
        "host_stop_signals_succeeded":True,
        "original_stage303_strict_host_recorder_passed":False,
    }

def recheck(paths:dict[str,Path])->dict:
    original={}
    for key in PINS:
        original[key]=bound_source(paths[key].read_bytes(),key)
    old=reaudited_archive(
        {k:paths[k] for k in ("tail","lease","reason","stage313","stage314","stage348","stage351")},
        {k:PINS[k] for k in ("tail","lease","reason")},RUN_ID
    )
    def load(key):
        v=json.loads(paths[key].read_text(encoding="utf-8"))
        if not isinstance(v,dict):
            raise ValueError("non-object original receipt: "+key)
        return v
    stage313=load("stage313")
    stage351=load("stage351")
    stage357=load("stage357")
    stage360=load("stage360")
    wait=audit_wait(original["wait"],stage351)
    # The Stage357 parser omits only this export-path metadata field.
    wait["original_guest_source_relative_path"]=WAIT_PATH
    for key in STAGE357_FIELDS:
        if key not in wait or type(stage357.get(key)) is not type(wait[key]) or stage357[key]!=wait[key]:
            raise ValueError("Stage357 original source receipt mismatch: "+key)
    probe=audit_probe(original["probe"],stage313,stage351)
    receipt_equals(probe,stage360,path=PROBE_PATH)
    if (old["tail_reason_code"]!=7 or old["tail_reason_name"]!="return_confirmed"
        or old["lease_pages_acquired"]!=1366
        or old["lease_pages_released"]!=1366
        or old["abandoned_sessions"]!=0
        or wait["audout_wait_result_raw"]!=0
        or probe["last_pre_submit_probe_attempt"]!=1361
        or probe["normal_submit_attempts_at_tail"]!=1365
        or probe["last_pre_submit_probe_age_ns"]!=125833907
        or probe["last_pre_submit_probe_age_at_tail_end_ns"]!=131117292
        or probe["last_pre_submit_probe_queue_count"]!=0
        or probe["last_pre_submit_probe_dropped_count"]!=0
        or probe["tail_elapsed_ns"]!=5283385
        or probe["direct_exit_time_queue_depth_observed"] is not False):
        raise ValueError("not the original software-success Stage360 context")
    host=parse_failed_host_stop(original["host_stop"])
    return {
        "schema":"vh-stage361-authentic-success-probe-forensic-replay/v1",
        "result":VERIFIED,"original_neXium_run_id":RUN_ID,
        "original_sources_sha256":PINS,
        "original_guest_stage313_348_351_357_360_reaudited":True,
        "tail_reason_code":7,"wait_result_raw":0,
        "software_lease_pages_acquired":1366,
        "software_lease_pages_released":1366,
        "software_lease_abandoned_sessions":0,
        "last_pre_submit_probe_attempt":1361,
        "normal_submit_attempts_at_tail":1365,
        "pre_submit_queue_count_at_old_probe_only":0,
        "last_pre_submit_probe_age_at_tail_begin_ns":125833907,
        "last_pre_submit_probe_age_at_tail_end_ns":131117292,
        "tail_software_interval_ns":5283385,
        "last_probe_is_not_exit_queue_depth":True,
        "matched_timeout_stage360_source_available":False,
        "underlying_kernel_wait_site_uniquely_proven":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_run_overall_success":False,
        **host,
    }

def archive_paths(root:Path)->dict[str,Path]:
    if not root.is_dir() or any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError("missing or linked archive root")
    paths={}
    for key,name in FILES.items():
        hits=list(root.rglob(name))
        if len(hits)!=1:
            raise ValueError("missing or ambiguous original archive file: "+name)
        p=hits[0]
        if not p.is_file() or any(q.is_symlink() for q in (p,*p.parents)):
            raise ValueError("missing or linked original archive source")
        if p.stat().st_size>128*1024:
            raise ValueError("oversized original diagnostic source")
        paths[key]=p
    return paths

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("refuse overwrite source verification report")
        report=recheck(archive_paths(args.archive_root))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if any(x.is_symlink() for x in (args.output,*args.output.parents)):
            raise ValueError("unsafe output path")
        with args.output.open("x",encoding="utf-8") as stream:
            json.dump(report,stream,sort_keys=True,indent=2)
            stream.write("\n")
        print(json.dumps({"result":VERIFIED,"guest_source_verified":True,
            "original_full_run_success":False,"host_stage303_passed":False,
            "hardware_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps({"result":"STAGE361_ORIGINAL_ARCHIVE_NOT_VERIFIED",
            "error_kind":type(error).__name__,
            "original_run_overall_success":False,
            "hardware_audio_verified":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
