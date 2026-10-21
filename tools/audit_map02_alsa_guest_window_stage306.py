#!/usr/bin/env python3
"""Stage306 verified post-input ALSA per-anonymous-alias snapshot deltas.

Read only the two original Stage305 Actions artifacts. Independently reparse
retained raw CPAL P/L and userspace ALSA CSV, hash original Pulse event CSV,
and cross-check Stage305 SUCCESS receipts where private Pulse snapshots,
raw virtual PCM and private GUI FileLogger were NOT uploaded intentionally.
Never reconstruct or claim a recheck of missing raw evidence.
The same alias number across separate trial processes is NOT thread identity.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_alsa_userspace_stage305 import samples as reparse_alsa
from audit_map02_cpal_lifetime_stage299 import analyze as reparse_cpal
from capture_map02_alsa_userspace_stage305 import KINDS,OPS,SLOTS

SCHEMA="vh-map02-stage306-source-reparsed-alsa-guest-window-alias-deltas/v1"
SOURCE_RUN=39558740492
SOURCE_HEAD="193cd92e75bebe31353d345ddc5b961ffa5f30d1"
EXPECTED_NAMES={
    21:"map02-stage305-real-userspace-alsa-hint21-evidence",
    22:"map02-stage305-real-userspace-alsa-hint22-evidence",
}
CSV_HEADER=["kind","monotonic_ns","anonymous_alias","operation",*KINDS]

def require(ok,reason):
    if not ok:raise ValueError(reason)

def read_json(path):
    data=json.loads(Path(path).read_text())
    require(type(data) is dict,"Source JSON was not an object")
    return data

def window_deltas(csv_path,first,last):
    p=Path(csv_path)
    require(p.is_file() and not p.is_symlink(),
            "Source Stage305 anonymous ALSA CSV missing")
    raw=p.read_bytes()
    require(100<len(raw)<16_000_000,"ALSA CSV source size invalid")
    try:
        rows=list(csv.reader(raw.decode("ascii").splitlines()))
    except UnicodeError as e:raise ValueError("Non-ASCII ALSA CSV") from e
    require(rows and rows[0]==CSV_HEADER,"Stage305 exact source CSV header changed")
    require(type(first) is int and type(last) is int and 0<first<last,
            "Original monotonic guest markers invalid")
    frames=[]
    frame=None
    last_ts=-1
    for row in rows[1:]:
        require(len(row)==len(CSV_HEADER),"Stage305 source row width mismatch")
        kind,when,alias,op,*fields=row
        try:
            clock=int(when);tid=int(alias);nums=tuple(int(x) for x in fields)
        except ValueError as e:raise ValueError("Noninteger ALSA CSV field") from e
        require(0<clock<2**64 and all(0<=x<2**64 for x in nums),
                "ALSА CSV invalid bounded clocks and counters")
        if kind=="P":
            require(clock>last_ts and tid==-1 and op=="sample",
                    "Missing or misordered complete P boundary")
            frame={"ts":clock,"slot_count":nums[0],"ops":{}}
            require(0<=nums[0]<100000 and not any(nums[1:]),
                    "Original Stage305 slot count invalid")
            frames.append(frame);last_ts=clock
        elif kind=="S":
            require(frame is not None and clock==frame["ts"],
                    "S row outside source P sampling instant")
            require(0<=tid<SLOTS and op in OPS,"Unknown exported ALSA symbol/TLS alias")
            require(nums[0]>0 and sum(nums[1:])<=nums[0],
                    "ALSA return class > original total")
            key=(tid,op)
            require(key not in frame["ops"],"Duplicate TLS alias and symbol in sample")
            frame["ops"][key]=dict(zip(KINDS,nums))
        else:
            raise ValueError("Unexpected Stage305 source frame record")
    pre=[f for f in frames if f["ts"]<=first]
    late=[f for f in frames if f["ts"]<=last]
    require(pre and late,"No source counter frames bounding true guest")
    b=pre[-1];a=late[-1]
    require(b["ts"]<first<last and a["ts"]>first,
            "Original guest markers not strictly enclosed by source P snapshots")
    require(first-b["ts"]<1_000_000_000 and last-a["ts"]<1_000_000_000,
            "Unacceptably distant bracketing ALSA snapshots")
    differences=[]
    for alias,op in sorted(set(b["ops"])|set(a["ops"])):
        old=b["ops"].get((alias,op),{k:0 for k in KINDS})
        new=a["ops"].get((alias,op),{k:0 for k in KINDS})
        delta={k:new[k]-old[k] for k in KINDS}
        require(all(x>=0 for x in delta.values()),
                "Source ALSA cumulative counters regressed over guest")
        # Return-category snapshots are not atomic as a group; don't assume
        # every sampled TOTAL necessarily equals a category sum.
        if delta["total"]:
            differences.append({
                "anonymous_alias":alias,
                "exported_alsa_symbol":op,
                "guest_window_sampled_return_class_deltas":delta,
            })
    per_op=defaultdict(lambda: {k:0 for k in KINDS})
    for item in differences:
        bucket=per_op[item["exported_alsa_symbol"]]
        for key,value in item["guest_window_sampled_return_class_deltas"].items():
            bucket[key]+=value
    return {
        "source_alsa_csv_sha256":hashlib.sha256(raw).hexdigest(),
        "source_alsa_csv_length_bytes":len(raw),
        "actual_guest_first_input_ns":first,
        "actual_guest_final_observation_ns":last,
        "pre_input_alsa_snapshot_ns":b["ts"],
        "late_alsa_snapshot_ns":a["ts"],
        "pre_input_snapshot_observation_lag_ns":first-b["ts"],
        "late_snapshot_observation_lag_ns":last-a["ts"],
        "source_snapshot_count":len(frames),
        "delta_by_anonymous_alias_and_exported_symbol":differences,
        "delta_by_exported_symbol":dict(sorted(per_op.items())),
        "no_exact_individual_alsa_call_timestamp":True,
        "separate_trial_anonymous_aliases_are_not_globally_comparable":True,
    }


def verify_available_original_stage305_sources(root,hint):
    """Replay only genuine available source streams; trust private data receipts."""
    root=Path(root)
    saved=read_json(root/"stage305-userspace-alsa-guest-audit.json")
    require(saved["schema"]=="vh-map02-stage305-real-userspace-alsa-interposer/v1"
            and saved["result"]==
                "REAL_STAGE305_PINNED_GUEST_USERSPACE_ALSA_COUNTERS_SOURCE_REPARSED"
            and saved["real_actions_run_id"]==SOURCE_RUN
            and saved["requested_pulse_latency_hint_ms"]==hint,
            "Original actual Stage305 verified receipt invalid")
    meta=read_json(root/"stage299-pinned-new-host-guest.json")
    require(meta["schema"]=="vh-map02-stage299-pinned-new-elf-and-generated-nro/v1"
            and meta["actual_stage299_run_id"]==SOURCE_RUN
            and meta["attempt"]==1 and meta["hint_ms"]==hint
            and meta["exact_stage298_elf_sha256"]==saved["host_elf_sha256"]
            and meta["exact_generated_nro_sha256"]==
                saved["generated_rom_free_nro_sha256"],
            "Source build identity does not match verified receipt")
    build=read_json(root/"stage305-interposer-build-manifest.json")
    require(build["result"]=="REAL_ALSA_INTERPOSER_BINARY_COMPILED"
            and build["interposer_so_sha256"]==saved["interposer_so_sha256"]
            and build["preflight_synthetic_null_device_return_codes_match"] is True
            and build["preflight_interposer_observed_public_alsa_calls"] is True
            and build["actual_original_game_or_ps1_music_used"] is False,
            "Original private shim built identity was altered")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    host=reparse_cpal(root/"host-cpal-lifetime-p.csv",
                      root/"host-cpal-audioout-timeline.csv",first,last)
    require(host==read_json(root/"host-cpal-lifetime-audit.json")
            and host["guest_window_original_l_cpal_entry_delta"]==
                saved["guest_cpal_entries_after_input"],
            "Independent raw P/L time series differs from original audited receipt")
    alsa=reparse_alsa(root/"alsa-userspace-anonymous-atomic.csv")
    require(all(saved.get(k)==v for k,v in alsa.items()),
            "Source raw ALSA rows differ from signed trial summary")
    pulse=read_json(root/"stage301-pulse-subscribe-verified.json")
    pulse_raw=(root/"pulse-sink-input-events-monotonic.csv").read_bytes()
    require(pulse["schema"]==
                "vh-map02-stage301-pulse-subscribe-monotonic-real-guest/v1"
            and pulse["result"]==
                "REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED"
            and pulse["source_actions_run_id"]==SOURCE_RUN
            and pulse["hint_ms"]==hint
            and pulse["guest_first_input_monotonic_ns"]==first
            and pulse["guest_last_observation_monotonic_ns"]==last
            and pulse["host_guest_window_cpal_callback_entries"]==
                saved["guest_cpal_entries_after_input"]
            and pulse["guest_final_8_page_crc_verified"]==
                saved["guest_crc_8_pages_passed"]
            and pulse["virtual_pcm_nonzero_samples"]==
                saved["virtual_pcm16_nonzero_samples"]
            and hashlib.sha256(pulse_raw).hexdigest()==
                pulse["pulse_subscribe_receipt_sha256"],
            "Retained Pulse event file SHA or previous verified Pulse receipt changed")
    old=read_json(root/"stage299-source-pinned-real-lifetime-receipt.json")
    require(old["schema"]==
                "vh-map02-stage299-real-new-elf-lifetime-guest-evidence/v1"
            and old["result"]==
                "REAL_STAGE299_NEW_SHA_PINNED_P_L_GUEST_FILELOGGER_VERIFIED"
            and old["actual_run_id"]==SOURCE_RUN
            and old["hint_ms"]==hint
            and old["guest_8_pages_crc_verified"]==
                saved["guest_crc_8_pages_passed"]
            and old["virtual_pcm_nonzero_samples"]==
                saved["virtual_pcm16_nonzero_samples"]
            and old["host_L_guest_window_callback_delta"]==
                saved["guest_cpal_entries_after_input"],
            "Original previously audited GUI/optical/PCM receipt changed")
    image=read_json(root/"guest-final-receipt.json")
    require((image["result"]=="GUEST_PRESUBMIT_PCM_PAGES_MATCHED")==
            saved["guest_crc_8_pages_passed"],
            "Original optical receipt disagrees with original ALSA audit")
    pcm=read_json(root/"virtual-pcm-health.json")
    require(pcm["nonzero_pcm16_samples"]==
            saved["virtual_pcm16_nonzero_samples"],
            "Prior real PCM sha verified receipt differs from ALSA guest")
    return saved

def one(root,hint):
    root=Path(root)
    require(root.name==EXPECTED_NAMES[hint] and root.is_dir() and not root.is_symlink(),
            "Original Stage305 Actions artifact directory identity absent")
    original=verify_available_original_stage305_sources(root,hint)
    saved=read_json(root/"stage305-userspace-alsa-guest-audit.json")
    require(original==saved and original["result"]==
            "REAL_STAGE305_PINNED_GUEST_USERSPACE_ALSA_COUNTERS_SOURCE_REPARSED",
            "Stage305 original real-run receipt cannot be independently reproduced")
    require(original["real_actions_run_id"]==SOURCE_RUN
            and original["requested_pulse_latency_hint_ms"]==hint,
            "Source actual Stage305 run identity changed")
    prior_receipt=read_json(root/"stage299-pinned-new-host-guest.json")
    require(prior_receipt["actual_stage299_run_id"]==SOURCE_RUN
            and prior_receipt["attempt"]==1,
            "Actual original guest build/trial attempt did not match")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    delta=window_deltas(root/"alsa-userspace-anonymous-atomic.csv",first,last)
    require(delta["source_alsa_csv_sha256"]==
            original["original_sanitized_sha256"],
            "Original Stage305 audited ALSA raw CSV SHA disagrees")
    return {
        "requested_pulse_hint_ms":hint,
        "source_real_actions_run_id":SOURCE_RUN,
        "retained_raw_cpal_P_L_and_alsa_reparsed":True,
        "retained_pulse_event_csv_sha_rechecked":True,
        "unuploaded_private_pulse_pcm_filelogger_not_reparsed":True,
        "prior_stage305_pulse_pcm_filelogger_receipts_cross_checked":True,
        "stage305_original_audit_json_sha256":hashlib.sha256(
            (root/"stage305-userspace-alsa-guest-audit.json").read_bytes()).hexdigest(),
        "actual_guest_CPAL_post_input_entries":
            original["guest_cpal_entries_after_input"],
        "actual_guest_optical_crc_8_of_8_verified":
            original["guest_crc_8_pages_passed"],
        "actual_virtual_pcm16_nonzero_samples":
            original["virtual_pcm16_nonzero_samples"],
        "original_entire_host_process_ALSA_function_call_count":
            original["total_reported_alsa_function_entries"],
        **delta,
    }

def compare(root):
    root=Path(root)
    require(root.is_dir() and not root.is_symlink(),"Original Stage305 source pair missing")
    actual={p.name for p in root.iterdir() if p.is_dir()}
    require(actual==set(EXPECTED_NAMES.values()),
            "Unexpected source artifact pair absent, renamed or extra")
    data=[one(root/EXPECTED_NAMES[hint],hint) for hint in (21,22)]
    # No fixed behavioral outcome forced by parser: 21 and 22 are two real
    # independent trials, not a proven exact 1ms audio hardware threshold.
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE305_PAIR_POST_INPUT_ALSA_SNAPSHOT_DELTAS_REPARSED",
        "original_source_github_actions_run_id":SOURCE_RUN,
        "original_stage305_head_commit":SOURCE_HEAD,
        "trials":data,
        "unobserved_library_internal_or_dlsym_calls_may_exist":True,
        "raw_Pulse_snapshots_virtual_PCM_and_private_FileLogger_were_not_uploaded":True,
        "full_source_replay_of_unuploaded_data_is_impossible":True,
        "ld_preload_perturbs_nexium_symbol_resolution_and_timing":True,
        "alsa_export_call_not_source_proven_cpal_callback_thread":True,
        "guest_window_endpoints_are_bounded_sample_times_not_exact_callbacks":True,
        "original_game_rom_or_ps1_soundtrack_or_physical_switch_audio_used":False,
        "no_audio_root_cause_or_production_fix_proven":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    try:
        r=compare(args.root);ret=0
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,
            json.JSONDecodeError,csv.Error) as e:
        r={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
           "no_audio_root_cause_or_production_fix_proven":True}
        ret=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True))
    return ret

if __name__=="__main__":raise SystemExit(main())
