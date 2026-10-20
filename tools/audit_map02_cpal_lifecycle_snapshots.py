#!/usr/bin/env python3
"""Stage288: fail-closed observer of opt-in Stage286 NeXium CPAL lifecycle CSV.

CSV rows:
L,monotonic_ns,lifecycle_state,error_callbacks,cpal_entries,cpal_returns,
  cpal_output_frames,sink_consumed_frames,guest_audioout_appends,
  guest_audioout_accepted_frames,guest_audioout_releases

All values are cumulative atomic snapshots with nominal 200ms interval.
No per-callback event clock, guest PCM, production emulator source, or device
pause/drop state is available. Do not imply a live callback or permanent lock.
"""
import argparse
import csv
import json
from pathlib import Path

SCHEMA="vh-map02-stage288-cpal-lifecycle-snapshot-audit/v1"
FIELDS=("error_callbacks","cpal_entries","cpal_returns","cpal_output_frames",
        "sink_consumed_frames","audioout_appends","audioout_accepted_frames",
        "audioout_releases")
STATES={0:"NOT_OBSERVED",1:"BUILD_ATTEMPTED",2:"STREAM_BUILT",
        3:"STREAM_PLAY_RETURNED_OK",4:"BUILD_FAILED",5:"PLAY_FAILED"}
MAX_SAMPLES=240
MAX_GAP_NS=2_000_000_000
ALLOWED_NEXT={
    0:{0,1,2,3,4,5},  # early transitions may happen between snapshots
    1:{1,2,3,4,5},    # build -> successful play or error
    2:{2,3,5},
    3:{3},
    4:{4},
    5:{5},
}


def require(test,message):
    if not test:
        raise ValueError(message)


def parse(path,first_input_ns=None,last_observation_ns=None):
    if (first_input_ns is None)!=(last_observation_ns is None):
        raise ValueError("Both monotonic guest markers required, or neither")
    try:
        with Path(path).open("r",encoding="ascii",newline="") as f:
            lines=list(csv.reader(f))
    except UnicodeDecodeError as exc:
        raise ValueError("Non-ASCII CPAL lifecycle reporter") from exc
    require(8<=len(lines)<=MAX_SAMPLES,
            "Reporter needs 8 to 240 exact raw snapshots")
    samples=[]
    for i,row in enumerate(lines):
        require(len(row)==11 and row[0]=="L",
                f"Lifecycle reporter line {i} has wrong tag or column count")
        try:
            ints=[int(v) for v in row[1:]]
        except ValueError as exc:
            raise ValueError(f"Lifecycle reporter line {i} has noninteger field") from exc
        require(all(0<=v<=2**64-1 for v in ints),
                f"Lifecycle reporter line {i} contains non-u64 field")
        stamp,state=ints[:2]
        require(stamp>0 and state in STATES,
                f"Lifecycle reporter line {i} contains invalid monotonic clock/state")
        snap={"monotonic_ns":stamp,"lifecycle_state":state,
              **dict(zip(FIELDS,ints[2:]))}
        require(snap["cpal_returns"]<=snap["cpal_entries"],
                f"Lifecycle reporter line {i}: returns exceed entries")
        if samples:
            old=samples[-1]
            require(stamp>old["monotonic_ns"],"Nonmonotonic lifecycle sample time")
            require(stamp-old["monotonic_ns"]<=MAX_GAP_NS,
                    "Lifecycle heartbeat gap above 2 seconds")
            require(state in ALLOWED_NEXT[old["lifecycle_state"]],
                    "Impossible lifecycle state transition between snapshots")
            for key in FIELDS:
                require(snap[key]>=old[key],
                        f"Decreasing atomic lifecycle/callback counter {key}")
        samples.append(snap)
    require(samples[-1]["monotonic_ns"]-samples[0]["monotonic_ns"]>=1_000_000_000,
            "Observation span under one second")
    baseline=None
    final=None
    if first_input_ns is not None:
        require(type(first_input_ns) is int and
                type(last_observation_ns) is int and
                samples[0]["monotonic_ns"]+500_000_000<=first_input_ns
                <last_observation_ns and
                samples[-1]["monotonic_ns"]>=last_observation_ns-1_000_000_000,
                "Host lifecycle CSV does not span pre-input and final guest markers")
        before=[x for x in samples if x["monotonic_ns"]<=first_input_ns]
        near_end=[x for x in samples
                  if last_observation_ns-1_000_000_000<=x["monotonic_ns"]
                  <=last_observation_ns]
        require(before and near_end,
                "Missing actual host sample before input or near final guest clock")
        baseline=before[-1]
        final=near_end[-1]
    deltas={k:(final[k]-baseline[k] if baseline is not None else None)
            for k in FIELDS}
    if baseline is None:
        status="NO_GUEST_INPUT_MARKERS"
    elif deltas["error_callbacks"]>0:
        status="CPAL_ERROR_CALLBACK_COUNT_INCREASED_IN_GUEST_WINDOW"
    elif final["lifecycle_state"]==4:
        status="CPAL_STREAM_BUILD_FAILURE_STATE_OBSERVED"
    elif final["lifecycle_state"]==5:
        status="CPAL_STREAM_PLAY_FAILURE_STATE_OBSERVED"
    elif final["cpal_entries"]>final["cpal_returns"]:
        status="CPAL_CALLBACK_ENTRY_UNRETURNED_AT_LAST_SNAPSHOT"
    elif final["lifecycle_state"]==3 and deltas["cpal_entries"]==0:
        status="PLAY_ONCE_SUCCEEDED_BUT_NO_NEW_CPAL_ENTRY_IN_GUEST_WINDOW"
    elif deltas["cpal_entries"]>0:
        status="CPAL_CALLBACK_ENTRIES_OBSERVED_IN_GUEST_WINDOW"
    else:
        status="NO_NEW_CPAL_ENTRY_AND_NO_VERIFIED_PLAY_STATE"
    transitions=[
        {"from_state":a["lifecycle_state"],"to_state":b["lifecycle_state"],
         "not_before_monotonic_ns":a["monotonic_ns"],
         "not_after_monotonic_ns":b["monotonic_ns"]}
        for a,b in zip(samples,samples[1:])
        if a["lifecycle_state"]!=b["lifecycle_state"]
    ]
    return {
        "schema":SCHEMA,
        "result":"BOUNDED_LIFECYCLE_ATOMIC_SNAPSHOTS_PARSED",
        "samples":len(samples),
        "first_clock_ns":samples[0]["monotonic_ns"],
        "last_clock_ns":samples[-1]["monotonic_ns"],
        "observation_ms":(samples[-1]["monotonic_ns"]-
                          samples[0]["monotonic_ns"])/1e6,
        "max_observed_sample_gap_ms":max((b["monotonic_ns"]-a["monotonic_ns"])/1e6
                                     for a,b in zip(samples,samples[1:])),
        "guest_monotonic_window_verified":baseline is not None,
        "first_input_ns":first_input_ns,
        "last_guest_observation_ns":last_observation_ns,
        "baseline_clock_ns":baseline["monotonic_ns"] if baseline else None,
        "final_window_sample_clock_ns":final["monotonic_ns"] if final else None,
        "baseline_lifecycle_state":baseline["lifecycle_state"] if baseline else None,
        "final_lifecycle_state":final["lifecycle_state"] if final else None,
        "final_lifecycle_name":STATES[final["lifecycle_state"]] if final else None,
        "observed_lifecycle_transition_intervals":transitions,
        "guest_window_atomic_counter_deltas":deltas,
        "guest_window_observation":status,
        "state_3_means_play_call_returned_not_stream_still_running":True,
        "cpal_error_counter_is_not_a_timestamped_error_event":True,
        "snapshots_do_not_include_pause_drop_or_alsa_wakeup":True,
        "reporter_intrusiveness_not_qualified_by_this_parser":True,
        "exact_nexium_elf_source_sha_verified_by_this_parser":False,
        "permanent_guest_audioout_deadlock_or_cpal_root_cause_proven":False,
        "physical_switch_dac_proven":False,
        "original_game_rom_or_audio_read":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace",type=Path,required=True)
    p.add_argument("--first-input-marker",type=Path)
    p.add_argument("--final-observation-marker",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        first=(int(a.first_input_marker.read_text().strip())
               if a.first_input_marker else None)
        last=(int(a.final_observation_marker.read_text().strip())
              if a.final_observation_marker else None)
        result=parse(a.trace,first,last)
        rc=0
    except (OSError,ValueError,TypeError,UnicodeError,csv.Error) as exc:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
                "exact_nexium_elf_source_sha_verified_by_this_parser":False,
                "permanent_guest_audioout_deadlock_or_cpal_root_cause_proven":False,
                "physical_switch_dac_proven":False}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return rc


if __name__=="__main__":
    raise SystemExit(main())
