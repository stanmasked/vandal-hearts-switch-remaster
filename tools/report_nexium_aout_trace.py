#!/usr/bin/env python3
"""Summarize NeXium's existing AudioOut trace WITHOUT exporting addresses.

NeXium source: nexium-kernel/src/services/audio_out/handlers.rs:
NEXIUM_AUDIO_TRACE gates up to 128 host log::info! '[aout-trace]' messages.
NEXIUM_LOG_LEVEL=info and NEXIUM_DATA_ROOT make its *file* logger readable.
The trace observes the emulator's decoded guest AudioOut append operation;
it does not prove host DAC / speakers / continuous playback.
"""
import argparse
import json
import re
from pathlib import Path

MARKER=re.compile(r"\[aout-trace\]\s+n=(\d+)\b")
FIELD={
    "frames":re.compile(r"\bframes=(\d+)\b"),
    "pcm_nonzero":re.compile(r"\bpcm_nonzero=(\d+)\b"),
    "pcm_peak":re.compile(r"\bpcm_peak=(\d+)\b"),
    "pushed_frames":re.compile(r"\bpushed_frames=(\d+)\b"),
    "queued":re.compile(r"\bqueued=(\d+)\b"),
    "sink_present":re.compile(r"\bsink_present=(true|false)\b"),
    "started":re.compile(r"\bstarted=(true|false)\b"),
    "pcm_read":re.compile(r"\bpcm_read=(true|false)\b")
}

def parse(raw):
    if not isinstance(raw,str): raise ValueError("A NeXium text log is required")
    startup=("=== NeXium" in raw or "Nintendo Switch Emulator" in raw)
    events=[]
    seen=set()
    for line in raw.splitlines():
        m=MARKER.search(line)
        if not m: continue
        serial=int(m.group(1))
        if serial<1 or serial>128 or serial in seen:
            raise ValueError("AudioOut trace serial invalid or duplicated")
        seen.add(serial)
        event={"n":serial}
        for name,regex in FIELD.items():
            mm=regex.search(line)
            if not mm:
                raise ValueError("Incomplete AudioOut trace field: "+name)
            event[name]=mm.group(1)=="true" if name in ("sink_present","started","pcm_read") else int(mm.group(1))
        if event["pcm_nonzero"]>2*event["frames"] or event["pushed_frames"]>event["frames"]:
            raise ValueError("AudioOut samples/frames impossible")
        events.append(event)
    if events and [e["n"] for e in events]!=list(range(1,len(events)+1)):
        raise ValueError("Discontinuous AudioOut trace serials")
    # Output explicitly omits addresses, tags, buffer headers, guest memory,
    # file paths and any decoded sample payload.
    return {
        "schema":"vh-map02-nexium-aout-trace-audit/v1",
        "nexium_file_logger_started":startup,
        "trace_event_count":len(events),
        "has_audio_out_append_events":bool(events),
        "has_nonzero_guest_pcm_append":any(e["pcm_nonzero"]>0 for e in events),
        "positive_frame_append_count":sum(e["frames"]>0 for e in events),
        "nonzero_append_count":sum(e["pcm_nonzero"]>0 for e in events),
        "total_appended_frames":sum(e["frames"] for e in events),
        "append_events":events,
        "trace_limit_first_128_only":True,
        "actual_physical_switch_audio_proven":False,
        "continuous_audio_without_silent_gaps_proven":False,
        "note":"Emulator AudioOut IPC append trace only; absence is meaningful only when logger initialization is separately confirmed"
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nexium-log",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--require-logger",action="store_true")
    a=ap.parse_args()
    try:
        data=parse(a.nexium_log.read_text(encoding="utf-8",errors="replace"))
    except (OSError,ValueError) as ex:
        data={"schema":"vh-map02-nexium-aout-trace-audit/v1",
              "parse_error":str(ex),"nexium_file_logger_started":False,
              "has_audio_out_append_events":False,
              "actual_physical_switch_audio_proven":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data,sort_keys=True,indent=2))
    return 1 if "parse_error" in data or (
        a.require_logger and not data.get("nexium_file_logger_started")) else 0

if __name__=="__main__":
    raise SystemExit(main())
