#!/usr/bin/env python3
"""Stage273: fail-closed 200ms host ALSA counter snapshots with stream identity.

Does not measure Rust CPAL callback period or prove a guest audout deadlock.
A 200ms reporter is a changed workload and is killed with host NeXium.
"""
import argparse
import csv
import json
from pathlib import Path

SCHEMA="vh-map02-alsa-lifetime-snapshots/v1"
KINDS={"T","S"}

def parse(path,first_input_ns=None,last_observation_ns=None):
    with path.open(encoding="ascii",newline="") as inp:
        rows=list(csv.reader(inp))
    if not rows or len(rows)>10000:
        raise ValueError("Missing or unbounded periodic ALSA counters")
    beats=[]
    per_stream={}
    latest=None
    for index,fields in enumerate(rows):
        if len(fields)!=11 or fields[0] not in KINDS:
            raise ValueError(f"Malformed ALSA counter row {index}")
        try:
            t,ident,rate,ch,period,buf,writes,mmaps,frames,errors=map(int,fields[1:])
        except ValueError as exc:
            raise ValueError(f"Non-integer ALSA counters at row {index}") from exc
        if (t<=0 or min(ident,rate,ch,period,buf,writes,mmaps,frames,errors)<0
                or ident>100000 or rate>2000000 or ch>64):
            raise ValueError(f"Impossible ALSA lifetime values at row {index}")
        if fields[0]=="T":
            if ident or any((rate,ch,period,buf,writes,mmaps,frames,errors)):
                raise ValueError("Heartbeat must not masquerade as stream")
            if latest is not None and t<=latest:
                raise ValueError("Nonmonotonic heartbeat")
            if beats and t-beats[-1]>2000000000:
                raise ValueError("Host snapshot gap exceeds 2 seconds")
            beats.append(t)
            latest=t
        else:
            if not ident or latest!=t:
                raise ValueError("Stream counter lacks matching heartbeat")
            records=per_stream.setdefault(ident,[])
            if records:
                prev=records[-1]
                if t<=prev["t"] or any(now<prev[name] for name,now in
                    (("write_calls",writes),("mmap_calls",mmaps),
                     ("positive_frames",frames),("errors",errors))):
                    raise ValueError("Decreased counters or duplicate stream timestamp")
            if (rate==48000 and ch==2 and
                (period==0 or buf<period)):
                raise ValueError("Invalid 48k stereo hardware configuration")
            records.append({"t":t,"rate_hz":rate,"channels":ch,
                            "period_frames":period,"buffer_frames":buf,
                            "write_calls":writes,"mmap_calls":mmaps,
                            "positive_frames":frames,"errors":errors})
    if len(beats)<8 or beats[-1]-beats[0]<1000000000:
        raise ValueError("Host lifetime trace is too short")
    if not per_stream:
        raise ValueError("No independent ALSA stream ordinal was captured")
    first_input=first_input_ns
    final=last_observation_ns
    if first_input is not None or final is not None:
        if not(type(first_input) is int and type(final) is int and
               beats[0]<=first_input<final and beats[0]<beats[-1] and
               first_input<beats[-1] and
               beats[-1]>=final-1000000000 and
               first_input-beats[0]>=500000000):
            raise ValueError("Guest input/final markers not bracketed by host snapshots")
    def key(row):
        return (row["rate_hz"],row["channels"])
    totals={}
    for ident,events in sorted(per_stream.items()):
        eligible=[e for e in events if e["rate_hz"]==48000 and e["channels"]==2]
        other=[e for e in events if e["rate_hz"]!=48000 or e["channels"]!=2]
        label="mixed" if eligible and other else ("48k_stereo" if eligible else "other_or_unknown")
        # Approximate controller-input window: compare a snapshot no
        # later than the first input to the latest sampled state close to
        # the final observation. No baseline => unknown, not zero.
        before_input=[e for e in events
                      if first_input is not None and e["t"]<=first_input]
        close_to_final=[e for e in events
                        if final is not None and
                        final-1000000000<=e["t"]<=beats[-1]]
        coverage=bool(before_input and close_to_final)
        baseline=before_input[-1] if coverage else None
        final_sample=close_to_final[-1] if coverage else None
        totals[str(ident)]={
            "input_to_final_sample_window_covered":coverage,
            "input_to_final_sample_delta_write_calls":(
                final_sample["write_calls"]-baseline["write_calls"]
                if coverage else None),
            "input_to_final_sample_delta_positive_frames":(
                final_sample["positive_frames"]-baseline["positive_frames"]
                if coverage else None),
            "format_class":label,
            "sampled_snapshots":len(events),
            "first_ns":events[0]["t"],"last_ns":events[-1]["t"],
            "observed_write_calls":events[-1]["write_calls"],
            "observed_mmap_calls":events[-1]["mmap_calls"],
            "observed_positive_frames":events[-1]["positive_frames"],
            "observed_errors":events[-1]["errors"],
            "observed_rate_channel_pairs":sorted(
                {f'{e["rate_hz"]}/{e["channels"]}' for e in events}),
            "sampled_first_last_delta_write_calls":
                events[-1]["write_calls"]-events[0]["write_calls"],
            "sampled_first_last_delta_positive_frames":
                events[-1]["positive_frames"]-events[0]["positive_frames"],
        }
    return {
        "schema":SCHEMA,
        "result":"PERIODIC_HOST_ALSA_COUNTER_SNAPSHOTS_RECORDED",
        "heartbeat_count":len(beats),
        "heartbeat_first_ns":beats[0],
        "heartbeat_last_ns":beats[-1],
        "observed_span_ms":(beats[-1]-beats[0])/1000000,
        "guest_input_markers_checked":first_input is not None,
        "first_input_ns":first_input,
        "last_guest_observation_ns":final,
        "sample_interval_nominal_ms":200,
        "sample_gap_max_ms":max((b-a)/1000000 for a,b in zip(beats,beats[1:])),
        "sample_prefix_and_killed_exit_not_exact_lifetime":True,
        "per_stream":totals,
        "original_game_pcm_captured":False,
        "instrumentation_changes_host_scheduling":True,
        "direct_cpal_rust_callback_captured":False,
        "guest_audout_permanent_deadlock_proven":False,
        "physical_nintendo_switch_speaker_proven":False,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace",type=Path,required=True)
    p.add_argument("--first-input-marker",type=Path,required=True)
    p.add_argument("--last-observation-marker",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        first=int(a.first_input_marker.read_text().strip())
        end=int(a.last_observation_marker.read_text().strip())
        result=parse(a.trace,first,end)
        rc=0
    except (OSError,ValueError,UnicodeError,csv.Error) as exc:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
                "direct_cpal_rust_callback_captured":False,
                "guest_audout_permanent_deadlock_proven":False,
                "physical_nintendo_switch_speaker_proven":False}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return rc

if __name__=="__main__":
    raise SystemExit(main())
