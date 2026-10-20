#!/usr/bin/env python3
"""Stage383: recheck 18 original NeXium guest audio exits, not hardware playback."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import zlib
import audit_stage373_six_optical_originals as original
import audit_stage382_sixteen_optical_originals as prior

NINTH_RUN=39479476340
NINTH_PIN={
 "head":"83379b23d8fbd86147500be1bb16320f5b2ad7c2",
 "merge":"c52dd353fe14f065cfe7c28f441509ec1f98587a",
 "artifact":12290652201,
 "digest":"sha256:2bbb189adac7eae6e0508159075b12ce2173bb5789e804eea83ed3a130650ad8",
 "optical":["a88c146d23efc864a620d684c519ee29db4d49f4c4df745712506b3b00ee5eb1",
            "1dc6fd17a1aab179580f5f3a9d9c9a21729e87dd6e39d030f405d17b5fdefc46"],
 "reason":["1aaacb77e69ddaeff8b37d7a08d70c404a69b2bc9e832108dfc480838c42b201",
           "adb20a948f38f4671270c8a26f7f31ab13f709ac0de5c7caad0b980daf9c2f61"]}
ALL_RUNS=(*prior.ALL_RUNS,NINTH_RUN)
RESULT="STAGE383_EIGHTEEN_ORIGINAL_NEIXUM_GUEST_EXITS_SOURCE_BOUND"

def combine(old,new):
    need=original.need
    need(type(old) is dict and old.get("result")==prior.RESULT and
         old.get("source_run_ids")==list(prior.ALL_RUNS) and
         old.get("nro_sha256")==original.NRO_SHA and
         old.get("original_guest_sessions")==16 and
         old.get("all_software_wait_results_zero") is True and
         old.get("all_returned_descriptors_exactly_one") is True and
         old.get("all_sixteen_optical_pngs_and_packets_distinct") is True and
         old.get("physical_switch_speaker_audio_tested") is False and
         old.get("new_guest_sessions_created_by_audit") is False and
         old.get("cause_of_historical_0xEA01_proven") is False,
         "previous sixteen original sources not verified")
    previous=old.get("sessions")
    need(type(previous) is list and len(previous)==16,"missing original sessions")
    need(type(new) is list and len(new)==2 and
         [(s.get("run_id"),s.get("trial"),s.get("dwell_seconds")) for s in new] ==
         [(NINTH_RUN,"a",6),(NINTH_RUN,"b",12)],
         "ninth source run/trial/dwell invalid")
    rows=previous+new
    need(len(rows)==18 and
         [(s.get("run_id"),s.get("trial"),s.get("dwell_seconds")) for s in rows] ==
         [(r,t,d) for r in ALL_RUNS for t,d in (("a",6),("b",12))],
         "original trial order or run substitution")
    for s in rows:
        need(s.get("guest_result")==0 and s.get("released_descriptors")==1 and
             type(s.get("pcm_pages_acquired_and_released")) is int and
             s["pcm_pages_acquired_and_released"]>0 and
             type(s.get("tail_interval_ms")) in (int,float) and
             0<s["tail_interval_ms"]<12 and
             s.get("guest_event_rows")==23 and s.get("complete_scene_serials")==4 and
             s.get("dropped_guest_events")==0,
             "service return, PCM ownership or guest optical event mismatch")
        for field in ("original_optical_sha256","pixel_packet_sha256","original_reason_sha256"):
            sha=s.get(field)
            need(type(sha) is str and len(sha)==64 and
                 all(ch in "0123456789abcdef" for ch in sha),
                 "malformed source digest")
        crc=s.get("pixel_packet_crc32")
        need(type(crc) is str and len(crc)==8 and
             all(ch in "0123456789abcdef" for ch in crc),
             "malformed optical CRC")
    for field in ("original_optical_sha256","pixel_packet_sha256"):
        need(len({s[field] for s in rows})==18,
             "duplicate original guest PNG or decoded packet")
    # Source-identical software counter CSVs can recur across independent
    # captures. Every original CSV is still verified against its own source pin.
    groups={}
    for s in rows:
        groups.setdefault(s["original_reason_sha256"],[]).append(
            {"run_id":s["run_id"],"trial":s["trial"]})
    repeated=[{"reason_sha256":key,"source_sessions":value}
              for key,value in sorted(groups.items()) if len(value)>1]
    return {"schema":"vh-stage383-eighteen-original-guest-exits/v1",
            "result":RESULT,"source_run_ids":list(ALL_RUNS),
            "nro_sha256":original.NRO_SHA,
            "original_guest_sessions":18,"successful_software_wait_results":18,
            "confirmed_exact_descriptor_returns":18,
            "distinct_original_optical_pngs":18,
            "distinct_crc_checked_optical_packets":18,
            "distinct_reason_csv_sha256_count":len(groups),
            "repeated_reason_counter_csv":repeated,
            "complete_music_scene_transitions":72,"dropped_guest_events":0,
            "min_tail_append_plus_wait_ms":min(s["tail_interval_ms"] for s in rows),
            "max_tail_append_plus_wait_ms":max(s["tail_interval_ms"] for s in rows),
            "sessions":rows,"new_guest_sessions_created_by_audit":False,
            "physical_switch_speaker_audio_tested":False,
            "hardware_status":"HARDWARE NOT TESTED",
            "cause_of_historical_0xEA01_proven":False,
            "direct_exit_queue_depth_measured":False,
            "controlled_causal_dwell_experiment":False}

def audit(originals:Path,metadata:Path):
    original.need(tuple(original.RUNS)==tuple(prior.eight.SIX_RUNS)
                  and NINTH_RUN not in original.RUNS
                  and NINTH_RUN not in prior.ALL_RUNS,
                  "historical pinned sources altered")
    old=prior.audit(originals,metadata)
    original.RUNS[NINTH_RUN]=NINTH_PIN
    try:
        latest=original.verify(NINTH_RUN,originals/str(NINTH_RUN),metadata)
    finally:
        del original.RUNS[NINTH_RUN]
    return combine(old,latest)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("originals","metadata","output"):
        p.add_argument("--"+key,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        original.need(not args.output.exists() and not args.output.is_symlink(),
                      "refuse overwrite")
        report=audit(args.originals,args.metadata)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(report,f,sort_keys=True,indent=2);f.write("\n")
        print(json.dumps({"result":RESULT,"original_guest_sessions":18,
                          "physical_audio_tested":False},sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error):
        print(json.dumps({"result":"STAGE383_ORIGINALS_NOT_VERIFIED",
                          "hardware_status":"HARDWARE NOT TESTED"},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
