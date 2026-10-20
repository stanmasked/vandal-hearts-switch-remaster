#!/usr/bin/env python3
"""Independent exact-artifact Stage292 21/22-ms CPAL/AudioOut comparison.

Actual JPG/PNG/raw PCM and host counter CSV are independently redecoded.
Expected guest stall is NOT falsely called successful eight-page guest audio.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys

from audit_map02_cpal_lifecycle_snapshots import parse as parse_cpal
from decode_map02_prejoin_stage import decode_image as decode_prejoin
from decode_map02_audout_presubmit import decode
from decode_map02_guest_scene_trace import decode_packet_image

SCHEMA="vh-map02-stage292-one-pair-cpal-optical-independent-audit/v1"
HOST_SHA="c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
RESEARCH_SOURCE="04b20024a50327091cff430eb5c28e4722d4ec76"
RUNS={21:39496853360,22:39495636729}
SOURCE_HEADS={21:"2c5397f7fc14f608f8c26c64c393465277831942",
              22:"4a789d841f276cf0cc8656ad32b04de61272e8ad"}


def require(ok,msg):
    if not ok: raise ValueError(msg)


def json_obj(path):
    obj=json.loads(path.read_text(encoding="utf-8"))
    require(type(obj) is dict,f"{path}: object expected")
    return obj


def check_trial(folder,ms):
    root=Path(folder)
    require(root.is_dir() and not root.is_symlink(),"Actual unlinked evidence directory needed")
    context=json_obj(root/"pinned-host-and-nro.json")
    require(context["schema"]==f"vh-map02-stage{291 if ms==21 else 290}-guest-host-pair/v1",
            "Guest source context schema mismatch")
    require(context["new_host_executable_sha256"]==HOST_SHA,
            "Not one exact compiled NeXium host SHA across guest trials")
    require(context["guest_nro_sha256"]==NRO_SHA,
            "Not one exact ROM-free research NRO SHA across guest trials")
    require(context["guest_original_research_source_sha"]==RESEARCH_SOURCE,
            "Guest NRO compilation source differs")
    require(context["actual_new_trial_run_id"]==RUNS[ms] and
            context["old_guest_artifact_run_id"]==39460035568 and
            context["trial_attempt"]==1 and context["pulse_hint_ms"]==ms,
            "Wrong actual run or attempt / pulse latency classification")
    hostidentity=json_obj(root/"host-identity.json")
    require(hostidentity["result"]=="EXACT_STAGE287_LIFECYCLE_HOST_SHA_VERIFIED" and
            hostidentity["observed_elf_sha256"]==HOST_SHA,
            "Independent host ELF source/hash receipt does not match")
    pre=json_obj(root/"guest-prejoin-stage.json")
    actually_pre=decode_prejoin(root/"guest-prejoin.png")
    require(pre==actually_pre,"Prejoin optical JSON disagrees with real PNG pixels")
    require(pre["result"]=="PREJOIN_STAGE_SNAPSHOT_CAPTURED",
            "Guest magenta-panel clock not independently decoded")
    require(not pre["audout_service_stall_proven"],
            "Prejoin cannot prove permanent guest service stall")
    final=json_obj(root/"guest-final-receipt.json")
    try:
        observed_final=decode(decode_packet_image(root/"guest-final.png"))
    except (OSError,ValueError,TypeError) as exc:
        observed_final={"schema":"vh-map02-presubmit-optical/v1",
                        "result":"GUEST_PRESUBMIT_UNVERIFIED",
                        "reason":str(exc),
                        "live_dac_samples_proven":False,
                        "physical_switch_speaker_audio_verified":False}
    require(final==observed_final,"Final optical JSON disagrees with raw PNG decoding")

    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    cp=parse_cpal(root/"host-cpal-audioout-timeline.csv",first,last)
    require(cp==json_obj(root/"host-cpal-lifecycle-audit.json"),
            "Host CPAL saved report does not match raw timestamp CSV")
    require(cp["guest_monotonic_window_verified"] is True,
            "No real pre-input/final-window host CPAL evidence")
    pcm_report=json_obj(root/"virtual-pcm-health.json")
    raw=(root/"virtual-pulse-48k-stereo-s16le.pcm").read_bytes()
    require(100000<len(raw)<100000000 and len(raw)%4==0,
            "Raw virtual 48k/stereo PCM is missing/invalid")
    require(pcm_report["raw_sha256"]==hashlib.sha256(raw).hexdigest() and
            pcm_report["bytes"]==len(raw) and
            pcm_report["valid_pcm16le_stereo"] is True,
            "Raw capture SHA, bytes or format do not match saved report")
    samples=array("h")
    samples.frombytes(raw)
    if sys.byteorder!="little": samples.byteswap()
    nonzero=sum(v!=0 for v in samples)
    require(nonzero==pcm_report["nonzero_pcm16_samples"],
            "Real nonzero PCM count changed since receipt")
    require(not pcm_report["physical_switch_dac_proven"],
            "Virtual sink cannot prove physical Nintendo Switch DAC")
    delta=cp["guest_window_atomic_counter_deltas"]
    return {
        "hint_ms":ms,
        "actual_source_run_id":RUNS[ms],
        "compiled_host_sha256":HOST_SHA,
        "generated_research_nro_sha256":NRO_SHA,
        "guest_prejoin_stage":pre["stage_name"],
        "prejoin_audout_entries":pre["audout_playbuffer_call_entries"],
        "prejoin_audout_returns":pre["audout_playbuffer_call_returns"],
        "guest_final_optical_result":final["result"],
        "guest_final_optical_page_count":final.get("observed_pages",0),
        "actual_raw_virtual_pcm_sha256":hashlib.sha256(raw).hexdigest(),
        "actual_raw_virtual_pcm_bytes":len(raw),
        "actual_nonzero_pcm16_samples":nonzero,
        "host_sample_count":cp["samples"],
        "host_observed_span_ms":cp["observation_ms"],
        "host_callback_status":cp["guest_window_observation"],
        "cpal_lifecycle_final_state":cp["final_lifecycle_state"],
        "cpal_lifecycle_final_name":cp["final_lifecycle_name"],
        "cpal_error_callbacks_after_input":delta["error_callbacks"],
        "cpal_input_window_proven":cp["guest_monotonic_window_verified"],
        "cpal_entries_after_input":delta["cpal_entries"],
        "cpal_returns_after_input":delta["cpal_returns"],
        "cpal_output_frames_after_input":delta["cpal_output_frames"],
        "audioout_appends_after_input":delta["audioout_appends"],
        "audioout_accepted_frames_after_input":delta["audioout_accepted_frames"],
        "audioout_releases_after_input":delta["audioout_releases"],
        "actual_raw_png_pcm_cpal_evidence_redecoded":True,
    }


def classify(t):
    completed=(
        t["guest_prejoin_stage"]=="CLEANUP_COMPLETED" and
        t["prejoin_audout_entries"]==t["prejoin_audout_returns"]>0 and
        t["guest_final_optical_result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED" and
        t["guest_final_optical_page_count"]==8 and
        t["actual_nonzero_pcm16_samples"]>0 and
        t["cpal_entries_after_input"]==t["cpal_returns_after_input"]>0 and
        t["audioout_appends_after_input"]>0 and
        t["audioout_releases_after_input"]>0
    )
    pending=(
        t["guest_prejoin_stage"]=="ENTERED_PLAYBUFFER" and
        t["prejoin_audout_entries"]>t["prejoin_audout_returns"] and
        t["guest_final_optical_result"]=="GUEST_PRESUBMIT_UNVERIFIED" and
        t["actual_nonzero_pcm16_samples"]==0 and
        t["cpal_entries_after_input"]==0 and
        t["cpal_returns_after_input"]==0 and
        t["audioout_appends_after_input"]==0
    )
    return ("GUEST_COMPLETED_CRC_8_PAGES_WITH_VIRTUAL_PCM" if completed else
            "GUEST_AUDOUT_RETURN_PENDING_AT_FINITE_PREJOIN" if pending else
            "OTHER_OR_UNVERIFIED_RUNTIME_BEHAVIOR")


def compare(t21,t22):
    require(t21["hint_ms"]==21 and t22["hint_ms"]==22,
            "Not expected requested 21/22ms pair")
    require(t21["compiled_host_sha256"]==t22["compiled_host_sha256"]==HOST_SHA and
            t21["generated_research_nro_sha256"]==t22["generated_research_nro_sha256"]==NRO_SHA,
            "Host or guest NRO SHA-256 identity mismatch")
    require(t21["actual_raw_png_pcm_cpal_evidence_redecoded"] is True and
            t22["actual_raw_png_pcm_cpal_evidence_redecoded"] is True and
            t21["cpal_input_window_proven"] is True and
            t22["cpal_input_window_proven"] is True,
            "Independent raw guest optical/CPAL/PCM evidence missing")
    for record in (t21,t22):
        require(record["cpal_lifecycle_final_state"] in (0,1,2,3,4,5),
                "Invalid observed lifecycle state")
        require(record["cpal_error_callbacks_after_input"]>=0,
                "CPAL error callback counter not verified")
    a,b=classify(t21),classify(t22)
    stable=(a=="GUEST_AUDOUT_RETURN_PENDING_AT_FINITE_PREJOIN" and
            b=="GUEST_COMPLETED_CRC_8_PAGES_WITH_VIRTUAL_PCM")
    return {
        "schema":SCHEMA,
        "result":("ONE_NEW_ELF_21_22_GUEST_CONTRAST_VERIFIED" if stable
                  else "TWO_COMPLETE_ARCHIVES_SHOW_DIFFERENT_OR_MIXED_RESULTS"),
        "exact_nexium_lifecycle_elf_sha256":HOST_SHA,
        "same_rom_free_research_guest_nro_sha256":NRO_SHA,
        "requested_pulse_latency_hints_ms":[21,22],
        "host_lifecycle_and_error_counters_independently_reparsed":True,
        "real_raw_guest_png_and_virtual_pcm_independently_checked":True,
        "same_new_compiled_elf_and_generated_guest_nro":True,
        "one_matched_pair_not_repeated_sampling":True,
        "both_21_and_22_lifecycle_error_count_measured":True,
        "host_error_callback_invocation_does_not_alone_imply_audio_failure":True,
        "host_lifecycle_play_success_not_guarantee_of_current_activity":True,
        "error_counter_does_not_include_per_callback_timestamps":True,
        "pending_guest_call_not_permanent_deadlock_proof":True,
        "requested_pulse_hint_is_not_measured_alsa_period":True,
        "physical_nintendo_switch_dac_proven":False,
        "original_ps1_music_or_game_rom_used":False,
        "trials":[dict(t21,behavior=a),dict(t22,behavior=b)],
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run21",required=True,type=Path)
    ap.add_argument("--run22",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    try:
        data=compare(check_trial(a.run21,21),check_trial(a.run22,22))
        rc=0
    except (OSError,UnicodeError,ValueError,KeyError,TypeError,OverflowError,
            json.JSONDecodeError) as exc:
        data={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
              "cpal_root_cause_or_permanent_guest_deadlock_proven":False,
              "physical_switch_dac_verified":False}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":
    raise SystemExit(main())
