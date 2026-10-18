#!/usr/bin/env python3
"""Stage338 diagnostic for one FAILED original Stage303 NeXium source capture.

Re-run existing strict Stage299->303 computations against the saved source
artifact and report the *first failing verification gate*, not a replacement
PASS result. Never alter Stage303, infer guest clock mapping or expose PCM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from analyze_nexium_pcm_stream_integrity import analyze_pair,read_report,require_file,FRAME_BYTES
from analyze_nexium_pcm_scene_silence import classify_silence
from audit_nexium_pcm_marker_uncertainty import audit_envelopes
from audit_nexium_pcm_terminal_silence import classify_recording_edges
from audit_nexium_pcm_recorder_stop import audit_recorder_stop,read_stop_events

SCHEMA="vh-stage338-failed-original-recorder-Stage303-source-diagnostic/v1"
RESULT="STAGE303_ORIGINAL_CAPTURE_DIAGNOSTIC_ONLY"
ALLOWED_STAGES={
    "stage299_source_pair_unreproducible",
    "stage300_pcm_scene_report_unreproducible",
    "stage301_envelopes_unreproducible",
    "stage302_edge_silence_unreproducible",
    "stage303_stop_csv_invalid",
    "stage303_after_wait_not_equal_raw_pcm_bytes",
    "stage303_after_wait_not_equal_stage302_pcm_bytes",
    "stage303_before_sigint_pcm_bytes_exceed_final",
    "stage303_scene_pcm_SHA_differs_from_stage302",
    "stage303_strict_replay_rejected_other",
    "stage303_strict_source_replayed_accepted",
}
FILENAMES={
    "monitor":"nexium-monitor-s16le-48k.pcm",
    "monitor_report":"pcm-quality-report.json",
    "scenes":"nexium-scenes-s16le-48k.pcm",
    "scene_report":"scene-audio-report.json",
    "events":"scene-events.csv",
    "stage299":"pcm-stream-integrity-stage299.json",
    "stage300":"pcm-scene-silence-stage300.json",
    "stage301":"pcm-marker-envelopes-stage301.json",
    "stage302":"pcm-recording-edge-silence-stage302.json",
    "stop_csv":"scene-recorder-stop.csv",
}


def bounded_stop_diagnosis(raw:bytes,stage302:dict,csv:bytes)->dict:
    """Compact fail-closed stop lifecycle check; never emit host epoch values."""
    try:
        events=read_stop_events(csv)
    except (ValueError,TypeError,KeyError):
        return {"gate":"stage303_stop_csv_invalid",
                "strict_stage303_accepted":False}
    first,second=events
    pre=first["pcm_bytes"]
    post=second["pcm_bytes"]
    frames=stage302.get("total_pcm_frames")
    expected=frames*FRAME_BYTES if type(frames) is int else None
    summary={
        "before_sigint_bytes":pre,
        "after_wait_bytes":post,
        "original_final_scene_pcm_bytes":len(raw),
        "after_wait_minus_original_final_pcm_bytes":post-len(raw),
        "buffered_bytes_after_sigint":post-pre,
        "stop_wall_interval_ms":second["host_epoch_ms"]-first["host_epoch_ms"],
        "partial_frame_before_sigint":bool(pre%FRAME_BYTES),
        "recording_bytes_not_sample_exact_guest_timestamps":True,
    }
    if post!=len(raw):
        gate="stage303_after_wait_not_equal_raw_pcm_bytes"
    elif expected!=len(raw):
        gate="stage303_after_wait_not_equal_stage302_pcm_bytes"
    elif pre>post:
        gate="stage303_before_sigint_pcm_bytes_exceed_final"
    elif hashlib.sha256(raw).hexdigest()!=stage302.get("scene_pcm_sha256"):
        gate="stage303_scene_pcm_SHA_differs_from_stage302"
    else:
        gate="stage303_strict_replay_rejected_other"
    return {"gate":gate,"strict_stage303_accepted":False,**summary}


def diagnose(root:Path)->dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("original NeXium runtime-evidence source root invalid")
    files={key:root/name for key,name in FILENAMES.items()}
    for key,p in files.items():
        if (p.is_symlink() or not p.is_file()
                or p.stat().st_size==0 or (key not in ("monitor","scenes")
                    and p.stat().st_size>1_000_000)):
            raise ValueError("missing, empty, symlinked or oversized original source")
    raw=require_file(files["scenes"],"original virtual scene PCM")
    stage299=read_report(files["stage299"])
    stage300=read_report(files["stage300"])
    stage301=read_report(files["stage301"])
    stage302=read_report(files["stage302"])
    gate=None
    if stage299!=analyze_pair(
            files["monitor"],files["monitor_report"],files["scenes"],
            files["scene_report"],files["events"]):
        gate="stage299_source_pair_unreproducible"
    elif stage300!=classify_silence(
            raw,stage299,read_report(files["scene_report"])):
        gate="stage300_pcm_scene_report_unreproducible"
    elif stage301!=audit_envelopes(raw,stage300):
        gate="stage301_envelopes_unreproducible"
    elif stage302!=classify_recording_edges(raw,stage300,stage301):
        gate="stage302_edge_silence_unreproducible"
    if gate:
        details={"gate":gate,"strict_stage303_accepted":False}
    else:
        details=bounded_stop_diagnosis(raw,stage302,files["stop_csv"].read_bytes())
        if details["gate"]=="stage303_strict_replay_rejected_other":
            try:
                audit_recorder_stop(raw,stage300,stage301,stage302,
                                    files["stop_csv"].read_bytes())
            except (ValueError,TypeError,KeyError):
                pass
            else:
                details["gate"]="stage303_strict_source_replayed_accepted"
                details["strict_stage303_accepted"]=True
    if details["gate"] not in ALLOWED_STAGES:
        raise ValueError("unrecognized diagnostic result")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "source_original_scene_pcm_sha256":hashlib.sha256(raw).hexdigest(),
        "original_stop_source_csv_sha256":hashlib.sha256(
            files["stop_csv"].read_bytes()).hexdigest(),
        "original_scene_pcm_length_bytes":len(raw),
        "original_stop_verification":details,
        "strict_Stage303_approval_not_replaced_by_diagnostic":True,
        "failed_original_artifact_is_not_a_fourth_accepted_capture":True,
        "only_original_archived_source_bytes_examined":True,
        "no_original_absolute_guest_or_host_epochs_published":True,
        "no_guest_host_clock_mapping_or_hardware_audio_claim":True,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.output.exists() or a.output.is_symlink():
            raise ValueError("refuse overwrite source failure diagnostic")
        r=diagnose(a.evidence_root)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(r,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":r["result"],
            "gate":r["original_stop_verification"]["gate"],
            "stop_size_delta":r["original_stop_verification"].get(
                "after_wait_minus_original_final_pcm_bytes"),
            "stage303_strict_accepted":r["original_stop_verification"][
                "strict_stage303_accepted"],
            "physical_audio_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        print(json.dumps({
            "result":"STAGE338_ORIGINAL_STOP_SOURCE_DIAGNOSTIC_UNAVAILABLE",
            "physical_audio_verified":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
