#!/usr/bin/env python3
"""Correlate *independent* guest optical, monitor and raster observations.

A missing post-join VHPRE001 receipt does not locate a stalled service call.
A nonzero virtual monitor does not prove physical Switch speaker audio.
This reports only facts already established by individual validators.
"""
import argparse
import json
from pathlib import Path

OPTICAL="vh-map02-presubmit-optical/v1"
MONITOR="vh-map02-latency-monitor-health/v1"
RASTER="vh-map02-optin-guest-raster-observation/v1"
SINK="vh-map02-presubmit-sink-audit/v1"
PULSE="vh-map02-pulse-sink-input-observation/v1"

def load_object(path):
    try:
        obj=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj,dict):
            raise ValueError("expected JSON object")
        return obj,None
    except (OSError,UnicodeError,ValueError) as exc:
        return None,str(exc)

def classify(optical,monitor,raster=None,sink=None,pulse=None):
    result={
        "schema":"vh-map02-guest-evidence-conjunction/v1",
        "guest_8page_receipt_valid":False,
        "virtual_48k_pcm_nonzero":None,
        "exact_8_individual_sink_page_matches":None,
        "guest_raster_before_final_changed_pixels":None,
        "guest_raster_final_late_changed_pixels":None,
        "unique_48k_stereo_pulse_client":None,
        "audout_playbuffer_stall_proven":False,
        "guest_join_deadlock_proven":False,
        "physical_switch_dac_samples_proven":False,
        "original_ps1_music_fidelity_proven":False,
    }
    if isinstance(raster,dict) and raster.get("schema")==RASTER:
        for field,entry in (("guest_raster_before_final_changed_pixels","before_to_final"),
                            ("guest_raster_final_late_changed_pixels","final_to_late")):
            v=raster.get(entry)
            if isinstance(v,dict) and type(v.get("changed_rgb_pixels")) is int and v["changed_rgb_pixels"]>=0:
                result[field]=v["changed_rgb_pixels"]
    if isinstance(pulse,dict) and pulse.get("schema")==PULSE:
        if type(pulse.get("unique_target_each_snapshot")) is bool:
            result["unique_48k_stereo_pulse_client"]=pulse["unique_target_each_snapshot"]
    valid_optical=(isinstance(optical,dict) and optical.get("schema")==OPTICAL
          and optical.get("result")=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED"
          and type(optical.get("observed_pages")) is int and optical["observed_pages"]==8
          and type(optical.get("mismatches")) is int and optical["mismatches"]==0
          and optical.get("actual_audout_call_observed") is True
          and isinstance(optical.get("pages"),list) and len(optical["pages"])==8
          and all(isinstance(p,dict)
                  and type(p.get("index")) is int and p["index"]==i
                  and type(p.get("descriptor_released_returns")) is int
                  and p["descriptor_released_returns"]==1
                  for i,p in enumerate(optical["pages"])))
    result["guest_8page_receipt_valid"]=bool(valid_optical)
    mon_ok=(isinstance(monitor,dict) and monitor.get("schema")==MONITOR
         and monitor.get("valid_pcm16le_stereo") is True
         and type(monitor.get("stereo_frames")) is int and monitor["stereo_frames"]>0
         and type(monitor.get("nonzero_pcm16_samples")) is int
         and 0<=monitor["nonzero_pcm16_samples"]<=2*monitor["stereo_frames"]
         and monitor.get("all_zero_monitor_pcm") is (monitor["nonzero_pcm16_samples"]==0))
    if mon_ok:
        result["virtual_48k_pcm_nonzero"]=monitor["nonzero_pcm16_samples"]>0
    if valid_optical and isinstance(sink,dict) and sink.get("schema")==SINK:
        matches=sink.get("per_page_matches")
        if isinstance(matches,list) and len(matches)==8 and all(type(x) is int and x>=0 for x in matches):
            result["exact_8_individual_sink_page_matches"]=all(x==1 for x in matches)
    if not mon_ok:
        verdict="INSUFFICIENT_VIRTUAL_MONITOR_EVIDENCE"
    elif valid_optical and not result["virtual_48k_pcm_nonzero"]:
        verdict="OPTICAL_RECEIPT_BUT_ZERO_MONITOR_CONTRADICTION"
    elif valid_optical and result["exact_8_individual_sink_page_matches"] is True:
        verdict="EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK"
    elif valid_optical:
        verdict="OPTICAL_VALID_SINK_PAGE_IDENTITY_UNVERIFIED"
    elif result["virtual_48k_pcm_nonzero"]:
        verdict="OPTICAL_MISSING_NONZERO_VIRTUAL_SINK"
    else:
        verdict="OPTICAL_MISSING_ZERO_VIRTUAL_SINK"
    result["classification"]=verdict
    result["interpretation"]=(
        "Observational conjunction only. No audio-thread liveness, service "
        "call stall, post-join timing, physical DAC, speakers, original game "
        "soundtrack fidelity or sample-synchronized music cue is proven.")
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--directory",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    filenames={
        "optical":"presubmit-guest.json",
        "monitor":"presubmit-monitor-health.json",
        "raster":"presubmit-guest-raster-sequence.json",
        "sink":"presubmit-sink-parity.json",
        "pulse":"pulse-sink-input-observed.json"}
    objects={}
    errors={}
    for name,fn in filenames.items():
        obj,err=load_object(args.directory/fn)
        objects[name]=obj
        if err:errors[name]=err
    out=classify(**objects)
    out["missing_or_invalid_input_reports"]=sorted(errors)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,sort_keys=True,indent=2))
    # Observation is not an acceptance gate: the original guest CRC
    # assertion still independently decides the NeXium job result.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
