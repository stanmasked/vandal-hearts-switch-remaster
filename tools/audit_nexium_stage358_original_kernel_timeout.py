#!/usr/bin/env python3
"""Stage358: fourth SHA-pinned ORIGINAL NeXium source confirms Kernel TimedOut.

Replays Stage352's original Stage313/348/351 receipts and independently
checks the new Stage357 original numerical wait Result and receipt. No
additional audio service action, DAC claim or acoustic causal attribution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from audit_nexium_stage350_original_tail_vs_lease import safe_file
from audit_nexium_stage352_three_original_tail_sources import (
    reaudited_archive, VERIFIED as OLD_VERIFIED,
)
from audit_nexium_guest_tail_wait_result_stage357 import (
    parse_source as audit_raw_wait,
    VERIFIED as WAIT_VERIFIED,
)

RUN_ID=39325440778
TAPER="6ae164f7e6b2435c9ebb0126f56e74bc7ef87faa19277a198ce9af2009158ea2"
LEASE="48bef5d972d87aa4c43b71470dc637b6b0f32e0de6d819b9a3723ebf11850a41"
REASON="118d734cf6739d9b053a78b8f4fc0b285c6df84461195a1705e25fe14cf8101e"
WAIT="a1694b18ba05fa9715ae29c08a1fdc8f2836001264fe449bbc5ca2b834e8b57a"
RAW_RESULT=59905
MODULE_KERNEL=1
DESC_TIMED_OUT=117
VERIFIED="FOUR_ORIGINAL_NEIXUM_GUEST_TAIL_SOURCES_VERIFY_KERNEL_TIMED_OUT"
SOURCES={
    "tail":"audio-exit-output-000.csv",
    "lease":"audio-lease-reconciliation-000.csv",
    "reason":"audio-exit-tail-reason-000.csv",
    "wait":"audio-exit-tail-wait-result-000.csv",
    "stage313":"guest-last-audout-release-stage313.json",
    "stage314":"guest-original-audout-last-page-stage314.json",
    "stage348":"guest-lease-reconciliation-stage348.json",
    "stage351":"guest-exit-tail-reason-stage351.json",
    "stage357":"guest-exit-tail-wait-result-stage357.json",
}
STAGE357_FIELDS=(
    "schema","result","original_guest_wait_result_csv_sha256",
    "original_guest_wait_result_source_observed",
    "original_guest_wait_result_bytes_preserved",
    "stage351_reason_code","wait_result_observed","audout_wait_result_raw",
    "original_stage351_source_sha256",
    "raw_result_is_software_service_status_only",
    "underlying_result_symbolic_meaning_proven",
    "audible_dropout_or_DAC_verified",
    "physical_Nintendo_Switch_audio_tested",
    "original_guest_source_relative_path",
)

def verify(old:dict, prior351:dict, receipt357:dict,
           original_wait:bytes)->dict:
    if (not isinstance(old,dict)
        or old.get("result")!=OLD_VERIFIED
        or type(old.get("original_neXium_run_id")) is not int
        or old["original_neXium_run_id"]!=RUN_ID
        or old.get("original_guest_csv_sha256")!={
            "stage313_last_audio_page_and_tail":TAPER,
            "stage348_software_PCM_lease":LEASE,
            "stage351_exit_tail_reason":REASON,
        }
        or old.get("tail_reason_code")!=4
        or old.get("tail_reason_name")!="wait_failed"
        or old.get("tail_attempted") is not True
        or old.get("tail_descriptor_return_confirmed") is not False
        or old.get("lease_pages_acquired")!=1414
        or old.get("lease_pages_released")!=1413
        or old.get("abandoned_sessions")!=1
        or old.get("exact_archived_original_CSV_bytes_reaudited") is not True
        or old.get("three_distinct_guest_source_receipts_matched") is not True
        or old.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("Stage352 original guest triple identity not reproduced")
    if (not isinstance(original_wait,bytes)
        or hashlib.sha256(original_wait).hexdigest()!=WAIT):
        raise ValueError("Stage357 original guest raw wait Result SHA-256 changed")
    if (not isinstance(prior351,dict)
        or prior351.get("original_guest_tail_reason_csv_sha256")!=REASON
        or prior351.get("prior_stage313_and_stage348_original_bytes_reaudited") is not True):
        raise ValueError("Stage351 source receipt identity missing")
    observed=audit_raw_wait(original_wait,prior351)
    observed["original_guest_source_relative_path"]=(
        "sdmc/switch/vandal-hearts-remake/audio-exit-tail-wait-result-000.csv"
    )
    if not isinstance(receipt357,dict):
        raise ValueError("Stage357 receipt missing")
    for key in STAGE357_FIELDS:
        if (key not in observed
            or type(receipt357.get(key)) is not type(observed[key])
            or receipt357[key]!=observed[key]):
            raise ValueError("original Stage357 receipt mismatches raw guest bytes: "+key)
    raw=observed["audout_wait_result_raw"]
    module=raw & 0x1FF
    desc=(raw>>9)&0x1FFF
    if (raw!=RAW_RESULT or module!=MODULE_KERNEL
        or desc!=DESC_TIMED_OUT
        or observed.get("stage351_reason_code")!=4
        or observed.get("wait_result_observed") is not True
        or observed.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("not authenticated Kernel TimedOut from original wait")
    return {
        "schema":"vh-stage358-four-original-guest-tail-kernel-timed-out/v1",
        "result":VERIFIED,
        "original_neXium_run_id":RUN_ID,
        "source_sha256":{
            "stage313":TAPER,"stage348":LEASE,
            "stage351":REASON,"stage357":WAIT,
        },
        "software_lease_pages_acquired":1414,
        "software_lease_pages_released":1413,
        "software_abandoned_sessions":1,
        "stage351_reason_code":4,
        "stage351_reason_name":"wait_failed",
        "stage357_audout_wait_raw_result_decimal":raw,
        "stage357_audout_wait_raw_result_hex":f"0x{raw:04X}",
        "result_module":module,
        "result_description":desc,
        "result_symbolic_class":"KernelError_TimedOut",
        "all_four_original_guest_sources_independently_reaudited":True,
        "original_stage313_314_348_351_357_receipts_rechecked":True,
        "underlying_event_wait_call_site_uniquely_proven":False,
        "older_unclassified_guest_failure_cause_proven":False,
        "audible_dropout_or_DAC_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_PS1_soundtrack_verified":False,
    }

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        root=args.archive_root
        if (not root.is_dir() or
            any(path.is_symlink() for path in (root,*root.parents))):
            raise ValueError("missing or linked original NeXium artifact root")
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("cannot replace existing Stage358 source receipt")
        paths={}
        for kind,name in SOURCES.items():
            found=list(root.rglob(name))
            if len(found)!=1:
                raise ValueError("missing or ambiguous source: "+name)
            safe_file(found[0])
            paths[kind]=found[0]
        old=reaudited_archive(
            {k:paths[k] for k in (
                "tail","lease","reason","stage313","stage314","stage348","stage351"
            )},
            {"tail":TAPER,"lease":LEASE,"reason":REASON},RUN_ID
        )
        old351=json.loads(paths["stage351"].read_text(encoding="utf-8"))
        receipt357=json.loads(paths["stage357"].read_text(encoding="utf-8"))
        doc=verify(old,old351,receipt357,paths["wait"].read_bytes())
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if any(x.is_symlink() for x in (args.output,*args.output.parents)):
            raise ValueError("Stage358 output parent linked")
        with args.output.open("x",encoding="utf-8") as out:
            json.dump(doc,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({
            "result":VERIFIED,
            "raw_result":RAW_RESULT,
            "result_hex":"0xEA01",
            "description":"KernelError_TimedOut",
            "hardware_audio_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as err:
        print(json.dumps({
            "result":"ORIGINAL_GUEST_STAGE358_TIMEOUT_NOT_VERIFIED",
            "error_kind":type(err).__name__,
            "physical_Nintendo_Switch_audio_tested":False,
        },sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
