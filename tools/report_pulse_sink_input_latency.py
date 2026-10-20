#!/usr/bin/env python3
"""Parse captured PulseAudio sink inputs without assuming requested latency.

A machine-readable observation from a host monitor snapshot, not proof that
a latency hint was honored or a physical audio device was exercised.
"""
import argparse
import json
import re
from pathlib import Path

HEADER=re.compile(r"^Sink Input #(\d+)\s*$",re.M)
SAMPLE=re.compile(r"^\s*Sample Specification:\s*(\S+)\s+(\d+)ch\s+(\d+)Hz\s*$",re.M)
BUFFER=re.compile(r"^\s*Buffer Latency:\s*(\d+)\s+usec\s*$",re.M)
SINK=re.compile(r"^\s*Sink Latency:\s*(\d+)\s+usec\s*$",re.M)
CORKED=re.compile(r"^\s*Corked:\s*(yes|no)\s*$",re.M)
APP=re.compile(r'^\s*application\.name\s*=\s*"([^"]+)"\s*$',re.M)
MEDIA=re.compile(r'^\s*media\.name\s*=\s*"([^"]+)"\s*$',re.M)
METHOD=re.compile(r"^\s*Resample method:\s*(\S+)\s*$",re.M)


def first(pattern,block,cast=str):
    m=pattern.search(block)
    return cast(m.group(1)) if m else None


def parse_snapshot(content):
    if not isinstance(content,str):
        raise ValueError("Sink snapshot must be UTF-8 text")
    starts=list(HEADER.finditer(content))
    result=[]
    for i,m in enumerate(starts):
        block=content[m.end():starts[i+1].start() if i+1<len(starts) else len(content)]
        sample=SAMPLE.search(block)
        entry={
            "input_id":int(m.group(1)),
            "format":sample.group(1) if sample else None,
            "channels":int(sample.group(2)) if sample else None,
            "rate_hz":int(sample.group(3)) if sample else None,
            "buffer_latency_us":first(BUFFER,block,int),
            "sink_latency_us":first(SINK,block,int),
            "corked":first(CORKED,block),
            "application":first(APP,block),
            "media":first(MEDIA,block),
            "resample_method":first(METHOD,block)
        }
        result.append(entry)
    return result


def summarize(during,after):
    snapshots={"during":parse_snapshot(during),"after":parse_snapshot(after)}
    relevant={}
    for key,entries in snapshots.items():
        matches=[v for v in entries
                 if v["channels"]==2 and v["rate_hz"]==48000
                 and v["application"]=="ALSA plug-in [nexium]"
                 and v["media"]=="ALSA Playback"]
        relevant[key]=matches
    return {
        "schema":"vh-map02-pulse-sink-input-observation/v1",
        "observed_client_inputs":snapshots,
        "nexium_stereo_48k_matches":relevant,
        "unique_target_each_snapshot":all(len(v)==1 for v in relevant.values()),
        "buffer_latency_us":{
            key:matches[0]["buffer_latency_us"] if len(matches)==1 else None
            for key,matches in relevant.items()
        },
        "sink_latency_us":{
            key:matches[0]["sink_latency_us"] if len(matches)==1 else None
            for key,matches in relevant.items()
        },
        "requested_latency_hint_was_honored_proven":False,
        "physical_switch_dac_or_speaker_proven":False
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--during",type=Path,required=True)
    ap.add_argument("--after",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        data=summarize(a.during.read_text(),a.after.read_text())
    except (OSError,UnicodeError,ValueError) as exc:
        data={"schema":"vh-map02-pulse-sink-input-observation/v1",
              "unique_target_each_snapshot":False,
              "error":str(exc),
              "requested_latency_hint_was_honored_proven":False,
              "physical_switch_dac_or_speaker_proven":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data,sort_keys=True,indent=2))
    return 0 if data.get("unique_target_each_snapshot") else 1

if __name__=="__main__":
    raise SystemExit(main())
