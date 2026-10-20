#!/usr/bin/env python3
"""Stage285: localize first/last CPAL callback *snapshot* around guest input.

No per-callback timestamp exists in Stage274's counters. A snapshot brackets
the transition, NOT an exact onset instant, CPU stack or cause of suspension.
"""
import argparse
import csv
import json
from pathlib import Path

from audit_map02_cpal_audioout_timeline import parse as verified_timeline

KEYS=("cpal_entries","cpal_returns","cpal_output_frames","sink_consumed_frames",
      "audioout_appends","audioout_accepted_frames","audioout_releases")
SCHEMA="vh-map02-stage285-cpal-callback-transition-window/v1"


def require(ok,what):
    if not ok: raise ValueError(what)


def single(path,hint,repeat):
    root=Path(path)
    identity=json.loads((root/"matrix-identity.json").read_text())
    require(identity["hint_ms"]==hint and identity["repeat"]==repeat,
            "Matrix label mismatch")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text())
    final=int((root/"guest-final-observation-monotonic-ns.txt").read_text())
    trace=root/"host-cpal-audioout-timeline.csv"
    original=verified_timeline(trace,first,final)
    require(original==json.loads((root/"host-cpal-audioout-audit.json").read_text()),
            "Original monotonic timeline receipt mismatch")
    raw=list(csv.reader(trace.open("r",encoding="ascii",newline="")))
    samples=[]
    for row in raw:
        require(len(row)==9 and row[0]=="T","Malformed original reporter row")
        vals=list(map(int,row[1:]))
        samples.append(dict(monotonic_ns=vals[0],**dict(zip(KEYS,vals[1:]))))
    before=[r for r in samples if r["monotonic_ns"]<=first]
    after=[r for r in samples if first<r["monotonic_ns"]<=final]
    require(before and after,"Missing pre-input or after-input snapshots")
    last_before=before[-1]
    differences=[]
    for prev,cur in zip(samples,samples[1:]):
        if cur["cpal_entries"]>prev["cpal_entries"]:
            differences.append((prev["monotonic_ns"],cur["monotonic_ns"],
                                cur["cpal_entries"]-prev["cpal_entries"]))
    post=[(lo,hi,n) for lo,hi,n in differences if hi>first and lo>=first]
    crossing=[(lo,hi,n) for lo,hi,n in differences if lo<first<hi]
    dur=(final-first)/1e6
    cp=original["guest_window_counter_deltas"]
    return {
        "hint_ms":hint,"repeat":repeat,
        "guest_input_marker_ns":first,"guest_final_marker_ns":final,
        "guest_window_ms":dur,
        "reporter_nominal_ms":original["nominal_reporter_interval_ms"],
        "reporter_max_gap_ms":original["maximum_sample_gap_ms"],
        "cpal_entries_before_input_at_last_sample":last_before["cpal_entries"],
        "cpal_returns_before_input_at_last_sample":last_before["cpal_returns"],
        "cpal_entries_after_input_sample_delta":cp["cpal_entries"],
        "cpal_returns_after_input_sample_delta":cp["cpal_returns"],
        "post_input_positive_entry_snapshot_intervals":len(post),
        "interval_overlapping_guest_input_has_callback_increments":len(crossing)>0,
        "first_fully_postinput_callback_interval_ns":(
            [post[0][0],post[0][1]] if post else None),
        "last_fully_postinput_callback_interval_ns":(
            [post[-1][0],post[-1][1]] if post else None),
        "kernel_audioout_appends_after_input":cp["audioout_appends"],
        "kernel_audioout_releases_after_input":cp["audioout_releases"],
        "stream_state_and_cpal_error_callback_not_in_reporter":True,
        "callback_exact_stall_onset_not_proven":True,
        "input_boundary_callbacks_could_be_unresolved":bool(crossing),
    }


def audit(root):
    cases=[single(Path(root)/f"hint{h}-repeat{i}",h,i)
           for h in (21,22) for i in (1,2,3)]
    require(len(cases)==6,"Expected six real guest trials")
    require(all(v["cpal_entries_after_input_sample_delta"]==0
                and v["post_input_positive_entry_snapshot_intervals"]==0
                for v in cases if v["hint_ms"]==21),
            "21ms no-postinput snapshot observation not reproduced")
    require(all(v["cpal_entries_after_input_sample_delta"]>0
                and v["post_input_positive_entry_snapshot_intervals"]>0
                for v in cases if v["hint_ms"]==22),
            "22ms postinput callback activity not reproduced")
    return {
        "schema":SCHEMA,
        "result":"SIX_GUEST_SNAPSHOT_TRANSITION_WINDOWS_INDEPENDENTLY_RECHECKED",
        "no_cpal_stream_lifecycle_events_available":True,
        "cannot_separate_alsa_wakeup_from_cpal_stream_pause_or_error":True,
        "cannot_infer_exact_callback_stop_time_or_causal_order":True,
        "physical_switch_audio_proven":False,
        "cases":cases,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        result=audit(a.root)
        status=0
    except (OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError) as e:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "cannot_infer_exact_callback_stop_time_or_causal_order":True}
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return status

if __name__=="__main__":
    raise SystemExit(main())
