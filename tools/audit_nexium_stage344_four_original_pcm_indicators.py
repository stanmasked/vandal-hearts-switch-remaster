#!/usr/bin/env python3
"""Stage344: compare source-authenticated PCM continuity INDICATORS in four NeXium runs.

Re-read original PCM from four independently successful NeXium archives using
the unchanged Stage299 scanner. Require exact parity with each original saved
Stage299 report; compare exact-zero, low-RMS and large-sample-step indicators
using frame-normalized rates. Neither PCM nor service-call duration proves
missing/duplicated device frames, physical sound or audout causal delays.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from analyze_nexium_pcm_stream_integrity import (
    SCHEMA as STAGE299_SCHEMA, analyze_pair, read_report,
)
from compare_nexium_stage337_four_original_captures import find_unique

SCHEMA="vh-stage344-four-original-NeXium-PCM-continuity-indicators/v1"
RESULT="FOUR_ORIGINAL_NE XIUM_PCM_CONTINUITY_INDICATORS_SOURCE_REPLAYED".replace(" ","")
STAGE299_RESULT="TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED"
STAGE342_RESULT="FOUR_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_CAPTURE_COHORTS_SOURCE_VERIFIED"
NAMES=("original_first","original_second","original_third","original_fourth")
RUN_IDS=(39166023593,39167324026,39175592570,39182548276)
PIN_FIELDS=("original_guest_history_csv_sha256","original_guest_last_call_csv_sha256",
            "original_host_legacy_csv_sha256","original_host_monotonic_csv_sha256")
HEX=re.compile(r"[0-9a-f]{64}\Z")
SOURCE_FLAGS=("all_three_previous_stage335_original_sources_replayed",
              "original_fourth_stage334_receipt_recomputed_exactly",
              "original_fourth_stage336_receipt_recomputed_exactly",
              "all_four_original_guest_host_CSV_source_hashes_distinct",
              "no_software_guest_clock_converted_into_host_PCM_clock")

def nonneg(value:object,name:str,upper:int|None=None)->int:
    if type(value) is not int or value<0 or (upper is not None and value>upper):
        raise ValueError("invalid original PCM indicator: "+name)
    return value

def compact_pcm(snapshot:dict,kind:str)->dict:
    if not isinstance(snapshot,dict) or snapshot.get("kind")!=kind:
        raise ValueError("invalid original PCM stream kind")
    sha=snapshot.get("pcm_sha256")
    if not isinstance(sha,str) or not HEX.fullmatch(sha):
        raise ValueError("original PCM SHA-256 invalid")
    frames=nonneg(snapshot.get("frames"),"frames")
    if frames==0 or snapshot.get("pcm_bytes")!=frames*4:
        raise ValueError("original PCM frame accounting wrong")
    blocks=(frames+479)//480
    if (snapshot.get("analysis_block_frames")!=480
        or snapshot.get("analysis_blocks")!=blocks
        or snapshot.get("final_partial_block_frames")!=frames%480
        or snapshot.get("pinned_prior_report_reconciled") is not True
        or snapshot.get("physical_console_DAC_or_audible_glitches_measured") is not False
        or snapshot.get("possible_sample_discontinuities_are_not_verified_dropouts") is not True
        or snapshot.get("missing_frames_cannot_be_proven_from_pcm_bytes_alone") is not True
        or snapshot.get("guest_audio_queue_state_not_measured_by_pcm") is not True):
        raise ValueError("original PCM provenance or evidence boundary not preserved")
    zeros=nonneg(snapshot.get("exact_zero_stereo_frames"),"zero frames",frames)
    long=nonneg(snapshot.get("longest_exact_zero_stereo_run_frames"),"longest zero",frames)
    count=nonneg(snapshot.get("zero_runs_at_least_10ms"),"long zero runs")
    low=nonneg(snapshot.get("low_rms_10ms_blocks"),"low rms blocks",blocks)
    silent=nonneg(snapshot.get("exact_zero_10ms_blocks"),"all zero blocks",blocks)
    steps=nonneg(snapshot.get("adjacent_frame_deltas_ge4096"),"large frame steps",frames-1)
    boundaries=nonneg(snapshot.get("ge4096_deltas_at_10ms_block_boundaries"),"boundary steps",steps)
    if (long>zeros or silent>low or silent*480>zeros):
        raise ValueError("original exact-zero/low-RMS conservation fails")
    markers=snapshot.get("scene_event_markers")
    if (kind=="monitor" and markers is not None) or (
        kind=="scenes" and (not isinstance(markers,list) or len(markers)!=5)):
        raise ValueError("unexpected original scene marker scope")
    return {
        "kind":kind,
        "original_pcm_sha256":sha,
        "frames":frames,
        "pcm_bytes":frames*4,
        "exact_zero_frames":zeros,
        "exact_zero_frames_per_million":zeros*1000000//frames,
        "longest_exact_zero_run_frames":long,
        "exact_zero_runs_at_least_10ms":count,
        "low_rms_blocks":low,
        "low_rms_blocks_per_million":low*1000000//blocks,
        "all_zero_10ms_blocks":silent,
        "large_adjacent_sample_steps_ge4096":steps,
        "large_steps_per_million_frame_transitions":steps*1000000//max(frames-1,1),
        "large_steps_at_10ms_block_boundaries":boundaries,
    }

def compare_verified_reports(parent:dict, reports:list[dict])->dict:
    if (not isinstance(parent,dict) or parent.get("result")!=STAGE342_RESULT
        or parent.get("schema")!="vh-stage337-four-genuine-neXium-guest-host-source-to-nro-cohorts/v1"
        or any(parent.get(key) is not True for key in SOURCE_FLAGS)
        or parent.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ValueError("independent Stage342 original source acceptance absent")
    cohorts=parent.get("cohorts")
    if (not isinstance(cohorts,list) or len(cohorts)!=4 or
        tuple(c.get("source") if isinstance(c,dict) else None for c in cohorts)!=NAMES or
        not isinstance(reports,list) or len(reports)!=4):
        raise ValueError("exact four confirmed original source cohorts required")
    for field in PIN_FIELDS:
        vals=[c.get(field) for c in cohorts]
        if any(not isinstance(v,str) or not HEX.fullmatch(v) for v in vals) or len(set(vals))!=4:
            raise ValueError("original guest/host source pins not distinct")
    if (parent.get("original_third_run_id")!=RUN_IDS[2]
        or parent.get("original_fourth_run_id")!=RUN_IDS[3]):
        raise ValueError("third/fourth original run identities changed")
    rows=[]
    for name,run_id,cohort,doc in zip(NAMES,RUN_IDS,cohorts,reports):
        if (not isinstance(doc,dict) or doc.get("schema")!=STAGE299_SCHEMA
            or doc.get("result")!=STAGE299_RESULT
            or doc.get("distinct_current_run_virtual_PCM_sources") is not True
            or doc.get("both_prior_PCM_audits_bound_by_exact_SHA256") is not True
            or doc.get("all_stereo_frames_and_10ms_blocks_accounted") is not True
            or doc.get("dropped_or_duplicated_audio_frames_proven") is not False
            or doc.get("physical_Nintendo_Switch_hardware_tested") is not False
            or doc.get("soundtrack_identity_or_audible_playback_verified") is not False):
            raise ValueError("original independently replayed Stage299 evidence invalid")
        monitor=compact_pcm(doc.get("monitor_capture"),"monitor")
        scenes=compact_pcm(doc.get("scene_capture"),"scenes")
        if monitor["original_pcm_sha256"]==scenes["original_pcm_sha256"]:
            raise ValueError("two original recordings unexpectedly identical")
        last=cohort.get("guest_last_software_duration_ns")
        median=cohort.get("guest_prior_lower_median_software_ns")
        if (type(last) is not int or type(median) is not int or last<0 or median<0
            or cohort.get("guest_prior_median_minus_last_software_ns")!=median-last):
            raise ValueError("original guest timing witness altered")
        rows.append({
            "source":name,"source_run_id":run_id,
            "source_guest_history_sha256":cohort[PIN_FIELDS[0]],
            "guest_last_PlayBuffer_software_ns":last,
            "guest_prior_lower_median_software_ns":median,
            "monitor":monitor,"scenes":scenes,
        })
    for kind in ("monitor","scenes"):
        if len({r[kind]["original_pcm_sha256"] for r in rows})!=4:
            raise ValueError("original virtual PCM source reused across captures")
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "source_runs":list(RUN_IDS),
        "original_capture_indicator_rows":rows,
        "all_four_original_Stage299_PCM_reports_independently_recomputed":True,
        "original_Stage342_guest_host_source_chain_confirmed":True,
        "original_PCM_streams_distinct_within_and_across_runs":True,
        "PCM_exact_zero_and_sample_steps_only_descriptive_indicators":True,
        "guest_service_time_not_mapped_to_host_PCM_frames":True,
        "missing_or_duplicated_samples_not_verified_without_reference":True,
        "not_a_population_confidence_interval_or_causal_test":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_soundtrack_or_audible_dropout_verified":False,
    }

def replay(archives:list[Path],stage342:dict)->dict:
    if len(archives)!=4 or len({p.resolve() for p in archives})!=4:
        raise ValueError("four different original source archives required")
    reports=[]
    for root in archives:
        original=read_report(find_unique(root,"pcm-stream-integrity-stage299.json"))
        recomputed=analyze_pair(
            find_unique(root,"nexium-monitor-s16le-48k.pcm",limit=150_000_000),
            find_unique(root,"pcm-quality-report.json"),
            find_unique(root,"nexium-scenes-s16le-48k.pcm",limit=150_000_000),
            find_unique(root,"scene-audio-report.json"),
            find_unique(root,"scene-events.csv"))
        if original!=recomputed:
            raise ValueError("archived original Stage299 PCM evidence not reproduced exactly")
        reports.append(recomputed)
    return compare_verified_reports(stage342,reports)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("first","second","third","fourth"):
        p.add_argument("--"+name+"-archive",required=True,type=Path)
    p.add_argument("--stage342-report",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if a.output.is_symlink() or a.output.exists():
            raise ValueError("refuse overwrite original PCM source comparison")
        parent=read_report(a.stage342_report)
        doc=replay([getattr(a,x+"_archive") for x in
                    ("first","second","third","fourth")],parent)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as out:
            json.dump(doc,out,sort_keys=True,indent=2)
            out.write("\n")
        print(json.dumps({"result":doc["result"],
                         "rows":[{"source":r["source"],
                                  "monitor_zero_per_million":r["monitor"]["exact_zero_frames_per_million"],
                                  "scene_zero_per_million":r["scenes"]["exact_zero_frames_per_million"],
                                  "monitor_large_steps":r["monitor"]["large_adjacent_sample_steps_ge4096"],
                                  "scene_large_steps":r["scenes"]["large_adjacent_sample_steps_ge4096"]}
                                 for r in doc["original_capture_indicator_rows"]],
                         "physical_Nintendo_Switch_audio_tested":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({"result":"STAGE344_FOUR_ORIGINAL_PCM_INDICATORS_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "physical_Nintendo_Switch_audio_tested":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
