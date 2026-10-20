#!/usr/bin/env python3
"""Stage294 real NeXium GUI FileLogger CPAL error messages, ROM-free guest.

The source-pinned GUI uses FileLogger under nexium_common::paths::root()/logs;
it does not mirror log::error to stdout. Read log on the SAME guest runner,
publish only sanitized, bounded derived receipt. Do NOT upload original logs.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys

from audit_map02_cpal_error_messages_stage293 import scan_host_log
from audit_map02_cpal_lifecycle_snapshots import parse as parse_cpal
from decode_map02_prejoin_stage import decode_image as decode_prejoin
from decode_map02_guest_scene_trace import decode_packet_image
from decode_map02_audout_presubmit import decode as decode_final

SCHEMA="vh-map02-stage294-source-pinned-gui-filelogger-guest-evidence/v1"
HOST_SHA="c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"


def require(test,reason):
    if not test:
        raise ValueError(reason)


def doc(path):
    result=json.loads(Path(path).read_text())
    require(type(result) is dict,"Expected source JSON object")
    return result


def classify(pre,final,cp,nonzero):
    deltas=cp["guest_window_atomic_counter_deltas"]
    passed=(
        pre["stage_name"]=="CLEANUP_COMPLETED"
        and pre["audout_playbuffer_call_entries"]==
            pre["audout_playbuffer_call_returns"]>0
        and final["result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED"
        and final.get("observed_pages")==8
        and deltas["cpal_entries"]==deltas["cpal_returns"]>0
        and deltas["audioout_appends"]>0 and nonzero>0
    )
    pending=(
        pre["stage_name"]=="ENTERED_PLAYBUFFER"
        and pre["audout_playbuffer_call_entries"]>
            pre["audout_playbuffer_call_returns"]
        and final["result"]=="GUEST_PRESUBMIT_UNVERIFIED"
        and deltas["cpal_entries"]==deltas["cpal_returns"]==0
        and deltas["audioout_appends"]==0 and nonzero==0
    )
    return ("EIGHT_PAGE_GUEST_CRC_AND_VIRTUAL_PCM_COMPLETED" if passed else
            "GUEST_AUDOUT_RETURN_PENDING_IN_FINITE_PREJOIN" if pending else
            "OTHER_VERIFIED_OR_MIXED_AUDIO_OBSERVATION")


def real_audit(evidence,logdir,hint,run_id):
    root=Path(evidence)
    require(hint in (21,22),"Requested hint must be 21 or 22")
    require(root.is_dir() and not root.is_symlink(),"Evidence directory unavailable")
    source=doc(root/"pinned-host-and-nro.json")
    require(source.get("schema")=="vh-map02-stage294-guest-host-pair/v1"
            and source.get("pulse_hint_ms")==hint
            and source.get("actual_new_trial_run_id")==run_id
            and source.get("trial_attempt")==1
            and source.get("new_host_executable_sha256")==HOST_SHA
            and source.get("guest_nro_sha256")==NRO_SHA
            and source.get("old_guest_artifact_run_id")==39460035568,
            "Actual Stage294 run/hint/host/NRO identity mismatch")
    h=doc(root/"host-identity.json")
    require(h["result"]=="EXACT_STAGE287_LIFECYCLE_HOST_SHA_VERIFIED" and
            h["observed_elf_sha256"]==HOST_SHA,
            "Actual Stage287 host content identity receipt mismatch")
    pre=decode_prejoin(root/"guest-prejoin.png")
    require(pre==doc(root/"guest-prejoin-stage.json"),
            "Prejoin optical PNG differs from archived receipt")
    try:
        final=decode_final(decode_packet_image(root/"guest-final.png"))
    except (OSError,ValueError,TypeError) as exc:
        final={
            "schema":"vh-map02-presubmit-optical/v1",
            "result":"GUEST_PRESUBMIT_UNVERIFIED",
            "reason":str(exc),"live_dac_samples_proven":False,
            "physical_switch_speaker_audio_verified":False,
        }
    require(final==doc(root/"guest-final-receipt.json"),
            "Final optical guest PNG differs from saved CRC result")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    cp=parse_cpal(root/"host-cpal-audioout-timeline.csv",first,last)
    require(cp==doc(root/"host-cpal-lifecycle-audit.json")
            and cp["guest_monotonic_window_verified"] is True,
            "Actual CPAL lifecycle/error L-CSV differs from receipt")
    pcm=(root/"virtual-pulse-48k-stereo-s16le.pcm").read_bytes()
    p=doc(root/"virtual-pcm-health.json")
    require(100000<len(pcm)<100000000 and len(pcm)%4==0
            and p["raw_sha256"]==hashlib.sha256(pcm).hexdigest()
            and p["bytes"]==len(pcm)
            and p["valid_pcm16le_stereo"] is True
            and p["physical_switch_dac_proven"] is False,
            "Actual PCM integrity/format mismatch")
    audio=array("h")
    audio.frombytes(pcm)
    if sys.byteorder!="little": audio.byteswap()
    nonzero=sum(x!=0 for x in audio)
    require(nonzero==p["nonzero_pcm16_samples"],
            "Nonzero virtual PCM count changed from saved receipt")
    logdir=Path(logdir)
    require(logdir.is_dir() and not logdir.is_symlink(),
            "Source NeXium GUI FileLogger logs directory not found")
    logfiles=sorted(logdir.glob("nexium-????????-??????.log"))
    require(len(logfiles)==1 and logfiles[0].is_file()
            and not logfiles[0].is_symlink(),
            "Expected exactly one real GUI FileLogger for one guest process")
    messages=scan_host_log(logfiles[0])
    delta=cp["guest_window_atomic_counter_deltas"]
    classification=classify(pre,final,cp,nonzero)
    return {
        "schema":SCHEMA,
        "result":"REAL_LIFECYCLE_NEXIUM_FILELOGGER_AND_GUEST_EVIDENCE_VERIFIED",
        "requested_pulse_hint_ms":hint,
        "actual_source_run_id":run_id,
        "exact_stage287_nexium_elf_sha256":HOST_SHA,
        "exact_generated_guest_nro_sha256":NRO_SHA,
        "one_source_pinned_gui_filelogger_found":True,
        "original_gui_filelogger_path_published":False,
        "original_gui_filelogger_raw_bytes_uploaded":False,
        "full_process_filelogger_sha256":messages["original_stdout_sha256"],
        "full_process_filelogger_bytes":messages["original_stdout_bytes"],
        "full_process_cpal_error_log_lines":messages["cpal_stream_error_log_line_count_all_times"],
        "sanitized_cpal_message_groups":messages["sanitized_error_message_groups"],
        "error_groups_truncated":messages["error_groups_truncated"],
        "guest_window_cpal_error_callback_delta":delta["error_callbacks"],
        "guest_window_cpal_entries":delta["cpal_entries"],
        "guest_window_cpal_returns":delta["cpal_returns"],
        "guest_window_audioout_appends":delta["audioout_appends"],
        "guest_lifecycle_state_at_final_sample":cp["final_lifecycle_state"],
        "guest_final_optical_result":final["result"],
        "guest_prejoin_audout_entries":pre["audout_playbuffer_call_entries"],
        "guest_prejoin_audout_returns":pre["audout_playbuffer_call_returns"],
        "raw_virtual_pcm_sha256":hashlib.sha256(pcm).hexdigest(),
        "virtual_pcm_nonzero_samples":nonzero,
        "guest_observed_behavior":classification,
        "same_host_and_guest_as_previous_real_stage290_291":True,
        "filelogger_lines_cannot_be_assumed_equal_to_guest_window_count":True,
        "wall_clock_log_messages_not_monotonic_guest_event_timestamps":True,
        "lexical_error_token_not_causal_proof":True,
        "requested_pulse_hint_not_measured_cpal_hardware_period":True,
        "no_permanent_audout_deadlock_or_cpal_root_cause_proven":True,
        "physical_switch_audio_proven":False,
        "rom_or_licensed_game_audio_included":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--logdir",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        obj=real_audit(a.evidence,a.logdir,a.hint,a.run_id)
        status=0
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError,json.JSONDecodeError) as exc:
        obj={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
             "original_gui_filelogger_raw_bytes_uploaded":False,
             "no_permanent_audout_deadlock_or_cpal_root_cause_proven":True,
             "physical_switch_audio_proven":False}
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    print(json.dumps(obj,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())
