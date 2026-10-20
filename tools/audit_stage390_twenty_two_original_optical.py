#!/usr/bin/env python3
"""Independently verify 22 original NeXium guest exits; no hardware-audio claim."""
from __future__ import annotations
import argparse, json, zlib
from pathlib import Path
import audit_stage373_six_optical_originals as original
import audit_stage386_twenty_optical_nexium_sources as prior

NEW_RUN = 39494326413
PIN = {
  "head": "9c2d566a1d8e0762b4fd9bf89aeffd5dc0a597c1",
  "merge": "542e5461ef026f17117d9cc6f43be444e869a6d0",
  "artifact": 12301225369,
  "digest": "sha256:4ab098139a718e250e1d43520c8a7041ef86ac1ea68b4bbcaeb635836b528710",
  "optical": [
    "89ed945459ac31fa556eee7173fc6297c293fdd02ae4c24e4c341628b46e41b7",
    "108d0e4df2e817bb2a88bb0995e6d7bdbc655be01c07d8dd7f08c1e3a5e968c9"],
  "reason": [
    "5fdee0ad2687a010a604e43d55069e8df678420d4345f2262b74a9df5cc08cde",
    "2d8e9c950b201e0233f5ea269d64bf67ea2a7ac5c3af626addc85b3cbe5af43d"]
}
RUNS = (*prior.ALL_RUNS, NEW_RUN)
RESULT = "STAGE390_TWENTY_TWO_SOURCE_PINNED_NEIXUM_GUEST_EXITS"

def emulator_identity(path: Path) -> dict:
    need=original.need
    a=original.metadata(path/"runtime-evidence/nexium-runtime-binary-provenance.json")
    b=original.metadata(path/"runtime-evidence/nexium-tar-preextract.json")
    need(a.get("source_run_id")==NEW_RUN and a.get("source_head_sha")==PIN["merge"]
         and a.get("schema")=="vh-stage384-nexium-runtime-bytes/v1"
         and a.get("result")=="STAGE384_ONE_GUEST_RUN_NEXIUM_BYTES_PINNED"
         and a.get("release_id")==b.get("release_id")==340509243
         and a.get("release_asset_id")==b.get("release_asset_id")==658656899
         and a.get("asset_name")==b.get("asset_name")=="nexium-linux-x86_64.tar.gz"
         and a.get("asset_sha256")==b.get("archive_sha256")==prior.EXPECTED_EMULATOR_TAR
         and a.get("asset_size_bytes")==b.get("archive_bytes")==114182978
         and a.get("advertised_asset_digest_checked") is True
         and a.get("binary_sha256")==prior.EXPECTED_EMULATOR_BIN
         and a.get("binary_name")=="nexium" and a.get("binary_size_bytes")==304888160
         and a.get("hardware_status")==b.get("hardware_status")=="HARDWARE NOT TESTED"
         and a.get("physical_audio_output_tested") is False
         and a.get("same_binary_in_historical_runs_proven") is False
         and b.get("result")=="STAGE385_RELEASE_ARCHIVE_BYTES_AND_TAR_PATHS_VERIFIED"
         and b.get("ready_for_controlled_extraction") is True
         and b.get("github_advertised_sha256_checked") is True
         and b.get("binary_authenticity_signed") is False
         and b.get("member_count")==15 and b.get("symbolic_links")==0,
         "eleventh original executable/asset receipts inconsistent")
    return {"archive_sha256":a["asset_sha256"],"binary_sha256":a["binary_sha256"],
            "same_neixum_binary_on_runs_10_and_11":True,
            "same_neixum_binary_on_runs_1_to_9_proven":False}

def combine(old:dict, fresh:list[dict], emulator:dict) -> dict:
    need=original.need
    need(type(old) is dict and old.get("result")==prior.RESULT
         and old.get("source_run_ids")==list(prior.ALL_RUNS)
         and old.get("original_guest_sessions")==20
         and old.get("guest_wait_result_zero")==20
         and old.get("exact_returned_descriptors")==20
         and old.get("unique_crc_verified_optical_packets")==20
         and old.get("complete_music_scene_transitions")==80
         and old.get("dropped_guest_events")==0
         and old.get("nro_sha256")==original.NRO_SHA
         and old.get("physical_switch_speaker_audio_tested") is False
         and old.get("cause_of_historical_0xEA01_proven") is False,
         "previous twenty original software exits not verified")
    tenth=old.get("tenth_run_neixum_emulator")
    need(type(tenth) is dict and
         tenth.get("archive_sha256")==prior.EXPECTED_EMULATOR_TAR
         and tenth.get("binary_sha256")==prior.EXPECTED_EMULATOR_BIN
         and tenth.get("same_binary_in_earlier_nine_runs_proven") is False
         and tenth.get("physical_switch_audio_tested") is False,
         "tenth original emulator receipt invalid")
    need(type(emulator) is dict and
         emulator.get("archive_sha256")==tenth["archive_sha256"]
         and emulator.get("binary_sha256")==tenth["binary_sha256"]
         and emulator.get("same_neixum_binary_on_runs_10_and_11") is True
         and emulator.get("same_neixum_binary_on_runs_1_to_9_proven") is False,
         "eleventh NeXium must match only source-authenticated tenth")
    need(type(fresh) is list and len(fresh)==2 and
         [(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in fresh]
         ==[(NEW_RUN,"a",6),(NEW_RUN,"b",12)],"eleventh pair swapped or missing")
    rows=old.get("sessions")
    need(type(rows) is list and len(rows)==20,"prior source rows missing")
    rows=rows+fresh
    need(len(rows)==22 and
         [(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in rows]
         ==[(run,t,d) for run in RUNS for t,d in (("a",6),("b",12))],
         "guest original run order invalid")
    for x in rows:
        need(x.get("guest_result")==0 and x.get("released_descriptors")==1
             and type(x.get("pcm_pages_acquired_and_released")) is int
             and x["pcm_pages_acquired_and_released"]>0
             and type(x.get("tail_interval_ms")) in (int,float)
             and 0<x["tail_interval_ms"]<12
             and x.get("complete_scene_serials")==4
             and x.get("guest_event_rows")==23 and x.get("dropped_guest_events")==0,
             "nonzero kernel wait or unbalanced PCM/scene events")
        for key in ("original_optical_sha256","pixel_packet_sha256","original_reason_sha256"):
            value=x.get(key)
            need(type(value) is str and len(value)==64 and
                 all(c in "0123456789abcdef" for c in value),"unbound source digest")
    for key in ("original_optical_sha256","pixel_packet_sha256"):
        need(len({x[key] for x in rows})==22,"reused optical packet")
    reasons={}
    for x in rows:
        reasons.setdefault(x["original_reason_sha256"],[]).append(
            {"run_id":x["run_id"],"trial":x["trial"]})
    need(len(reasons)==20 and
         reasons.get(PIN["reason"][1])==
         [{"run_id":prior.TENTH_RUN,"trial":"b"},{"run_id":NEW_RUN,"trial":"b"}],
         "original software counter reuse mismatch")
    return {"schema":"vh-stage390-twenty-two-original-audio-exits/v1",
            "result":RESULT,"original_guest_sessions":22,
            "source_run_ids":list(RUNS),"sessions":rows,
            "guest_wait_result_zero":22,"exact_returned_descriptors":22,
            "unique_crc_verified_optical_packets":22,
            "distinct_original_optical_pngs":22,
            "complete_music_scene_transitions":88,"dropped_guest_events":0,
            "distinct_reason_counter_csv_sha256_count":20,
            "repeated_counter_csv":[{"sha256":k,"sessions":v}
                                    for k,v in sorted(reasons.items()) if len(v)>1],
            "last_two_emulator_byte_identity":emulator,
            "nro_sha256":original.NRO_SHA,
            "min_tail_append_plus_wait_ms":min(x["tail_interval_ms"] for x in rows),
            "max_tail_append_plus_wait_ms":max(x["tail_interval_ms"] for x in rows),
            "physical_switch_speaker_audio_tested":False,
            "cause_of_historical_0xEA01_proven":False,
            "new_guest_sessions_created_by_audit":False}

def audit(originals:Path,metadata:Path) -> dict:
    original.need(NEW_RUN not in original.RUNS and NEW_RUN not in prior.ALL_RUNS,
                  "new original source pin collides with earlier runs")
    previous=prior.audit(originals,metadata)
    original.RUNS[NEW_RUN]=PIN
    try:
        new=original.verify(NEW_RUN,originals/str(NEW_RUN),metadata)
    finally:
        del original.RUNS[NEW_RUN]
    return combine(previous,new,emulator_identity(originals/str(NEW_RUN)))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("originals","metadata","output"):
        p.add_argument("--"+key,type=Path,required=True)
    a=p.parse_args(argv)
    try:
        original.need(not a.output.exists() and not a.output.is_symlink(),
                      "refuse to overwrite existing source receipt")
        value=audit(a.originals,a.metadata)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(value,f,sort_keys=True,indent=2);f.write("\n")
        print(json.dumps({"result":RESULT,"guests":22,"hardware":False}))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error):
        print(json.dumps({"result":"STAGE390_AUTHENTIC_SOURCES_NOT_VERIFIED","hardware":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
