#!/usr/bin/env python3
"""Require all eight guest PCM pages to occur uniquely, in order, in sink.

Unlike guest VHPRE001 CRC (which attests the pre-AudioOut descriptor)
this gate evaluates full page bytes in the separately recorded host
virtual-sink 48k stereo PCM16LE using CRC32 and FNV1a64 signatures.
It intentionally permits observed *digital-zero* gaps. It never claims
continuous DAC output, real speakers or original PS1 music fidelity.
"""
import argparse
import json
from pathlib import Path

def assess(report,health):
    if not isinstance(report,dict) or not isinstance(health,dict):
        raise ValueError("Missing structured host evidence")
    if report.get("schema")!="vh-map02-presubmit-sink-audit/v1":
        raise ValueError("Unexpected virtual sink report schema")
    if health.get("schema")!="vh-map02-latency-monitor-health/v1":
        raise ValueError("Unexpected monitor health schema")
    matches=report.get("per_page_matches")
    if matches != [1]*8 or any(type(k) is not int for k in matches):
        raise ValueError("Not all eight pages uniquely present in virtual PCM")
    offsets=report.get("unique_page_frame_offsets")
    if not isinstance(offsets,list) or len(offsets)!=8 or any(type(k) is not int or k<0 for k in offsets):
        raise ValueError("Missing or ambiguous PCM page offset")
    if any(a>=b for a,b in zip(offsets,offsets[1:])):
        raise ValueError("PCM pages not in increasing order")
    if report.get("all_eight_pages_found_once") is not True or report.get("unique_page_order_preserved") is not True:
        raise ValueError("Original PCM attribution flag invalid")
    gaps=report.get("inter_page_gap_frames")
    if not isinstance(gaps,list) or len(gaps)!=7 or any(type(k) is not int or k<0 for k in gaps):
        raise ValueError("Overlapping or ambiguous PCM pages")
    gap_bytes=report.get("inter_page_gap_nonzero_pcm_bytes")
    if gap_bytes != [0]*7 or any(type(k) is not int for k in gap_bytes):
        raise ValueError("Unexpected nonzero gap PCM in known zero-padding experiment")
    if report.get("all_nonnegative_inter_page_gaps_digital_silence") is not True:
        raise ValueError("Digital-zero padding not independently established")
    if health.get("all_zero_monitor_pcm") is not False or (
        type(health.get("nonzero_pcm16_samples")) is not int or
        health["nonzero_pcm16_samples"]<=0
    ):
        raise ValueError("Virtual PCM monitor appears silent")
    if health.get("valid_pcm16le_stereo") is not True:
        raise ValueError("Monitor is not verified 48k stereo PCM16LE")
    if report.get("capture_frames") != health.get("stereo_frames"):
        raise ValueError("Independent monitor frame counts disagree")
    # Page matching does not establish all-frame contiguous playback.
    return {
        "schema":"vh-map02-guest-sink-eight-page-guard/v1",
        "result":"EXACT_EIGHT_INDIVIDUAL_SINK_PAGES_WITH_ZERO_GAPS",
        "unique_verified_page_count":8,
        "zero_gap_frames":sum(gaps),
        "contiguous_eight_page_stream_proven":all(g==0 for g in gaps),
        "actual_switch_speaker_dac_proven":False,
        "original_ps1_soundtrack_fidelity_proven":False
    }

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sink",type=Path,required=True)
    ap.add_argument("--health",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        result=assess(json.loads(a.sink.read_text()),
                      json.loads(a.health.read_text()))
        ok=True
    except (ValueError,TypeError,OSError) as exc:
        ok=False
        result={"schema":"vh-map02-guest-sink-eight-page-guard/v1",
                "result":"GUEST_SINK_EIGHT_PAGE_UNVERIFIED",
                "reason":str(exc),
                "contiguous_eight_page_stream_proven":False,
                "actual_switch_speaker_dac_proven":False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main())
