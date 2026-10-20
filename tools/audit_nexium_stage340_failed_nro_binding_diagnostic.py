#!/usr/bin/env python3
"""Stage340: read-only gate-level diagnosis of a failed genuine Stage336 source bind.

This does NOT replace Stage336 acceptance. Checks are limited to source
receipt equality, current-run NRO preflight identity and monitor source SHA.
Do not publish absolute source epochs, PCM contents or proprietary assets.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import audit_original_capture, load
from audit_nexium_stage336_capture_build_binding import bind_sources, read_json

SCHEMA="vh-stage340-failed-original-nro-source-binding-gate-diagnostic/v1"
RESULT="FAILED_ORIGINAL_STAGE336_BINDING_GATE_IDENTIFIED"
HEX40=re.compile(r"[0-9a-f]{40}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")

def inspect_bind(receipt:dict,saved:dict,preflight:dict,monitor:dict,
                 *,git_sha:str,run_id:int,run_attempt:int)->str:
    """Return first failed gate, never treating diagnostics as source approval."""
    if (not isinstance(receipt,dict) or not isinstance(saved,dict)
            or not isinstance(preflight,dict) or not isinstance(monitor,dict)
            or not isinstance(git_sha,str) or not HEX40.fullmatch(git_sha)
            or type(run_id) is not int or run_id<1
            or type(run_attempt) is not int or run_attempt<1):
        return "invalid_argument_or_receipt_type"
    if (saved!=receipt or
            saved.get("schema")!="vh-stage334-single-real-NeXium-guest-and-host-original-source-manifest/v1" or
            saved.get("result")!="ORIGINAL_GUEST_SOFTWARE_AND_HOST_CLOCK_SOURCES_INDEPENDENTLY_REPLAYED" or
            saved.get("original_stage320_322_325_receipts_recomputed_from_exact_sources") is not True or
            saved.get("original_stage304_305_strict_success_receipts_checked") is not True or
            saved.get("physical_Nintendo_Switch_audio_tested") is not False):
        return "original_stage334_saved_receipt_not_identical_to_source_replay"
    if preflight.get("result")!="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED":
        return "NRO_preflight_result_not_verified"
    if preflight.get("git_sha")!=git_sha:
        return "NRO_preflight_commit_does_not_match_capture"
    if type(preflight.get("run_id")) is not int or preflight["run_id"]!=run_id:
        return "NRO_preflight_run_id_does_not_match_capture"
    if type(preflight.get("run_attempt")) is not int or preflight["run_attempt"]!=run_attempt:
        return "NRO_preflight_run_attempt_does_not_match_capture"
    if preflight.get("nro_filename")!="vandal-hearts-prototype.nro":
        return "NRO_preflight_filename_invalid"
    if type(preflight.get("nro_bytes")) is not int or preflight["nro_bytes"]<1024:
        return "NRO_preflight_size_invalid"
    digest=preflight.get("nro_sha256")
    if not isinstance(digest,str) or not HEX64.fullmatch(digest):
        return "NRO_preflight_SHA256_invalid"
    if preflight.get("hardware_status")!="HARDWARE NOT TESTED":
        return "NRO_preflight_hardware_claim_invalid"
    if monitor.get("source_nro_sha256")!=digest:
        return "host_monitor_NRO_SHA256_differs_from_preflight"
    if monitor.get("hardware_status")!="HARDWARE NOT TESTED":
        return "host_monitor_hardware_claim_invalid"
    if monitor.get("recording")!="virtual PulseAudio null-sink monitor; not audible playback":
        return "host_monitor_recording_scope_invalid"
    if monitor.get("sample_format")!="s16le stereo 48000Hz":
        return "host_monitor_sample_format_invalid"
    if type(monitor.get("raw_bytes")) is not int or monitor["raw_bytes"]<=0:
        return "host_monitor_source_byte_count_invalid"
    for name in (
        "original_guest_history_csv_sha256",
        "original_guest_last_call_csv_sha256",
        "original_host_legacy_csv_sha256",
        "original_host_monotonic_csv_sha256",
    ):
        value=receipt.get(name)
        if not isinstance(value,str) or not HEX64.fullmatch(value):
            return "original_guest_or_host_source_SHA256_invalid"
    return "all_visible_Stage336_binding_gates_pass"

def diagnose(root:Path,preflight_path:Path,*,git_sha:str,run_id:int,run_attempt:int)->dict:
    receipt=audit_original_capture(load(root))
    saved=read_json(root/"source-guest-host-stage334.json")
    preflight=read_json(preflight_path,max_bytes=4096)
    monitor=read_json(root/"pcm-quality-report.json")
    gate=inspect_bind(receipt,saved,preflight,monitor,git_sha=git_sha,
                      run_id=run_id,run_attempt=run_attempt)
    accepted=False
    if gate=="all_visible_Stage336_binding_gates_pass":
        try:
            checked=bind_sources(load(root),saved,preflight,monitor,
                                 git_sha=git_sha,run_id=run_id,run_attempt=run_attempt)
            accepted=checked.get("result")=="ORIGINAL_NEXIUM_GUEST_HOST_SOURCES_BOUND_TO_SAME_RUN_NRO"
        except (ExitTimelineError,ValueError,KeyError,TypeError):
            gate="strict_Stage336_rejects_after_visible_gates"
    return {
        "schema":SCHEMA,"result":RESULT,"first_gate":gate,
        "strict_Stage336_replay_accepts_source":accepted,
        "original_archived_audio_capture_is_not_accepted_by_diagnostic":True,
        "all_absolute_host_and_guest_epochs_omitted":True,
        "no_PCS_PCM_or_original_soundtrack_published":True,
        "no_guest_host_sample_clock_alignment_proven":True,
        "physical_Nintendo_Switch_audio_tested":False,
    }

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-root",type=Path,required=True)
    p.add_argument("--nro-preflight",type=Path,required=True)
    p.add_argument("--git-sha",required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--run-attempt",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output.is_symlink() or a.output.exists():
            raise ExitTimelineError("refuse overwrite original failed capture diagnostic")
        doc=diagnose(a.evidence_root,a.nro_preflight,git_sha=a.git_sha,
                     run_id=a.run_id,run_attempt=a.run_attempt)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(doc,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps(doc,sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as e:
        print(json.dumps({"result":"STAGE340_DIAGNOSTIC_UNAVAILABLE",
                          "error_kind":type(e).__name__,
                          "physical_Nintendo_Switch_audio_tested":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
