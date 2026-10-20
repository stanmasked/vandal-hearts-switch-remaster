#!/usr/bin/env python3
"""Validate 2x21/2x22ms CPAL host-only trials with zero NRO arguments.

No guest is started; its PCM, AudioOut, or physical Switch hardware are NOT
tested. Existing 200ms host reporter time series are interval-censored.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_audioout_timeline import parse as parse_cpal

SCHEMA="vh-map02-stage286-real-host-only-cpal-liveness/v1"
HOST_SHA="dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0"


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def read_json(path):
    x=json.loads(path.read_text(encoding="utf-8"))
    require(type(x) is dict,f"Expected JSON object in {path}")
    return x


def verify_trial(root,hint,repeat,run_id,attempt):
    root=Path(root)
    require(root.is_dir() and not root.is_symlink(),
            "Missing actual host-only run folder")
    identity=read_json(root/"host-only-identity.json")
    require(identity.get("schema")=="vh-map02-stage286-host-only-identity/v1",
            "Wrong host-only research receipt schema")
    for name,value in (
        ("hint_ms",hint),("repeat",repeat),("run_id",run_id),
        ("attempt",attempt),("compiled_host_sha256",HOST_SHA),
        ("launched_without_nro_argument",True),
        ("used_rom_or_licensed_game_audio",False),
        ("virtual_pulse_sample_rate",48000),
        ("runner_os","Linux"),
    ):
        require(identity.get(name)==value,f"Host-only identity mismatched: {name}")
    host=read_json(root/"host-identity.json")
    require(host["result"]=="EXACT_SOURCE_INSTRUMENTED_HOST_ELF_ARTIFACT_VERIFIED"
            and host["observed_elf_sha256"]==HOST_SHA,
            "Actual NeXium ELF provenance not verified")
    screenshot=(root/"nexium-without-nro.png").read_bytes()
    require(len(screenshot)>1024 and screenshot[:8]==b"\x89PNG\r\n\x1a\n",
            "No actual host NeXium GUI PNG evidence")
    before=int((root/"host-reference-start-monotonic-ns.txt").read_text().strip())
    after=int((root/"host-reference-final-monotonic-ns.txt").read_text().strip())
    parsed=parse_cpal(root/"host-cpal-audioout-timeline.csv",before,after)
    require(parsed["result"]=="BOUNDED_CPAL_AUDIOOUT_COUNTER_TIMELINE_PARSED"
            and parsed["guest_input_and_final_markers_verified"] is True,
            "Host-only timestamp and CPAL window invalid")
    require(parsed["sample_count"]>=20,
            "Insufficient host-only callback temporal coverage")
    log=(root/"nexium-no-rom-stdout.log").read_bytes()
    require(len(log)<=8_000_000,"Excessive host log size")
    x=parsed["guest_window_counter_deltas"]
    entries=x["cpal_entries"]
    returned=x["cpal_returns"]
    if entries==0 and returned==0:
        behavior="HOST_ONLY_NO_NEW_CPAL_CALLBACKS_IN_OBSERVATION_WINDOW"
    elif entries>0 and entries==returned:
        behavior="HOST_ONLY_CPAL_CALLBACKS_ENTERED_AND_RETURNED"
    else:
        behavior="HOST_ONLY_CPAL_ACTIVITY_OTHER_OR_UNRETURNED"
    return {
        "hint_ms":hint,
        "repeat":repeat,
        "job_run_id":run_id,
        "job_attempt":attempt,
        "same_compiled_host_sha256":HOST_SHA,
        "host_gui_png_sha256":hashlib.sha256(screenshot).hexdigest(),
        "host_stdout_sha256":hashlib.sha256(log).hexdigest(),
        "no_guest_nro_or_game_input":True,
        "host_reporter_snapshots":parsed["sample_count"],
        "host_reporter_span_ms":parsed["observed_span_ms"],
        "callback_entries_after_host_reference_start":entries,
        "callback_returns_after_host_reference_start":returned,
        "callback_output_frames_after_host_reference_start":
            x["cpal_output_frames"],
        "kernel_audioout_appends_without_guest":x["audioout_appends"],
        "host_only_behavior":behavior,
        "actual_host_cpal_source_timeline_verified":True,
        "timings_are_interval_censored_by_200ms_snapshots":True,
    }


def aggregate(records,run_id,attempt):
    require(len(records)==4 and
            {(x["hint_ms"],x["repeat"]) for x in records}
            =={(h,i) for h in (21,22) for i in (1,2)},
            "Exactly four independent hint/repeat host-only trials required")
    require(all(x["job_run_id"]==run_id and x["job_attempt"]==attempt and
                x["same_compiled_host_sha256"]==HOST_SHA and
                x["no_guest_nro_or_game_input"] is True and
                x["actual_host_cpal_source_timeline_verified"] is True
                for x in records),
            "Host-only source/run/attempt provenance changed")
    ordered=sorted(records,key=lambda x:(x["hint_ms"],x["repeat"]))
    repeated=all(x["host_only_behavior"]==(
        "HOST_ONLY_NO_NEW_CPAL_CALLBACKS_IN_OBSERVATION_WINDOW"
        if x["hint_ms"]==21 else
        "HOST_ONLY_CPAL_CALLBACKS_ENTERED_AND_RETURNED")
        for x in ordered)
    return {
        "schema":SCHEMA,
        "result":("FOUR_REAL_HOST_ONLY_RUNNERS_REPRODUCED_PULSE_HINT_CPAL_CONTRAST"
                  if repeated else
                  "FOUR_REAL_HOST_ONLY_RUNNERS_SHOW_OTHER_OR_MIXED_CPAL_BEHAVIOR"),
        "identical_host_executable_sha256":HOST_SHA,
        "source_ci_run_id":run_id,
        "source_ci_attempt":attempt,
        "no_research_nro_or_original_game_rom_used":True,
        "host_gui_and_raw_cpal_timeline_verification_passed":True,
        "two_independent_runs_per_requested_hint":True,
        "host_only_requested_hint_contrast_repeated":repeated,
        "pulse_latency_hint_not_measured_hardware_period":True,
        "guest_audioout_permanent_deadlock_proven":False,
        "specific_pulse_alsa_cpal_causal_root_proven":False,
        "physical_switch_audio_proven":False,
        "trials":ordered,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root",required=True,type=Path)
    ap.add_argument("--run-id",required=True,type=int)
    ap.add_argument("--attempt",required=True,type=int)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    try:
        records=[verify_trial(
            a.root/f"hint{h}-repeat{i}",h,i,a.run_id,a.attempt)
            for h in (21,22) for i in (1,2)]
        result=aggregate(records,a.run_id,a.attempt)
        code=0
    except (OSError,ValueError,KeyError,IndexError,TypeError,
            json.JSONDecodeError,UnicodeError) as exc:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
                "host_only_requested_hint_contrast_repeated":False,
                "guest_audioout_permanent_deadlock_proven":False,
                "specific_pulse_alsa_cpal_causal_root_proven":False,
                "physical_switch_audio_proven":False}
        code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return code


if __name__=="__main__":
    raise SystemExit(main())
