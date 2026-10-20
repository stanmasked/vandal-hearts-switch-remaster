#!/usr/bin/env python3
"""Validate bounded opt-in ALSA host interposer trace; no guest/audio samples.

ALSA calls may be made on CPAL's Linux backend, but observing them does NOT
measure the Rust CPAL callback itself, nor prove an audout service stall.
"""
import argparse
import csv
import json
from pathlib import Path

SCHEMA = "vh-map02-host-alsa-transfer-trace/v1"
FIELDS = ("event","start_monotonic_ns","end_monotonic_ns","tid",
          "requested_frames","returned_frames","rate_hz","channels",
          "period_frames","buffer_frames","stream_id")
KINDS = {"HW_PARAMS","WRITEI","MMAP_COMMIT"}
MAX_EVENTS = 256


def parse(path):
    with path.open(encoding="ascii", newline="") as source:
        records = list(csv.reader(source))
    if not records:
        raise ValueError("No host ALSA evidence; interposition may not be active")
    if len(records) > MAX_EVENTS:
        raise ValueError("Unbounded ALSA trace; expected <=256 rows")
    entries = []
    for idx, values in enumerate(records):
        if len(values) != len(FIELDS) or values[0] not in KINDS:
            raise ValueError(f"Invalid ALSA event row {idx}")
        try:
            data = {k: int(v) for k, v in zip(FIELDS[1:], values[1:])}
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid ALSA integer row {idx}") from exc
        if (data["start_monotonic_ns"] <= 0 or
            data["end_monotonic_ns"] < data["start_monotonic_ns"] or
            data["end_monotonic_ns"]-data["start_monotonic_ns"] > 10_000_000_000 or
            data["tid"] <= 0 or
            data["requested_frames"] < 0 or data["requested_frames"] > 1_000_000 or
            data["returned_frames"] < -4096 or data["returned_frames"] > 1_000_000 or
            min(data["rate_hz"],data["channels"],data["period_frames"],
                data["buffer_frames"]) < 0 or
            not (0 <= data["stream_id"] <= 1000000)):
            raise ValueError(f"Impossible ALSA event counters/timing at row {idx}")
        entries.append({"event": values[0], **data,
                        "duration_ns":
                            data["end_monotonic_ns"]-data["start_monotonic_ns"]})
    hw = [r for r in entries if r["event"]=="HW_PARAMS" and
          r["returned_frames"]==0]
    xfers = [r for r in entries if r["event"] in ("WRITEI","MMAP_COMMIT")]
    target_hw = [r for r in hw if r["rate_hz"]==48000 and
                 r["channels"]==2]
    invalid_target = [r for r in target_hw if
                      r["period_frames"]<=0 or
                      r["buffer_frames"]<r["period_frames"]]
    if invalid_target:
        raise ValueError("Target 48k stereo ALSA hw_params invalid period/buffer")
    valid_hw = target_hw
    if not valid_hw:
        raise ValueError("No valid 48k stereo ALSA hw_params observed")
    # CPAL/NeXium can negotiate other ALSA playback instances in the
    # same process (actual capture observed 768000 Hz / 32 channels).
    # Do NOT silently equate these independent configurations with the
    # primary 48-kHz guest output stream.
    other_hw = [r for r in hw if r not in target_hw]
    if not xfers:
        raise ValueError("No ALSA write/commit calls intercepted")
    if any(r["returned_frames"]>r["requested_frames"] for r in xfers
           if r["returned_frames"]>=0):
        raise ValueError("ALSA transfer returned more frames than requested")
    successful = [r for r in xfers if r["returned_frames"]>0]
    # Reconstruct the latest successfully applied configuration for each
    # anonymous snd_pcm_t ordinal BEFORE each transfer. The raw pointer
    # itself is never stored and an unrecognized ordinal remains unknown.
    # If recording hit 256 events this covers only the captured prefix.
    hw_sorted=sorted(hw,key=lambda r:r["end_monotonic_ns"])
    latest={}
    stream_48=set()
    stream_other=set()
    by_stream={}
    for h in hw_sorted:
        ident=h["stream_id"]
        if ident==0: continue
        if h in valid_hw: stream_48.add(ident)
        else: stream_other.add(ident)
        by_stream.setdefault(ident,[]).append(h)
    classified={"48k_stereo":0,"other_or_unknown":0}
    unknown=0
    for transfer in xfers:
        ident=transfer["stream_id"]
        preceding=[h for h in by_stream.get(ident,[]) if
                   h["end_monotonic_ns"]<=transfer["start_monotonic_ns"]]
        if not ident or not preceding:
            unknown+=1
            continue
        latest_cfg=max(preceding,key=lambda x:x["end_monotonic_ns"])
        if latest_cfg in valid_hw:
            classified["48k_stereo"]+=1
        else:
            classified["other_or_unknown"]+=1
    if sum(classified.values())+unknown!=len(xfers):
        raise ValueError("ALSA ordinal transfer partition is inconsistent")
    period_values=sorted({r["period_frames"] for r in valid_hw})
    buffer_values=sorted({r["buffer_frames"] for r in valid_hw})
    return {
        "schema":SCHEMA,
        "result":"OBSERVED_ALSA_HW_PARAMS_AND_TRANSFER_CALLS",
        "record_count":len(entries),
        "valid_48k_stereo_hw_params_count":len(valid_hw),
        "other_successful_alsa_hw_params_count":len(other_hw),
        "other_alsa_hw_configurations":[
            {"rate_hz":hz,"channels":ch,
             "period_frames":period,"buffer_frames":buf}
            for hz,ch,period,buf in sorted({
                (r["rate_hz"],r["channels"],
                 r["period_frames"],r["buffer_frames"])
                for r in other_hw})],
        "anonymous_pcm_stream_ordinals_available":True,
        "capture_prefix_only_if_event_limit_reached":len(entries)==MAX_EVENTS,
        "48k_stereo_stream_ids":sorted(stream_48),
        "other_hw_stream_ids":sorted(stream_other),
        "mixed_configuration_stream_ids":sorted(stream_48 & stream_other),
        "48k_stereo_attributed_transfer_count":classified["48k_stereo"],
        "other_config_attributed_transfer_count":classified["other_or_unknown"],
        "unattributed_transfer_count":unknown,
        "transfer_calls_directly_attributed_to_48k_pcm":(
            classified["48k_stereo"]>0 and unknown==0 and
            not (stream_48 & stream_other)),
        "transfer_call_count":len(xfers),
        "positive_frame_transfer_count":len(successful),
        "transfer_kinds":sorted({r["event"] for r in xfers}),
        "period_frames_values":period_values,
        "buffer_frames_values":buffer_values,
        "transfer_duration_ns_min":min(r["duration_ns"] for r in xfers),
        "transfer_duration_ns_max":max(r["duration_ns"] for r in xfers),
        "transfer_duration_ns_samples":[r["duration_ns"] for r in xfers[:32]],
        "first_event_monotonic_ns":min(r["start_monotonic_ns"] for r in entries),
        "last_event_monotonic_ns":max(r["end_monotonic_ns"] for r in entries),
        "bounded_trace_max_events":MAX_EVENTS,
        "instrumentation_affects_host_timing":True,
        "rust_cpal_callback_period_proven":False,
        "guest_audout_service_deadlock_proven":False,
        "physical_switch_audio_proven":False,
        "raw_audio_data_collected":False,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        report=parse(args.trace)
        result=0
    except (ValueError,OSError,UnicodeError,csv.Error) as exc:
        report={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
                "instrumentation_affects_host_timing":True,
                "rust_cpal_callback_period_proven":False,
                "guest_audout_service_deadlock_proven":False,
                "physical_switch_audio_proven":False,
                "raw_audio_data_collected":False}
        result=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",
                           encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))
    return result


if __name__=="__main__":
    raise SystemExit(main())
