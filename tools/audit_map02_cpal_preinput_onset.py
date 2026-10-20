#!/usr/bin/env python3
"""Bound first/last CPAL callback by 200ms host snapshots vs guest first input.

Stage285 never changes host/NRO and never attributes cause or infinite deadlock.
Original six PNG/PCM/CPAL archives are source-verified again by Stage283 code.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_audioout_timeline import parse as parse_host
from audit_map02_cpal_six_real_trials import verify_run, HOST, NRO

SCHEMA="vh-map02-stage285-cpal-last-callback-vs-first-input/v1"
RUN=39479885398
ATTEMPT=1
MAX_LOG_BYTES=8_000_000


def require(cond,msg):
    if not cond: raise ValueError(msg)


def raw_rows(path):
    with path.open("r",encoding="ascii",newline="") as f:
        raw=list(csv.reader(f))
    rows=[]
    for index,fields in enumerate(raw):
        require(len(fields)==9 and fields[0]=="T",
                f"Malformed host callback reporter row {index}")
        values=[int(field) for field in fields[1:]]
        rows.append({"ns":values[0],"entered":values[1],
                     "returned":values[2],"output_frames":values[3],
                     "appends":values[5],"releases":values[7]})
    return rows


def onset(rows,guest_input_ns,final_ns):
    """Each first/last callback is interval-censored, not a precise timestamp."""
    require(len(rows)>=8 and rows[0]["ns"]<guest_input_ns<final_ns,
            "Missing pre-input/final host callback timeline")
    assert all(rows[i]["ns"]<rows[i+1]["ns"] for i in range(len(rows)-1))
    pre=[r for r in rows if r["ns"]<=guest_input_ns]
    require(pre,"No actual pre-input callback snapshot")
    base=pre[-1]
    near=[r for r in rows if final_ns-1_000_000_000<=r["ns"]<=final_ns]
    require(near,"No actual final-window snapshot")
    last=near[-1]
    prev=None
    increases=[]
    for sample in rows:
        if prev is None:
            if sample["entered"]>0:
                increases.append({"lower_ns":None,"upper_ns":sample["ns"],
                                  "first_sample_already_positive":True})
        elif sample["entered"]>prev["entered"]:
            increases.append({"lower_ns":prev["ns"],"upper_ns":sample["ns"],
                              "first_sample_already_positive":False})
        prev=sample
    inc_before=[event for event in increases
                if event["upper_ns"]<=guest_input_ns]
    inc_after=[event for event in increases
               if event["upper_ns"]>guest_input_ns]
    last_before=inc_before[-1] if inc_before else None
    idle_pre=(guest_input_ns-last_before["upper_ns"])/1e6 if last_before else None
    post_delta=last["entered"]-base["entered"]
    ret_delta=last["returned"]-base["returned"]
    require(post_delta>=0 and ret_delta>=0,"Counter rolled back in guest window")
    if post_delta==0 and base["entered"]>0 and idle_pre is not None and idle_pre>=1000:
        state="CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT"
    elif post_delta==0 and base["entered"]>0:
        state="NO_NEW_CALLBACKS_AFTER_INPUT_PREINPUT_ONSET_UNRESOLVED"
    elif post_delta==0:
        state="NO_CALLBACKS_OBSERVED_IN_INPUT_WINDOW"
    else:
        state="CALLBACKS_CONTINUED_AFTER_GUEST_INPUT"
    return {
        "classification":state,
        "first_reporter_sample_ns":rows[0]["ns"],
        "first_sample_entered":rows[0]["entered"],
        "input_marker_ns":guest_input_ns,
        "final_marker_ns":final_ns,
        "pre_input_snapshots":len(pre),
        "input_to_final_host_snapshots":sum(
            guest_input_ns<r["ns"]<=final_ns for r in rows),
        "cpal_entries_at_pre_input_baseline":base["entered"],
        "cpal_returns_at_pre_input_baseline":base["returned"],
        "cpal_entries_after_guest_input":post_delta,
        "cpal_returns_after_guest_input":ret_delta,
        "last_observed_preinput_callback_increase_upper_ns":
            last_before["upper_ns"] if last_before else None,
        "last_observed_preinput_callback_increase_lower_ns":
            last_before["lower_ns"] if last_before else None,
        "last_observed_preinput_callback_increase_left_censored":
            last_before["first_sample_already_positive"] if last_before else None,
        "lower_bound_ms_between_last_preinput_increase_and_input":idle_pre,
        "any_increase_interval_after_guest_input":len(inc_after)>0,
        "host_callback_timing_is_interval_censored":True,
        "host_reporter_cannot_measure_exact_callback_timestamps":True,
    }


def host_log_summary(path):
    require(path.is_file() and not path.is_symlink(),
            "Missing actual host console log")
    data=path.read_bytes()
    require(len(data)<=MAX_LOG_BYTES,"Unbounded host log")
    text=data.decode("utf-8",errors="replace")
    logs=[line.lower() for line in text.splitlines()]
    cp=[s for s in logs if "cpal stream error" in s]
    disabled=[s for s in logs if "audio output disabled:" in s]
    return {
        "host_console_sha256":hashlib.sha256(data).hexdigest(),
        "host_console_size_bytes":len(data),
        "logged_cpal_stream_error_line_count":len(cp),
        "logged_audio_output_disabled_line_count":len(disabled),
        "absence_of_logged_error_does_not_prove_no_error":True,
        "host_console_contains_no_original_pcm_decode_in_this_audit":True,
    }


def verify_one(folder,hint,repeat):
    # Stage283's independently confirmed strict source/PNG/PCM checker is not
    # replaced: first verify the complete original underlying archived files.
    original=verify_run(folder,hint,repeat,RUN,ATTEMPT)
    f=Path(folder)
    before=int((f/"guest-first-input-monotonic-ns.txt").read_text().strip())
    final=int((f/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    timeline=f/"host-cpal-audioout-timeline.csv"
    parsed=parse_host(timeline,before,final)
    require(parsed["result"]=="BOUNDED_CPAL_AUDIOOUT_COUNTER_TIMELINE_PARSED",
            "Prior strict host timeline audit no longer passes")
    x=onset(raw_rows(timeline),before,final)
    require(x["cpal_entries_after_guest_input"]==
            original["cpal_callback_entries"],
            "Pre-input callback timing differs from verified guest-window counter")
    x.update(host_log_summary(f/"nexium-guest-stdout.log"))
    return {
        "hint_ms":hint,
        "repeat":repeat,
        "original_run_id":RUN,
        "original_archive_host_sha256":original["identical_compiled_host_sha256"],
        "original_archive_nro_sha256":original["identical_generated_nro_sha256"],
        "original_guest_optical_result":original["strict_guest_result"],
        "original_virtual_nonzero_pcm16":original["nonzero_virtual_pcm16"],
        "source_png_pcm_and_cpal_reverified":True,
        **x,
    }


def aggregate(rows):
    require(len(rows)==6 and {(r["hint_ms"],r["repeat"]) for r in rows}
            =={(h,i) for h in (21,22) for i in (1,2,3)},
            "All six separately identified real archives required")
    require(all(r["original_archive_host_sha256"]==HOST and
                r["original_archive_nro_sha256"]==NRO and
                r["source_png_pcm_and_cpal_reverified"] is True for r in rows),
            "Original paired research binary source/PCM evidence changed")
    quiet=[r for r in rows if r["hint_ms"]==21]
    live=[r for r in rows if r["hint_ms"]==22]
    pre_stop=all(r["classification"]==
                 "CALLBACK_ALREADY_QUIET_AT_LEAST_1S_BEFORE_GUEST_INPUT"
                 for r in quiet)
    post_live=all(r["classification"]=="CALLBACKS_CONTINUED_AFTER_GUEST_INPUT"
                  for r in live)
    return {
        "schema":SCHEMA,
        "result":"SIX_REAL_GUEST_CPAL_PREINPUT_TIMING_AUDITED",
        "same_elf_and_nro_across_six":True,
        "original_source_run_id":RUN,
        "observed_21ms_stopped_at_least_1s_before_input_in_all_three":pre_stop,
        "observed_22ms_callback_progress_after_input_in_all_three":post_live,
        "counts_are_200ms_snapshots_not_exact_callback_instants":True,
        "cpal_audio_backend_cause_proven":False,
        "controller_input_caused_stream_stop_proven":False,
        "permanent_audout_deadlock_proven":False,
        "physical_switch_dac_output_proven":False,
        "original_game_soundtrack_tested":False,
        "trials":sorted(rows,key=lambda r:(r["hint_ms"],r["repeat"])),
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        results=aggregate([verify_one(a.root/f"hint{h}-repeat{i}",h,i)
                           for h in (21,22) for i in (1,2,3)])
        code=0
    except (OSError,ValueError,TypeError,KeyError,IndexError,
            json.JSONDecodeError,UnicodeError,csv.Error) as exc:
        results={
            "schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
            "cpal_audio_backend_cause_proven":False,
            "permanent_audout_deadlock_proven":False,
            "physical_switch_dac_output_proven":False,
        }
        code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    print(json.dumps(results,indent=2,sort_keys=True))
    return code


if __name__=="__main__":
    raise SystemExit(main())
