#!/usr/bin/env python3
"""Validate opt-in NeXium CPAL callback and guest AudioOut COUNTER snapshots.

Input format is the Stage274 Linux-host reporter (not guest PCM):
T,monotonic_ns,callback_enter,callback_return,output_frames,
  sink_consumed_frames,audioout_appends,audioout_accepted_frames,audioout_releases

The collector is a NEW instrumented build with different scheduling than the
nightly or previous ALSA preload. No causality, deadlock or hardware proof.
"""
import argparse
import csv
import json
from pathlib import Path

SCHEMA="vh-map02-neixum-cpal-audioout-timeline/v1"
KEYS=("cpal_entries","cpal_returns","cpal_output_frames",
      "sink_consumed_frames","audioout_appends",
      "audioout_accepted_frames","audioout_releases")
MAX_ROWS=240
MAX_GAP_NS=2_000_000_000


def parse(path, first_input_ns=None, final_observation_ns=None):
    if (first_input_ns is None)!=(final_observation_ns is None):
        raise ValueError("Both guest-clock markers required, or neither")
    try:
        with path.open("r",encoding="ascii",newline="") as handle:
            raw=list(csv.reader(handle))
    except UnicodeDecodeError as exc:
        raise ValueError("Non-ASCII or malformed host timeline") from exc
    if len(raw)<8 or len(raw)>MAX_ROWS:
        raise ValueError("Insufficient or unbounded CPAL reporter samples")
    rows=[]
    for i,line in enumerate(raw):
        if len(line)!=9 or line[0]!="T":
            raise ValueError(f"Malformed NeXium host reporter row {i}")
        try:
            vals=[int(x) for x in line[1:]]
        except ValueError as exc:
            raise ValueError(f"Noninteger host counter value in row {i}") from exc
        t=vals[0]
        if t<=0 or any(x<0 for x in vals[1:]):
            raise ValueError(f"Negative or impossible host counter in row {i}")
        if t>2**64-1 or any(x>2**64-1 for x in vals[1:]):
            raise ValueError(f"Counter outside u64 domain in row {i}")
        sample={"monotonic_ns":t, **dict(zip(KEYS,vals[1:]))}
        if sample["cpal_returns"]>sample["cpal_entries"]:
            raise ValueError(f"CPAL callback returns exceed entries at row {i}")
        if rows:
            prev=rows[-1]
            if t<=prev["monotonic_ns"]:
                raise ValueError("Nonmonotonic host CLOCK_MONOTONIC time")
            if t-prev["monotonic_ns"]>MAX_GAP_NS:
                raise ValueError("Reporter heartbeat gap exceeds 2 seconds")
            for k in KEYS:
                if sample[k]<prev[k]:
                    raise ValueError(f"Decreasing cumulative {k} at row {i}")
        rows.append(sample)

    if rows[-1]["monotonic_ns"]-rows[0]["monotonic_ns"]<1_000_000_000:
        raise ValueError("Observed CPAL timeline is too short")

    base=None
    last=None
    if first_input_ns is not None:
        if not (type(first_input_ns) is int and
                type(final_observation_ns) is int and
                rows[0]["monotonic_ns"]<=first_input_ns<final_observation_ns and
                first_input_ns-rows[0]["monotonic_ns"]>=500_000_000 and
                rows[-1]["monotonic_ns"]>=final_observation_ns-1_000_000_000):
            raise ValueError("Host reporter does not bracket guest input/final observation")
        before=[r for r in rows if r["monotonic_ns"]<=first_input_ns]
        near_end=[r for r in rows if
                  final_observation_ns-1_000_000_000<=r["monotonic_ns"]
                  <=final_observation_ns]
        if not before or not near_end:
            raise ValueError("No reliable pre-input or pre-teardown reporter sample")
        base=before[-1]
        last=near_end[-1]

    first=rows[0]
    ending=rows[-1]
    if base is None:
        differences={key:None for key in KEYS}
        ending_for_class=None
        start_for_class=None
        status="NO_GUEST_INPUT_MARKERS"
    else:
        differences={key:last[key]-base[key] for key in KEYS}
        ending_for_class=last
        start_for_class=base
        pending=last["cpal_entries"]-last["cpal_returns"]
        entered=differences["cpal_entries"]
        if pending>0:
            status="CALLBACK_ENTRY_UNRETURNED_AS_OF_LAST_SNAPSHOT"
        elif entered==0:
            status="NO_NEW_CPAL_ENTRIES_AFTER_GUEST_INPUT"
        else:
            status="CPAL_ENTERED_AND_ALL_ENTRIES_RETURNED_AT_LAST_SNAPSHOT"

    return {
        "schema":SCHEMA,
        "result":"BOUNDED_CPAL_AUDIOOUT_COUNTER_TIMELINE_PARSED",
        "sample_count":len(rows),
        "first_sample_monotonic_ns":first["monotonic_ns"],
        "last_sample_monotonic_ns":ending["monotonic_ns"],
        "observed_span_ms":(ending["monotonic_ns"]-first["monotonic_ns"])/1e6,
        "maximum_sample_gap_ms":max(
            (next_row["monotonic_ns"]-prev["monotonic_ns"])/1e6
            for prev,next_row in zip(rows,rows[1:])),
        "guest_input_and_final_markers_verified":base is not None,
        "first_guest_input_ns":first_input_ns,
        "final_guest_observation_ns":final_observation_ns,
        "pre_input_sample_monotonic_ns":(
            start_for_class["monotonic_ns"] if start_for_class else None),
        "last_valid_guest_window_sample_ns":(
            ending_for_class["monotonic_ns"] if ending_for_class else None),
        "guest_window_counter_deltas":differences,
        "last_sample_cpal_entries":ending["cpal_entries"],
        "last_sample_cpal_returns":ending["cpal_returns"],
        "last_sample_unreturned_cpal_entries":
            ending["cpal_entries"]-ending["cpal_returns"],
        "guest_window_cpal_status":status,
        "nominal_reporter_interval_ms":200,
        "reporter_max_samples":MAX_ROWS,
        "samples_are_snapshots_not_real_time_callback_duration":True,
        "host_reporter_changes_neixum_scheduling":True,
        "original_neixum_nightly_binary_equivalence_proven":False,
        "trace_bound_to_source_binary_sha256_by_this_parser":False,
        "guest_audioout_deadlock_proven":False,
        "physical_switch_dac_output_proven":False,
        "raw_game_audio_data_logged":False,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace",required=True,type=Path)
    ap.add_argument("--first-input-marker",type=Path)
    ap.add_argument("--final-observation-marker",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        first=(int(args.first_input_marker.read_text().strip())
               if args.first_input_marker is not None else None)
        final=(int(args.final_observation_marker.read_text().strip())
               if args.final_observation_marker is not None else None)
        report=parse(args.trace,first,final)
        status=0
    except (OSError,ValueError,UnicodeError,csv.Error) as exc:
        report={
            "schema":SCHEMA,
            "result":"UNVERIFIED",
            "reason":str(exc),
            "guest_audioout_deadlock_proven":False,
            "physical_switch_dac_output_proven":False,
            "trace_bound_to_source_binary_sha256_by_this_parser":False,
        }
        status=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n",
        encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())
