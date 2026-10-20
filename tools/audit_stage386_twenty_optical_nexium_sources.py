#!/usr/bin/env python3
"""Reaudit ten original NeXium guest pairs, with Stage384/385 binary provenance for pair 10.

No new NeXium executions, real Switch hardware proof or PCM/game asset redistribution.
"""
from __future__ import annotations
import argparse
import json
import zlib
from pathlib import Path
import audit_stage373_six_optical_originals as original
import audit_stage383_eighteen_optical_originals as previous

TENTH_RUN = 39489476524
PIN = {
    "head": "ec0ab2cda2f8a2144ee4ab81596a15d365eea6df",
    "merge": "c1fadb4a61b0e8219f6c02782d2d7531492bbc27",
    "artifact": 12296297012,
    "digest": "sha256:235414769b87927a7a24893774ce1b9e0867fce508aed7e7e569c5aac79ce0ea",
    "optical": [
        "a9d7ac5addee0ae60f274d751f660adb51eed0c34a6cee6d0bbcb89a8f78157b",
        "282e591779f136a1e2ce947b59c2fa274bd0c304579586d33743ad43261ccac2",
    ],
    "reason": [
        "b278af55d7a57770ffc8723ba883042145214e1f7563a05b5adfc66fa161e734",
        "2d8e9c950b201e0233f5ea269d64bf67ea2a7ac5c3af626addc85b3cbe5af43d",
    ],
}
ALL_RUNS = (*previous.ALL_RUNS, TENTH_RUN)
EXPECTED_EMULATOR_TAR = "c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66"
EXPECTED_EMULATOR_BIN = "5026f934ed7cd7d81a5901e536f5fe29b00e117861d432f9be351730afc7d964"
RESULT = "STAGE386_TWENTY_SOURCE_PINNED_NEIXUM_GUEST_EXITS_AND_TENTH_EMULATOR_FINGERPRINT"


def check_provenance(directory: Path) -> dict:
    need = original.need
    binary = original.metadata(directory / "runtime-evidence/nexium-runtime-binary-provenance.json")
    archive = original.metadata(directory / "runtime-evidence/nexium-tar-preextract.json")
    need(binary.get("schema") == "vh-stage384-nexium-runtime-bytes/v1" and
         binary.get("result") == "STAGE384_ONE_GUEST_RUN_NEXIUM_BYTES_PINNED" and
         binary.get("source_run_id") == TENTH_RUN and
         binary.get("source_head_sha") == PIN["merge"] and
         binary.get("release_id") == archive.get("release_id") == 340509243 and
         binary.get("release_asset_id") == archive.get("release_asset_id") == 658656899 and
         binary.get("asset_name") == archive.get("asset_name") == "nexium-linux-x86_64.tar.gz" and
         binary.get("asset_sha256") == archive.get("archive_sha256") == EXPECTED_EMULATOR_TAR and
         binary.get("asset_size_bytes") == archive.get("archive_bytes") == 114182978 and
         binary.get("advertised_asset_digest_checked") is True and
         binary.get("binary_sha256") == EXPECTED_EMULATOR_BIN and
         binary.get("binary_name") == "nexium" and
         binary.get("binary_size_bytes") == 304888160 and
         binary.get("hardware_status") == archive.get("hardware_status") == "HARDWARE NOT TESTED" and
         binary.get("physical_audio_output_tested") is False and
         binary.get("same_binary_in_historical_runs_proven") is False and
         archive.get("result") == "STAGE385_RELEASE_ARCHIVE_BYTES_AND_TAR_PATHS_VERIFIED" and
         archive.get("ready_for_controlled_extraction") is True and
         archive.get("github_advertised_sha256_checked") is True and
         archive.get("binary_authenticity_signed") is False and
         archive.get("member_count") == 15 and archive.get("symbolic_links") == 0,
         "tenth original emulator binary identity or pre-extraction receipt invalid")
    return {
        "release_id": binary["release_id"],
        "release_asset_id": binary["release_asset_id"],
        "archive_sha256": EXPECTED_EMULATOR_TAR,
        "binary_sha256": EXPECTED_EMULATOR_BIN,
        "same_binary_in_earlier_nine_runs_proven": False,
        "binary_unchanged_between_tenth_guest_runs_proven_by_original_ci_step": True,
        "physical_switch_audio_tested": False,
    }


def combine(prior: dict, pair: list[dict], emulator: dict) -> dict:
    need=original.need
    need(type(prior) is dict and prior.get("result") == previous.RESULT and
         prior.get("source_run_ids") == list(previous.ALL_RUNS) and
         prior.get("original_guest_sessions") == 18 and
         prior.get("successful_software_wait_results") == 18 and
         prior.get("distinct_original_optical_pngs") == 18 and
         prior.get("distinct_crc_checked_optical_packets") == 18 and
         prior.get("physical_switch_speaker_audio_tested") is False and
         prior.get("cause_of_historical_0xEA01_proven") is False,
         "previous eighteen independent guests not validated")
    need(type(pair) is list and len(pair)==2 and
         [(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in pair] ==
         [(TENTH_RUN,"a",6),(TENTH_RUN,"b",12)], "invalid tenth source capture pair")
    need(type(emulator) is dict and
         emulator.get("archive_sha256") == EXPECTED_EMULATOR_TAR and
         emulator.get("binary_sha256") == EXPECTED_EMULATOR_BIN and
         emulator.get("same_binary_in_earlier_nine_runs_proven") is False and
         emulator.get("binary_unchanged_between_tenth_guest_runs_proven_by_original_ci_step") is True and
         emulator.get("physical_switch_audio_tested") is False,
         "emulator source provenance not confirmed")
    preceding=prior.get("sessions")
    need(type(preceding) is list and len(preceding)==18,"missing previous sessions")
    rows=preceding+pair
    need(len(rows)==20 and [(x.get("run_id"),x.get("trial"),x.get("dwell_seconds")) for x in rows] ==
         [(run,t,d) for run in ALL_RUNS for t,d in (("a",6),("b",12))],
         "missing, swapped or reused original guest")
    for s in rows:
        need(s.get("guest_result")==0 and s.get("released_descriptors")==1 and
             type(s.get("pcm_pages_acquired_and_released")) is int and
             s["pcm_pages_acquired_and_released"]>0 and
             type(s.get("tail_interval_ms")) in (int,float) and
             0<s["tail_interval_ms"]<12 and
             s.get("complete_scene_serials")==4 and s.get("guest_event_rows")==23 and
             s.get("dropped_guest_events")==0, "unbalanced lease, lost music event or guest wait failure")
        for kind in ("original_optical_sha256","pixel_packet_sha256","original_reason_sha256"):
            value=s.get(kind)
            need(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),
                 "bad guest source digest")
    for kind in ("original_optical_sha256","pixel_packet_sha256"):
        need(len({s[kind] for s in rows})==20, "duplicate original optical PNG or pixel packet")
    # Identical counter CSVs across distinct original sessions are permitted.
    grouped={}
    for s in rows:
        grouped.setdefault(s["original_reason_sha256"], []).append({"run_id":s["run_id"],"trial":s["trial"]})
    return {
        "schema":"vh-stage386-twenty-original-guest-exits-and-emulator-provenance/v1",
        "result":RESULT, "source_run_ids":list(ALL_RUNS),
        "original_guest_sessions":20,"guest_wait_result_zero":20,
        "exact_returned_descriptors":20,"unique_crc_verified_optical_packets":20,
        "complete_music_scene_transitions":80,"dropped_guest_events":0,
        "distinct_reason_counter_csv_sha256_count":len(grouped),
        "repeated_reason_counter_csv":[{"sha256":k,"sessions":v} for k,v in sorted(grouped.items()) if len(v)>1],
        "min_tail_append_plus_wait_ms":min(x["tail_interval_ms"] for x in rows),
        "max_tail_append_plus_wait_ms":max(x["tail_interval_ms"] for x in rows),
        "nro_sha256":original.NRO_SHA,"tenth_run_neixum_emulator":emulator,
        "sessions":rows,"new_guest_sessions_created_by_audit":False,
        "physical_switch_speaker_audio_tested":False,
        "cause_of_historical_0xEA01_proven":False,
        "direct_exit_queue_depth_measured":False,
        "controlled_causal_dwell_experiment":False,
    }


def audit(originals:Path,metadata:Path) -> dict:
    original.need(tuple(original.RUNS)==tuple(previous.prior.eight.SIX_RUNS)
                  and TENTH_RUN not in original.RUNS
                  and TENTH_RUN not in previous.ALL_RUNS,
                  "historical source pins unexpectedly changed")
    old=previous.audit(originals,metadata)
    original.RUNS[TENTH_RUN]=PIN
    try:
        new=original.verify(TENTH_RUN,originals/str(TENTH_RUN),metadata)
    finally:
        del original.RUNS[TENTH_RUN]
    return combine(old,new,check_provenance(originals/str(TENTH_RUN)))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("originals","metadata","output"):
        p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args(argv)
    try:
        original.need(not args.output.exists() and not args.output.is_symlink(),"refuse overwriting audit report")
        report=audit(args.originals,args.metadata)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as output:
            json.dump(report,output,indent=2,sort_keys=True);output.write('\n')
        print(json.dumps({'result':RESULT,'original_guest_sessions':20,
                          'hardware_audio_tested':False},sort_keys=True))
        return 0
    except (ValueError,KeyError,TypeError,IndexError,OSError,UnicodeError,zlib.error):
        print(json.dumps({'result':'STAGE386_ORIGINAL_SOURCES_NOT_VERIFIED',
                          'hardware_audio_tested':False},sort_keys=True))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
