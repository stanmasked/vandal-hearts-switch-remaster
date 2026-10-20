#!/usr/bin/env python3
"""Stage299 real opt-in new Stage298 NeXium ELF + generated NRO/PNG/PCM/P/L verification.

Never pretend that 21ms guest AudioOut finite-window pending == permanent deadlock,
or that successful stream.play means the device never stopped.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys

from audit_map02_cpal_lifetime_stage299 import analyze as analyze_p
from audit_map02_cpal_lifecycle_snapshots import parse as analyze_l
from audit_map02_cpal_error_messages_stage293 import scan_host_log
from decode_map02_prejoin_stage import decode_image as decode_prejoin
from decode_map02_guest_scene_trace import decode_packet_image
from decode_map02_audout_presubmit import decode as decode_final

SCHEMA="vh-map02-stage299-real-new-elf-lifetime-guest-evidence/v1"
ELF_SHA="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
ELF_SOURCE_SHA="e801588983a866c76dcedb52e818859a68ad113d"
AUDIO_SOURCE_SHA="dca4066830d132317ec4ae57f90b1943b785ea871f078844d1ff7da7fcb5040d"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
LOCK_SHA="e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739"

def require(value,reason):
    if not value:
        raise ValueError(reason)

def load(path):
    x=json.loads(Path(path).read_text())
    require(isinstance(x,dict),"Expected exact source JSON object")
    return x

def re_decode(evidence,logdir,hint,run_id):
    p=Path(evidence)
    require(hint in (21,22) and type(run_id) is int and run_id>0,
            "Real requested Pulse hint and Actions run identity missing")
    require(p.is_dir() and not p.is_symlink(),"Evidence directory absent")
    provenance=load(p/"stage299-pinned-new-host-guest.json")
    require(provenance["schema"]=="vh-map02-stage299-pinned-new-elf-and-generated-nro/v1"
        and provenance["stage298_build_run_id"]==39509934054
        and provenance["stage298_build_source_sha"]==ELF_SOURCE_SHA
        and provenance["original_nro_artifact_run_id"]==39460035568
        and provenance["guest_original_research_source_sha"]=="04b20024a50327091cff430eb5c28e4722d4ec76"
        and provenance["exact_stage298_elf_sha256"]==ELF_SHA
        and provenance["exact_generated_nro_sha256"]==NRO_SHA
        and provenance["hint_ms"]==hint
        and provenance["actual_stage299_run_id"]==run_id
        and provenance["attempt"]==1
        and provenance["rom_or_licensed_audio_used"] is False
        and provenance["physical_switch_speaker_proven"] is False,
        "New experimental NeXium and original generated NRO source pairing mismatch")
    build=load(p/"stage298-source-pinned-build-manifest.json")
    require(build["schema"]=="vh-map02-stage298-nexium-cpal-timestamped-host-build/v1"
        and build["result"]=="STAGE298_OPT_IN_TIMESTAMPED_NEXIUM_LINUX_BINARY_COMPILED"
        and build["executable_sha256"]==ELF_SHA
        and build["research_head_sha"]==ELF_SOURCE_SHA
        and build["pinned_upstream_source_sha"]=="089562567a0a8760dfdd8420e1f57c35159a9219"
        and build["cargo_lock_sha256"]==LOCK_SHA
        and build["lifecycle_instrumented_audio_source_sha256"]==AUDIO_SOURCE_SHA
        and build["cpu_backend"]=="rustarmic" and build["build_profile"]=="release"
        and build["stage298_separate_cpal_lifetime_p_csv"] is True
        and build["stage298_non_rt_build_play_drop_timestamps"] is True
        and build["stage298_original_l_csv_unchanged"] is True
        and build["stage298_same_original_cpal_callbacks"] is True
        and build["physical_nintendo_switch_audio_proven"] is False,
        "Stage298 real compiled binary manifest not authenticated")
    first=int((p/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((p/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    original_l=analyze_l(p/"host-cpal-audioout-timeline.csv",first,last)
    require(original_l==load(p/"host-cpal-lifecycle-audit.json")
        and original_l["guest_monotonic_window_verified"] is True,
        "Stage298 real L lifecycle CSV re-parse disagrees with archive")
    lifetime=analyze_p(p/"host-cpal-lifetime-p.csv",p/"host-cpal-audioout-timeline.csv",
                       first,last)
    require(lifetime==load(p/"host-cpal-lifetime-audit.json")
            and lifetime["result"]=="REAL_SOURCE_SYNCHRONIZED_CPAL_P_AND_L_REPARSED",
            "Stage298 real P lifecycle clock evidence re-parse mismatch")
    pre=decode_prejoin(p/"guest-prejoin.png")
    require(pre==load(p/"guest-prejoin-stage.json"),
            "Actual prejoin PNG does not match guest stage receipt")
    try:
        final=decode_final(decode_packet_image(p/"guest-final.png"))
    except (ValueError,OSError,TypeError) as exc:
        final={"schema":"vh-map02-presubmit-optical/v1",
               "result":"GUEST_PRESUBMIT_UNVERIFIED","reason":str(exc),
               "live_dac_samples_proven":False,
               "physical_switch_speaker_audio_verified":False}
    require(final==load(p/"guest-final-receipt.json"),
            "Actual final PNG CRC does not match recorded guest optical result")
    pcm=(p/"virtual-pulse-48k-stereo-s16le.pcm").read_bytes()
    h=load(p/"virtual-pcm-health.json")
    require(100000<len(pcm)<100000000 and len(pcm)%4==0
            and h["raw_sha256"]==hashlib.sha256(pcm).hexdigest()
            and h["bytes"]==len(pcm)
            and h["valid_pcm16le_stereo"] is True
            and h["physical_switch_dac_proven"] is False,
            "Actual raw virtual PCM format/identity mismatch")
    samples=array("h")
    samples.frombytes(pcm)
    if sys.byteorder!="little":samples.byteswap()
    nonzero=sum(x!=0 for x in samples)
    require(nonzero==h["nonzero_pcm16_samples"],
            "Actual PCM differs from saved nonzero count")
    logdir=Path(logdir)
    require(logdir.is_dir() and not logdir.is_symlink(),
            "True GUI NeXium FileLogger directory not available")
    files=sorted(logdir.glob("nexium-????????-??????.log"))
    require(len(files)==1 and files[0].is_file() and not files[0].is_symlink(),
            "Not exactly one real GUI FileLogger for one guest")
    messages=scan_host_log(files[0])
    require(messages["original_stdout_bytes"]>0,"Empty real GUI FileLogger")
    return {
       "schema":SCHEMA,
       "result":"REAL_STAGE299_NEW_SHA_PINNED_P_L_GUEST_FILELOGGER_VERIFIED",
       "actual_run_id":run_id,"hint_ms":hint,
       "stage298_compiled_elf_sha256":ELF_SHA,
       "original_generated_nro_sha256":NRO_SHA,
       "stage298_build_source_sha":ELF_SOURCE_SHA,
       "stage298_build_run_id":39509934054,
       "actual_P_reporter_redecoded":True,
       "actual_original_L_reporter_redecoded":True,
       "actual_guest_prejoin_and_final_png_redecoded":True,
       "actual_virtual_pcm_sha256_and_nonzero_count_redecoded":True,
       "true_gui_filelogger_bounded_sanitized":True,
       "raw_gui_filelogger_uploaded":False,
       "gui_filelogger_sha256":messages["original_stdout_sha256"],
       "gui_filelogger_raw_bytes":messages["original_stdout_bytes"],
       "gui_filelogger_cpal_error_lines_entire_process":
           messages["cpal_stream_error_log_line_count_all_times"],
       "gui_filelogger_sanitized_reason_groups":
           messages["sanitized_error_message_groups"],
       "guest_prejoin_stage":pre["stage_name"],
       "guest_prejoin_audout_calls":pre["audout_playbuffer_call_entries"],
       "guest_prejoin_audout_returns":pre["audout_playbuffer_call_returns"],
       "guest_final_optical_result":final["result"],
       "guest_8_pages_crc_verified":final["result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED",
       "host_P_play_ok_ns":lifetime["non_rt_event_timestamps_ns"]["play_ok_ns"],
       "host_P_drop_ns":lifetime["non_rt_event_timestamps_ns"]["drop_ns"],
       "host_P_first_callback_observation":lifetime["first_positive_cpal_entry_observation"],
       "host_P_first_callback_bracket_ns":lifetime["first_positive_callback_counter_bracket_ns"],
       "host_P_first_counter":lifetime["first_p_cpal_entry_counter"],
       "host_P_last_counter":lifetime["final_p_cpal_entry_counter"],
       "host_P_guest_window_callback_delta":lifetime["guest_window_p_cpal_entry_delta"],
       "host_L_guest_window_callback_delta":
           original_l["guest_window_atomic_counter_deltas"]["cpal_entries"],
       "host_L_guest_window_error_callback_delta":
           original_l["guest_window_atomic_counter_deltas"]["error_callbacks"],
       "virtual_pcm_nonzero_samples":nonzero,
       "host_lifetime_status":lifetime["host_observed_lifetime_classification"],
       "no_per_callback_exact_timestamp_or_backend_pause_probe":True,
       "new_instrumentation_may_perturb_cpal_timing":True,
       "no_cpal_root_cause_or_permanent_deadlock_proven":True,
       "physical_switch_audio_proven":False,
       "original_ps1_music_or_gameplay_rom_used":False,
    }

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--evidence",type=Path,required=True)
    a.add_argument("--logdir",type=Path,required=True)
    a.add_argument("--hint",type=int,required=True)
    a.add_argument("--run-id",type=int,required=True)
    a.add_argument("--output",type=Path,required=True)
    v=a.parse_args()
    try:
        r=re_decode(v.evidence,v.logdir,v.hint,v.run_id);code=0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,
            json.JSONDecodeError) as e:
        r={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
           "no_cpal_root_cause_or_permanent_deadlock_proven":True,
           "physical_switch_audio_proven":False}
        code=1
    v.output.parent.mkdir(parents=True,exist_ok=True)
    v.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True))
    return code
if __name__=="__main__":
    raise SystemExit(main())
