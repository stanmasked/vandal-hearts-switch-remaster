#!/usr/bin/env python3
"""Stage336: rebind a fresh NeXium source capture to its own exact NRO build.

Compare source-replayed Stage334's original guest/host CSV evidence with the
archived per-run receipt; independently bind the PCM host monitor's original
NRO SHA-256 to the checked *same-workflow* NRO preflight and Actions
run/attempt identity. A later capture may differ in software measurements.

No sound, original PS1 asset, sample-clock sync, physical Nintendo Switch or
third-party runner attestation is claimed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import (
    SCHEMA as STAGE334_SCHEMA,
    RESULT as STAGE334_RESULT,
    audit_original_capture,
    load as load_original,
)

SCHEMA="vh-stage336-original-real-neXium-source-capture-to-build-binding/v1"
RESULT="ORIGINAL_NEXIUM_GUEST_HOST_SOURCES_BOUND_TO_SAME_RUN_NRO"
HEX40=re.compile(r"[0-9a-f]{40}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")
DIGEST_FIELDS=(
    "original_guest_history_csv_sha256",
    "original_guest_last_call_csv_sha256",
    "original_host_legacy_csv_sha256",
    "original_host_monotonic_csv_sha256",
)


def bind_sources(source:dict,saved:dict,preflight:dict,monitor:dict,
                 *,git_sha:str,run_id:int,run_attempt:int)->dict:
    if (not isinstance(saved,dict) or not isinstance(preflight,dict)
            or not isinstance(monitor,dict)
            or not isinstance(git_sha,str) or not HEX40.fullmatch(git_sha)
            or type(run_id) is not int or run_id<1
            or type(run_attempt) is not int or run_attempt<1):
        raise ExitTimelineError("missing source receipts or invalid exact GitHub Actions execution identity")
    authenticated=audit_original_capture(source)
    if (saved!=authenticated or saved.get("schema")!=STAGE334_SCHEMA
            or saved.get("result")!=STAGE334_RESULT
            or saved.get("original_stage320_322_325_receipts_recomputed_from_exact_sources") is not True
            or saved.get("original_stage304_305_strict_success_receipts_checked") is not True
            or saved.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ExitTimelineError("saved original Stage334 source replay differs from original evidence")
    digest=preflight.get("nro_sha256")
    if (preflight.get("result")!="SAME_WORKFLOW_BUILD_ARTIFACT_HASH_AND_STRUCTURE_VERIFIED"
            or preflight.get("git_sha")!=git_sha
            or type(preflight.get("run_id")) is not int or preflight["run_id"]!=run_id
            or type(preflight.get("run_attempt")) is not int
            or preflight["run_attempt"]!=run_attempt
            or preflight.get("nro_filename")!="vandal-hearts-prototype.nro"
            or type(preflight.get("nro_bytes")) is not int
            or preflight["nro_bytes"]<1024
            or not isinstance(digest,str) or not HEX64.fullmatch(digest)
            or preflight.get("hardware_status")!="HARDWARE NOT TESTED"):
        raise ExitTimelineError("NRO preflight is not bound to this exact Actions run and commit")
    if (monitor.get("source_nro_sha256")!=digest
            or monitor.get("hardware_status")!="HARDWARE NOT TESTED"
            or monitor.get("recording")!="virtual PulseAudio null-sink monitor; not audible playback"
            or monitor.get("sample_format")!="s16le stereo 48000Hz"
            or type(monitor.get("raw_bytes")) is not int
            or monitor["raw_bytes"]<=0):
        raise ExitTimelineError("original host PCM recording source/NRO build identity not confirmed")
    if any(not isinstance(authenticated.get(k),str)
           or not HEX64.fullmatch(authenticated[k]) for k in DIGEST_FIELDS):
        raise ExitTimelineError("original guest or host source digest absent")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "github_git_sha":git_sha,
        "github_run_id":run_id,
        "github_run_attempt":run_attempt,
        "source_nro_sha256":digest,
        "source_nro_bytes":preflight["nro_bytes"],
        "host_monitor_source_nro_sha256":monitor["source_nro_sha256"],
        "original_csv_sha256":{k:authenticated[k] for k in DIGEST_FIELDS},
        "original_guest_last_software_duration_ns":
            authenticated["original_guest_last_call_duration_software_ns"],
        "original_guest_prior_lower_median_software_ns":
            authenticated["original_guest_prior_lower_median_software_ns"],
        "original_guest_last_first_possible_rank":
            authenticated["original_guest_last_call_first_possible_rank"],
        "original_host_control_intervals":authenticated["original_host_control_deltas"],
        "same_run_nro_bytes_and_host_monitor_source_digest_checked":True,
        "original_stage320_322_325_guest_host_receipts_replayed_again":True,
        "strict_original_stage304_305_receipts_preserved":True,
        "source_run_identity_is_not_independent_external_attestation":True,
        "guest_software_timestamps_not_converted_to_host_pcm_clock":True,
        "absolute_guest_and_host_timestamps_not_published":True,
        "original_soundtrack_and_audible_quality_unverified":True,
        "physical_Nintendo_Switch_audio_tested":False,
    }



def verify_monitor_quality(monitor:dict,quality:dict)->None:
    """Cross-check original NRO-bearing monitor metadata against later PCM analysis.

    The source capture report and the derived quality report have different
    schemas. The quality analysis alone does not contain an NRO source hash.
    """
    digest=quality.get("pcm_sha256")
    if (monitor.get("schema")!="vh-nexium-pcm-monitor/v1"
            or quality.get("schema")!="vh-nexium-pcm-quality/v1"
            or quality.get("hardware_status")!="HARDWARE NOT TESTED"
            or quality.get("format")!="s16le stereo 48000 Hz"
            or quality.get("bytes")!=monitor.get("raw_bytes")
            or type(quality.get("bytes")) is not int
            or quality["bytes"]<=0 or quality["bytes"]%4
            or not isinstance(digest,str) or not HEX64.fullmatch(digest)
            or quality.get("audible_music_confirmed") is not False
            or quality.get("original_soundtrack_confirmed") is not False):
        raise ExitTimelineError("original NRO-bearing monitor and independent PCM quality receipts disagree")


def read_json(path:Path,*,max_bytes:int=64_000)->dict:
    if (path.is_symlink() or not path.is_file()
            or not 0<path.stat().st_size<=max_bytes):
        raise ExitTimelineError("missing, symlinked, empty or oversized source receipt")
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):
        raise ExitTimelineError("invalid original source report type")
    return data


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
            raise ExitTimelineError("refuse overwrite of original NeXium source-to-build receipt")
        source=load_original(a.evidence_root)
        doc=bind_sources(
            source,
            read_json(a.evidence_root/"source-guest-host-stage334.json"),
            read_json(a.nro_preflight,max_bytes=4096),
            read_json(a.evidence_root/"pcm-monitor-report.json"),
            git_sha=a.git_sha,run_id=a.run_id,run_attempt=a.run_attempt)
        verify_monitor_quality(
            read_json(a.evidence_root/"pcm-monitor-report.json"),
            read_json(a.evidence_root/"pcm-quality-report.json"))
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(doc,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":doc["result"],
            "github_run_id":doc["github_run_id"],
            "original_guest_last_software_duration_ns":doc[
                "original_guest_last_software_duration_ns"],
            "source_nro_sha256":doc["source_nro_sha256"],
            "physical_audio_verified":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE336_ORIGINAL_SOURCE_TO_NRO_RUN_BINDING_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
