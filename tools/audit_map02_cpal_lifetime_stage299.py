#!/usr/bin/env python3
"""Stage299 independent source-pinned opt-in CPAL P+L reporter validator.

Stage298's P rows share a sample clock and cumulative CPAL-entry snapshot with
the existing real L reporter; only NON-RT host lifecycle transitions are exact
timestamped. No stream pause/drop, future callbacks or hardware state inferred
from a missing marker, and no precise callback event time from the 200ms samples.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_lifecycle_snapshots import parse as parse_l

SCHEMA="vh-map02-stage299-real-cpal-lifetime-p-timestamp-audit/v1"
EVENTS=("build_begin_ns","build_ok_ns","build_fail_ns",
        "play_begin_ns","play_ok_ns","play_fail_ns","drop_ns")
MAX_ROWS=240

def require(test,why):
    if not test:
        raise ValueError(why)

def read_p(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),"Real P reporter path absent")
    raw=path.read_bytes()
    require(80<=len(raw)<=50000,"P reporter missing or exceeds bounded size")
    try:
        rows=list(csv.reader(raw.decode("ascii").splitlines()))
    except UnicodeError as exc:
        raise ValueError("P reporter must be ASCII") from exc
    require(8<=len(rows)<=MAX_ROWS,"P reporter expected 8..240 rows")
    output=[]
    for n,row in enumerate(rows):
        require(len(row)==10 and row[0]=="P",f"Malformed Stage298 P row {n}")
        try:
            vals=[int(x) for x in row[1:]]
        except ValueError as e:
            raise ValueError("P reporter contains non-integer field") from e
        require(all(0<=v<=2**64-1 for v in vals) and vals[0]>0,
                "P reporter monotonic timestamp/uint64 invalid")
        obj={"sample_ns":vals[0], **dict(zip(EVENTS,vals[1:8])),
             "cpal_entry_counter":vals[8]}
        if output:
            prev=output[-1]
            require(prev["sample_ns"]<obj["sample_ns"]<=prev["sample_ns"]+2_000_000_000,
                    "P sample time gap/ordering invalid")
            require(prev["cpal_entry_counter"]<=obj["cpal_entry_counter"],
                    "P CPAL entry counter decreased")
            for key in EVENTS:
                old,new=prev[key],obj[key]
                require(old==0 or old==new,"Lifecycle event timestamp changed or vanished: "+key)
        output.append(obj)
    return output

def analyze(p_path,l_path,first_input_ns,last_observation_ns):
    require(type(first_input_ns) is int and type(last_observation_ns) is int
            and 0<first_input_ns<last_observation_ns,
            "Expected actual monotonic guest input and last-observation markers")
    raw_l=parse_l(l_path,first_input_ns,last_observation_ns)
    require(raw_l["result"]=="BOUNDED_LIFECYCLE_ATOMIC_SNAPSHOTS_PARSED"
            and raw_l["guest_monotonic_window_verified"] is True,
            "Original 11-column L reporter cannot be authenticated")
    rows=read_p(p_path)
    with Path(l_path).open("r",encoding="ascii",newline="") as f:
        lrows=list(csv.reader(f))
    lcounts={int(row[1]):int(row[4]) for row in lrows}
    require(len(lcounts)==len(lrows),"Duplicate original L timestamps")
    require(all(p["sample_ns"] in lcounts and
                p["cpal_entry_counter"]==lcounts[p["sample_ns"]]
                for p in rows),"P samples do not match exact same-tick original L callback counters")
    require(rows[0]["sample_ns"] <= first_input_ns-500_000_000 and
            rows[-1]["sample_ns"] >= last_observation_ns-1_000_000_000,
            "P telemetry does not span pre-input and final observation")
    require(rows[-1]["sample_ns"]<=last_observation_ns,
            "P telemetry contains sample beyond final guest marker")

    final=rows[-1]
    events={key:final[key] for key in EVENTS}
    order=["build_begin_ns","build_ok_ns","play_begin_ns","play_ok_ns"]
    if all(events[k] for k in order):
        values=[events[k] for k in order]
        require(values==sorted(values),"Build/play monotonic event ordering impossible")
    for positive,fail in (("build_ok_ns","build_fail_ns"),
                          ("play_ok_ns","play_fail_ns")):
        require(not(events[positive] and events[fail]),
                "Mutually exclusive build/play outcomes both recorded")
    require(events["build_fail_ns"]==0 or (
            events["build_begin_ns"]>0 and
            events["build_begin_ns"]<=events["build_fail_ns"]),
            "Build failure preceded build attempt")
    require(events["play_fail_ns"]==0 or (
            events["play_begin_ns"]>0 and
            events["play_begin_ns"]<=events["play_fail_ns"]),
            "Play failure preceded play attempt")
    require(events["drop_ns"]==0 or
            (events["play_ok_ns"]>0 and events["drop_ns"]>=events["play_ok_ns"]),
            "Retained stream guard was dropped before successful play")
    # Only source-tagged P event stamps claim exact CLOCK_MONOTONIC times.
    # Read-only callback counts may change between reporter samples.
    first_callback_positive=next((i for i,x in enumerate(rows)
                                  if x["cpal_entry_counter"]>0),None)
    if first_callback_positive is None:
        first_callback_bracket=None
        callback_status="NO_POSITIVE_CPAL_ENTRY_COUNTER_IN_P_SAMPLES"
    elif first_callback_positive==0:
        first_callback_bracket=None
        callback_status="INITIAL_P_COUNTER_ALREADY_POSITIVE_NO_FIRST_CALLBACK_TIME"
    else:
        before=rows[first_callback_positive-1]["sample_ns"]
        after=rows[first_callback_positive]["sample_ns"]
        first_callback_bracket=[before,after]
        callback_status="FIRST_POSITIVE_COUNTER_BRACKETED_BY_P_SNAPSHOTS"
    pre=[p for p in rows if p["sample_ns"]<=first_input_ns]
    near=[p for p in rows if
          last_observation_ns-1_000_000_000<=p["sample_ns"]<=last_observation_ns]
    require(pre and near,"P guest measurement window lacks bounding samples")
    deltas=near[-1]["cpal_entry_counter"]-pre[-1]["cpal_entry_counter"]
    require(deltas>=0,"Decreasing P guest-window callback count")
    status=("HOST_PLAY_SUCCEEDED_DROP_OBSERVED"
            if events["play_ok_ns"] and events["drop_ns"] else
            "HOST_PLAY_SUCCEEDED_NO_RETAINED_DROP_OBSERVED"
            if events["play_ok_ns"] else
            "HOST_PLAY_FAILURE_OBSERVED"
            if events["play_fail_ns"] else
            "HOST_BUILD_FAILURE_OBSERVED"
            if events["build_fail_ns"] else
            "HOST_BUILD_OR_PLAY_OUTCOME_UNVERIFIED")
    return {
        "schema":SCHEMA,
        "result":"REAL_SOURCE_SYNCHRONIZED_CPAL_P_AND_L_REPARSED",
        "p_rows":len(rows),
        "original_l_rows":len(lrows),
        "p_sha256":hashlib.sha256(Path(p_path).read_bytes()).hexdigest(),
        "l_sha256":hashlib.sha256(Path(l_path).read_bytes()).hexdigest(),
        "p_first_sample_clock_ns":rows[0]["sample_ns"],
        "p_final_sample_clock_ns":rows[-1]["sample_ns"],
        "first_p_cpal_entry_counter":rows[0]["cpal_entry_counter"],
        "final_p_cpal_entry_counter":rows[-1]["cpal_entry_counter"],
        "guest_window_p_cpal_entry_delta":deltas,
        "guest_window_original_l_cpal_entry_delta":
            raw_l["guest_window_atomic_counter_deltas"]["cpal_entries"],
        "non_rt_event_timestamps_ns":events,
        "first_positive_cpal_entry_observation":callback_status,
        "first_positive_callback_counter_bracket_ns":first_callback_bracket,
        "host_observed_lifetime_classification":status,
        "cumulative_counter_is_not_per_callback_exact_timestamp":True,
        "stream_play_returned_ok_does_not_prove_still_running":True,
        "no_drop_marker_does_not_prove_stream_still_owned_or_device_active":True,
        "source_contains_no_stream_pause_call":True,
        "backend_alsa_pause_or_drop_event_proven":False,
        "no_permanent_guest_deadlock_or_cpal_root_cause_proven":True,
        "physical_switch_speaker_proven":False,
        "original_game_rom_or_audio_used":False,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--p",type=Path,required=True)
    ap.add_argument("--l",type=Path,required=True)
    ap.add_argument("--first-input-marker",type=Path,required=True)
    ap.add_argument("--final-observation-marker",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        result=analyze(args.p,args.l,
            int(args.first_input_marker.read_text().strip()),
            int(args.final_observation_marker.read_text().strip()))
        status=0
    except (OSError,TypeError,ValueError,KeyError,csv.Error,UnicodeError) as e:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "backend_alsa_pause_or_drop_event_proven":False,
                "physical_switch_speaker_proven":False}
        status=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return status

if __name__=="__main__":
    raise SystemExit(main())
