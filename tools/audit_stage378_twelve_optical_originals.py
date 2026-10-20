#!/usr/bin/env python3
"""Stage378: independently replay twelve archived original NeXium audout exits.

This adds two immutable run/source pins to the separately validated Stage374
eight-original-guest evidence. No new guest session, speaker or DAC proof.
"""
from __future__ import annotations
import argparse
import json
import zlib
from pathlib import Path
import audit_stage373_six_optical_originals as original
import audit_stage374_eight_optical_originals as eight

NEW_RUNS=(39459228340,39462294094)
PINS={
39459228340:{
 "head":"696bb7649bf1b9bb066648b9151fbcaf01863b39",
 "merge":"ba58bfb3190bda47e0c904a3684eb27a0c69fd1c",
 "artifact":12281898466,
 "digest":"sha256:59c1f4735c4e65cc5d55f90fd88e0d038e003348059e2901b4818eaa9b1ed55f",
 "optical":["e00225743437d7e6e3741cfecbfd7abb97bbe3b7aa8d8f2cf4c6ce2e12e25a5e","901270d7011006971a40e089237e51902adbba6bd8f2145c8b46b75d2d049d29"],
 "reason":["ade49f640a6a6d2f2aa85d94b8a21726ce12887ab66a83ca823d87d41b8406e9","669d9e0922cefaa9b1b511ecebdb9ea6af2258dce4e30c787979bde886b8607f"]},
39462294094:{
 "head":"450705d117cd5e592df91898a89c1879d9ef1f79",
 "merge":"a5deed8cea073a6c95e36eb94fda7b820ac0e0f1",
 "artifact":12283318074,
 "digest":"sha256:3129ca262fb24a22d1a27b8dc74b636a23cf24413d55b25cd1c9d33ffb96b194",
 "optical":["a0a4f9fb46204d7b956cf20adaad188bccdb75cbfb17416eb912d1bee77c8c89","7141a67afe6a5d796165b79b3972bab0e23d859bf7041f5b4b72d40f904cb641"],
 "reason":["1f4b400273b36d11e42ca232e3627e26172bfae108c2d1b45f739c608865c284","c20a26cae5383291812b167ff7c6e085684a3afe5d6a59c8ece3d2548c158429"]}}
RUNS=(*eight.SIX_RUNS,eight.FOURTH_RUN,*NEW_RUNS)
HASHES=("pixel_packet_sha256","original_optical_sha256","original_reason_sha256")
RESULT="STAGE378_TWELVE_SOURCE_PINNED_NEIXUM_OPTICAL_EXITS_REPLAYED"

def combine(eight_source,fifth,sixth):
    require=original.need
    require(type(eight_source) is dict and
        eight_source.get("result")==eight.RESULT and
        eight_source.get("source_workflow_run_ids")==list(RUNS[:4]) and
        eight_source.get("nro_sha256")==original.NRO_SHA and
        eight_source.get("original_guest_session_count")==8 and
        eight_source.get("all_eight_guest_optical_packets_unique") is True and
        eight_source.get("all_eight_wait_results_zero") is True and
        eight_source.get("all_eight_returned_descriptors_one") is True and
        eight_source.get("physical_switch_speaker_audio_tested") is False and
        eight_source.get("historical_0xEA01_root_cause_proven") is False and
        eight_source.get("new_guest_sessions_created_by_replay") is False,
        "Stage374 archived eight-session source receipt invalid")
    preceding=eight_source.get("sessions")
    require(type(preceding) is list and len(preceding)==8,
            "missing original eight sessions")
    for run,pair in zip(NEW_RUNS,(fifth,sixth)):
        require(type(pair) is list and len(pair)==2 and
            [(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in pair] ==
            [(run,"a",6),(run,"b",12)],
            "wrong new source run, trial or dwell")
    sessions=preceding+fifth+sixth
    require([(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in sessions] ==
            [(run,trial,dwell) for run in RUNS for trial,dwell in (("a",6),("b",12))],
            "missing or duplicate archival sessions")
    for x in sessions:
        require(x.get("guest_result")==0 and x.get("released_descriptors")==1
            and x.get("complete_scene_serials")==4 and x.get("guest_event_rows")==23
            and x.get("dropped_guest_events")==0 and
            type(x.get("pcm_pages_acquired_and_released")) is int and
            x["pcm_pages_acquired_and_released"]>0 and
            type(x.get("tail_interval_ms")) in (float,int) and
            0 < x["tail_interval_ms"] < 12,
            "guest wait result/descriptor/lease/timing/scenes inconsistent")
        for field in HASHES:
            digest=x.get(field)
            require(type(digest) is str and len(digest)==64 and
                all(ch in "0123456789abcdef" for ch in digest),
                "malformed source hash")
        require(type(x.get("pixel_packet_crc32")) is str and
                len(x["pixel_packet_crc32"])==8,
                "missing original optical CRC")
    for field in HASHES:
        require(len({s[field] for s in sessions})==12,
                "reused source hash: "+field)
    return {
      "schema":"vh-stage378-twelve-original-guest-optical-exits/v1",
      "result":RESULT,"source_run_ids":list(RUNS),
      "nro_sha256":original.NRO_SHA,"guest_sessions":12,
      "all_wait_results_zero":True,"all_release_counts_one":True,
      "all_optical_packet_hashes_distinct":True,
      "min_tail_interval_ms":min(s["tail_interval_ms"] for s in sessions),
      "max_tail_interval_ms":max(s["tail_interval_ms"] for s in sessions),
      "sessions":sessions,
      "new_guest_sessions_created_by_audit":False,
      "physical_switch_speaker_audio_tested":False,
      "direct_exit_queue_depth_measured":False,
      "cause_of_historical_0xEA01_proven":False,
      "controlled_causal_dwell_experiment":False
    }

def audit(originals,metadata):
    original.need(tuple(original.RUNS)==eight.SIX_RUNS
        and eight.FOURTH_RUN not in original.RUNS
        and all(run not in original.RUNS for run in NEW_RUNS)
        and RUNS[:4]==(*eight.SIX_RUNS,eight.FOURTH_RUN),
        "source pins unexpectedly modified")
    previous=eight.audit(originals,metadata)
    extra=[]
    for run in NEW_RUNS:
        original.need(run not in original.RUNS,"source pin collision")
        original.RUNS[run]=PINS[run]
        try:
            extra.append(original.verify(run,originals/str(run),metadata))
        finally:
            del original.RUNS[run]
    return combine(previous,*extra)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("originals","metadata","output"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args(argv)
    try:
        original.need(not a.output.exists() and not a.output.is_symlink(),
                      "refuse overwriting existing guest source receipt")
        out=audit(a.originals,a.metadata)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(out,f,sort_keys=True,indent=2); f.write("\n")
        print(json.dumps({"result":RESULT,"original_guest_sessions":12,
                          "software_waits_succeeded":12,
                          "physical_audio_tested":False},sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error) as exc:
        print(json.dumps({"result":"STAGE378_TWELVE_ORIGINAL_SOURCES_NOT_VERIFIED",
                          "error_kind":type(exc).__name__,
                          "hardware_status":"HARDWARE NOT TESTED"},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
