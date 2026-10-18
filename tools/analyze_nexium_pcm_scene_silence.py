#!/usr/bin/env python3
"""Stage300: place *recorded* exact-zero PCM runs into host scene-marker zones.

Scene markers are buffered host byte-length snapshots, NOT exact guest input
time, audio callback timestamps, or independent reference waveform.
This reports descriptive silence location only, never underruns or causality.
"""
from __future__ import annotations

import argparse
from array import array
from bisect import bisect_right
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    RATE, FRAME_BYTES, SCENES, VirtualPcmEvidenceError,
    analyze_pair, read_report, require_file
)

SCHEMA="vh-nexium-pcm-actual-zero-runs-by-host-scene-marker-zones/v1"
POST_MARKER_GUARD_SECONDS=1.5
PRE_NEXT_MARKER_GUARD_SECONDS=0.5
LONG_RUN_MIN_SECONDS=0.1
MAX_REPORTED_LONG_RUNS=20


def zone_partition(markers:list[dict],total_frames:int,*,rate:int=RATE)->list[dict]:
    if (not isinstance(markers,list) or len(markers)!=5
            or type(total_frames) is not int or total_frames<=0
            or type(rate) is not int or rate<10):
        raise VirtualPcmEvidenceError("invalid current-run marker sequence")
    offsets=[]
    for index,(marker,label) in enumerate(zip(markers,SCENES)):
        frame=marker.get("approximate_frame_offset")
        if (marker.get("scene")!=label or type(frame) is not int
                or frame<0 or frame>=total_frames
                or marker.get("pcm_byte_offset")!=frame*FRAME_BYTES):
            raise VirtualPcmEvidenceError("invalid original scene byte-bound marker")
        if offsets and frame<=offsets[-1]:
            raise VirtualPcmEvidenceError("nonmonotone original scene markers")
        offsets.append(frame)
    post=int(POST_MARKER_GUARD_SECONDS*rate)
    pre=int(PRE_NEXT_MARKER_GUARD_SECONDS*rate)
    zones=[]
    def add(label,category,start,end):
        if end>start:
            zones.append({
                "zone":label,
                "category":category,
                "start_frame":start,
                "end_frame_exclusive":end,
                "frames":end-start,
            })
    add("before_first_marker","before_first_marker",0,offsets[0])
    for index,label in enumerate(SCENES):
        start=offsets[index]
        end=offsets[index+1] if index+1<len(offsets) else total_frames
        stable_start=start+post
        stable_end=end-pre
        # These are exactly the guard rules used by existing scene
        # analyzer. It requires >=2 stable seconds, never compressed.
        if stable_end-stable_start<2*rate:
            raise VirtualPcmEvidenceError("no validated settled interval for "+label)
        add(label+":post_marker_guard","post_marker_guard",start,stable_start)
        add(label+":settled_scene","settled_scene",stable_start,stable_end)
        add(label+":pre_next_or_end_guard",
            "pre_next_or_end_guard",stable_end,end)
    if (not zones or zones[0]["start_frame"]!=0
            or zones[-1]["end_frame_exclusive"]!=total_frames
            or any(a["end_frame_exclusive"]!=b["start_frame"]
                   for a,b in zip(zones,zones[1:]))
            or sum(x["frames"] for x in zones)!=total_frames):
        raise VirtualPcmEvidenceError("host marker zones do not partition PCM")
    return zones


def exact_zero_runs(raw:bytes)->tuple[list[tuple[int,int]],int]:
    if len(raw)<FRAME_BYTES or len(raw)%FRAME_BYTES:
        raise VirtualPcmEvidenceError("incomplete s16le stereo frames")
    values=array("h")
    values.frombytes(raw)
    if sys.byteorder!="little":
        values.byteswap()
    runs=[]
    start=None
    for frame in range(len(values)//2):
        a,b=values[2*frame],values[2*frame+1]
        if a==0 and b==0:
            if start is None:
                start=frame
        elif start is not None:
            runs.append((start,frame))
            start=None
    if start is not None:
        runs.append((start,len(values)//2))
    return runs,len(values)//2


def classify_silence(raw:bytes,stage299:dict,scene_report:dict,
                     *,rate:int=RATE)->dict:
    if (type(rate) is not int or rate<10
            or stage299.get("result")!="TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED"
            or stage299.get("physical_Nintendo_Switch_hardware_tested") is not False
            or stage299.get("dropped_or_duplicated_audio_frames_proven") is not False):
        raise VirtualPcmEvidenceError("Stage299 evidence not authenticated")
    capture=stage299.get("scene_capture")
    if (not isinstance(capture,dict) or
            capture.get("pinned_prior_report_reconciled") is not True
            or scene_report.get("pcm_sha256")!=capture.get("pcm_sha256")
            or scene_report.get("schema")!="vh-nexium-scene-audio/v1"
            or scene_report.get("hardware_status")!="HARDWARE NOT TESTED"
            or scene_report.get("scene_change_proven_causal") is not False):
        raise VirtualPcmEvidenceError("source scene report not bound to Stage299 capture")
    runs,frames=exact_zero_runs(raw)
    if frames!=capture.get("frames") or len(raw)!=capture.get("pcm_bytes"):
        raise VirtualPcmEvidenceError("source PCM frames differ from Stage299")
    import hashlib
    if hashlib.sha256(raw).hexdigest()!=capture.get("pcm_sha256"):
        raise VirtualPcmEvidenceError("source scene PCM SHA-256 mismatch")
    markers=capture.get("scene_event_markers")
    if (not isinstance(markers,list) or
            not isinstance(scene_report.get("intervals"),list) or
            len(scene_report["intervals"])!=len(SCENES)):
        raise VirtualPcmEvidenceError("missing audited five-scene intervals")
    for marker,interval,label in zip(markers,scene_report["intervals"],SCENES):
        if (interval.get("scene")!=label or
                interval.get("recorded_host_epoch_ms")!=marker.get("host_epoch_ms")
                or interval.get("event_offset_seconds")!=
                   round(marker["approximate_frame_offset"]/rate,3)):
            raise VirtualPcmEvidenceError("scene audio report diverges from PCM markers")
    zones=zone_partition(markers,frames,rate=rate)
    starts=[z["start_frame"] for z in zones]
    by_zone=[dict(zone) for zone in zones]
    for z in by_zone:
        z.update({"exact_zero_frames":0,
                  "long_run_zero_frames":0,
                  "long_run_intersections":0})
    long_min=max(1,int(LONG_RUN_MIN_SECONDS*rate))
    long_runs=[]
    longest=max((end-start for start,end in runs),default=0)
    zero_total=sum(end-start for start,end in runs)
    for start,end in runs:
        is_long=end-start>=long_min
        idx=max(0,bisect_right(starts,start)-1)
        overlaps=[]
        while idx<len(zones) and zones[idx]["start_frame"]<end:
            z=by_zone[idx]
            overlap=min(end,z["end_frame_exclusive"])-max(start,z["start_frame"])
            if overlap>0:
                z["exact_zero_frames"]+=overlap
                if is_long:
                    z["long_run_zero_frames"]+=overlap
                    z["long_run_intersections"]+=1
                    overlaps.append({"zone":z["zone"],"frames":overlap})
            idx+=1
        if is_long:
            long_runs.append({
                "start_frame":start,
                "end_frame_exclusive":end,
                "frames":end-start,
                "seconds":round((end-start)/rate,6),
                "zone_overlaps":overlaps,
            })
    if (zero_total!=capture.get("exact_zero_stereo_frames")
            or len(runs)!=capture.get("exact_zero_stereo_runs")
            or longest!=capture.get("longest_exact_zero_stereo_run_frames")
            or sum(z["exact_zero_frames"] for z in by_zone)!=zero_total
            or sum(z["long_run_zero_frames"] for z in by_zone)!=
               sum(z["frames"] for z in long_runs)
            or any(not 0<=z["long_run_zero_frames"]<=
                   z["exact_zero_frames"]<=z["frames"] for z in by_zone)):
        raise VirtualPcmEvidenceError("exact source zero-run/marker accounting mismatch")
    for z in by_zone:
        z["zero_fraction_of_zone"]=round(z["exact_zero_frames"]/z["frames"],6)
    longest_runs=sorted(long_runs,key=lambda x:(-x["frames"],x["start_frame"]))
    return {
        "schema":SCHEMA,
        "result":"SOURCE_BOUND_SCENE_SILENCE_BY_APPROXIMATE_HOST_MARKERS_RECONCILED",
        "scene_pcm_sha256":capture["pcm_sha256"],
        "scene_pcm_frames":frames,
        "marker_count":len(markers),
        "approximate_scene_markers":markers,
        "zone_count":len(zones),
        "zones":by_zone,
        "exact_zero_runs_total":len(runs),
        "exact_zero_frames_total":zero_total,
        "exact_zero_longest_run_frames":longest,
        "long_run_minimum_frames":long_min,
        "long_run_count":len(long_runs),
        "long_run_frames_total":sum(r["frames"] for r in long_runs),
        "longest_zero_runs_top20":longest_runs[:MAX_REPORTED_LONG_RUNS],
        "all_PCM_frames_partitioned_by_host_marker_zones":True,
        "all_original_zero_run_frames_partitioned_exactly":True,
        "scene_marker_times_are_host_buffered_estimates":True,
        "zero_runs_are_not_verified_audio_dropouts":True,
        "scene_input_or_music_transition_causality_proven":False,
        "actual_guest_scheduler_or_DAC_state_measured":False,
        "original_soundtrack_or_physical_speaker_output_verified":False,
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    for label in ("monitor","monitor-report","scenes","scene-report",
                  "events","stage299","output"):
        p.add_argument("--"+label,required=True,type=Path)
    a=p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse to replace audited scene silence report")
        current=analyze_pair(a.monitor,a.monitor_report,a.scenes,
                             a.scene_report,a.events)
        previous=read_report(a.stage299)
        if previous!=current:
            raise VirtualPcmEvidenceError(
                "prior Stage299 report is not reproducible from current exact PCM")
        raw=require_file(a.scenes,"original scene PCM")
        scene_report=read_report(a.scene_report)
        result=classify_silence(raw,previous,scene_report)
        a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
        print(json.dumps({
            "result":result["result"],
            "long_runs":result["long_run_count"],
            "longest_frames":result["exact_zero_longest_run_frames"],
            "longest_zone_overlaps":
                result["longest_zero_runs_top20"][0]["zone_overlaps"]
                if result["longest_zero_runs_top20"] else [],
            "physical_Switch_tested":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,UnicodeError,KeyError,TypeError) as exc:
        print(json.dumps({
            "result":"STAGE300_SCENE_SILENCE_CORRELATION_NOT_VERIFIED",
            "error":str(exc)
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
