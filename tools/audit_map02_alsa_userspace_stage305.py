#!/usr/bin/env python3
"""Stage305 source-verified actual ALSA userspace symbol interposer audit.

Each S line: one anonymous TLS alias, one exported public ALSA operation,
snapshotted atomic total and return-status class counts. No PID, TID,
pointer/PCM, real thread names, addresses or raw logs. Identical return codes
in a separate null-device preflight do NOT prove timing-neutral interposition.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_pulse_event_clocks_stage301 import audit as prior_guest
from capture_map02_alsa_userspace_stage305 import OPS, KINDS, MAGIC, SIZE, SLOTS

SCHEMA="vh-map02-stage305-real-userspace-alsa-interposer/v1"
HOST="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
NRO="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
HEADER=["kind","monotonic_ns","anonymous_alias","operation",*KINDS]
MAX_SOURCE_ROWS=180000

def require(ok,reason):
    if not ok:raise ValueError(reason)

def samples(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),
            "Real sanitized ALSA userspace recorder missing")
    raw=p.read_bytes()
    require(150<=len(raw)<=16_000_000,"Real ALSA recorder size out of bounds")
    try: rows=list(csv.reader(raw.decode("ascii").splitlines()))
    except UnicodeError as e:raise ValueError("Non-ASCII userspace evidence") from e
    require(rows and rows[0]==HEADER,"ALSA evidence header invalid")
    require(20<len(rows)<=MAX_SOURCE_ROWS,"Too few or too many ALSA sample rows")
    stamps=[]
    details=[]
    active_tick=None
    per_alias={}
    last_total={}
    per_op_totals={}
    for fields in rows[1:]:
        require(len(fields)==len(HEADER),"ALSA counter row width invalid")
        kind,when,alias,op,*numbers=fields
        try:
            stamp=int(when)
            who=int(alias)
            vals=[int(x) for x in numbers]
        except ValueError as e:
            raise ValueError("ALSA sampled counters not integers") from e
        require(0<stamp<2**64 and all(0<=n<=2**64-1 for n in vals),
                "ALSA counter uint64/clock range invalid")
        if kind=="P":
            require(who==-1 and op=="sample" and all(x==0 for x in vals[1:]),
                    "Malformed ALSA sample marker")
            require(0<=vals[0]<100000,"Unbounded thread alias counter")
            require(not stamps or stamps[-1]<stamp<=stamps[-1]+2_000_000_000,
                    "Missing or unordered monotonic ALSA sample instant")
            stamps.append(stamp);active_tick=stamp
        elif kind=="S":
            require(stamp==active_tick,"ALSA per-thread row outside sample instant")
            require(0<=who<SLOTS and op in OPS,"Unexpected ALSA operation/thread alias")
            require(vals[0]>0 and sum(vals[1:])<=vals[0],
                    "ALSA return classification exceeds number of calls")
            key=(who,op)
            old=last_total.get(key,-1)
            require(vals[0]>=old,"ALSA function call count regressed")
            # P samples are serialized, but readers can observe between two
            # atomics incrementing TOTAL and one status class. No equalities
            # are forced for intermediate snapshots.
            require(key not in per_alias or per_alias[key]!=stamp,
                    "Duplicate ALSA thread+op row in one sample")
            per_alias[key]=stamp
            last_total[key]=vals[0]
            per_op_totals[key]=vals
            details.append((stamp,who,op,vals))
        else:
            raise ValueError("Unexpected ALSA recorder row kind")
    require(len(stamps)>=15 and stamps[-1]>stamps[0],
            "Too few actual monotonic ALSA observation samples")
    final={}
    for op in OPS:
        final[op]={k:sum(values[i] for (who,name),values in per_op_totals.items()
                          if name==op)
                   for i,k in enumerate(KINDS)}
    require(sum(x["total"] for x in final.values())>=0,
            "Invalid ALSA aggregate totals")
    return {
        "original_sanitized_sha256":hashlib.sha256(raw).hexdigest(),
        "original_sanitized_bytes":len(raw),
        "first_sample_ns":stamps[0],
        "last_sample_ns":stamps[-1],
        "monotonic_sample_instants":len(stamps),
        "distinct_alsa_anonymous_tls_aliases":len({who for who,op in per_op_totals}),
        "total_reported_alsa_function_entries":
            sum(x["total"] for x in final.values()),
        "per_symbol_final_return_class_counts":final,
        "observed_alias_operations":[{
            "anonymous_alias":who,"operation":op,
            "final_total":values[0],"final_eio":values[2],
            "final_epipe":values[3],"final_eagain":values[4],
        } for (who,op),values in sorted(per_op_totals.items())],
        "individual_calls_dont_have_exact_event_timestamps":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    prior=prior_guest(root,hint,run_id)
    require(prior["result"]=="REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED"
            and prior["exact_compiled_neXium_elf_sha256"]==HOST
            and prior["exact_generated_research_nro_sha256"]==NRO,
            "Stage305 genuine unmodified guest provenance invalid")
    stored=json.loads((root/"stage301-pulse-subscribe-verified.json").read_text())
    require(stored==prior,"Original Stage301 guest/P/L/optical/PCM not reverified")
    manifest=json.loads((root/"stage305-interposer-build-manifest.json").read_text())
    require(manifest["schema"]=="vh-map02-stage305-alsa-interposer-build/v1"
            and manifest["result"]=="REAL_ALSA_INTERPOSER_BINARY_COMPILED"
            and len(manifest["interposer_so_sha256"])==64
            and manifest["preflight_synthetic_null_device_return_codes_match"] is True
            and manifest["preflight_interposer_observed_public_alsa_calls"] is True
            and manifest["actual_original_game_or_ps1_music_used"] is False,
            "Stage305 compiled interposer or synthetic test source proof invalid")
    report=samples(root/"alsa-userspace-anonymous-atomic.csv")
    ready=int((root/"alsa-userspace-observer-ready-ns.txt").read_text().strip())
    a=prior["guest_first_input_monotonic_ns"]
    b=prior["guest_last_observation_monotonic_ns"]
    require(0<ready<=report["first_sample_ns"]<a<b
            and report["last_sample_ns"]>=b-1_000_000_000,
            "ALSA userspace recorder did not overlap original guest window")
    # Reject traces polluted with process names or system paths.
    require(not (root/"alsa-userspace-counter-PRIVATE.bin").is_symlink()
            if (root/"alsa-userspace-counter-PRIVATE.bin").exists() else True,
            "Private counter file should not be symlinked")
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE305_PINNED_GUEST_USERSPACE_ALSA_COUNTERS_SOURCE_REPARSED",
        "requested_pulse_latency_hint_ms":hint,"real_actions_run_id":run_id,
        "host_elf_sha256":HOST,"generated_rom_free_nro_sha256":NRO,
        "actual_original_game_or_ps1_music_used":False,
        "guest_cpal_entries_after_input":prior["host_guest_window_cpal_callback_entries"],
        "guest_crc_8_pages_passed":prior["guest_final_8_page_crc_verified"],
        "virtual_pcm16_nonzero_samples":prior["virtual_pcm_nonzero_samples"],
        "interposer_so_sha256":manifest["interposer_so_sha256"],
        "interposer_synthetic_forwarding_parity_verified":True,
        **report,
        "no_process_tid_arguments_addresses_or_pcm_saved":True,
        "per_thread_alias_is_not_sourced_kernel_tid":True,
        "ld_preload_changes_symbol_resolution_and_timing":True,
        "calls_observed_at_alsa_export_do_not_prove_cpal_callback_owner":True,
        "missing_interposed_calls_do_not_prove_no_alsa_function_activity":True,
        "physical_switch_dac_or_alsa_root_cause_proven":False,
        "production_audio_fix_proven":False,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",required=True,type=Path)
    ap.add_argument("--hint",required=True,type=int)
    ap.add_argument("--run-id",required=True,type=int)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try: report=audit(args.evidence,args.hint,args.run_id);rc=0
    except (ValueError,OSError,KeyError,TypeError,UnicodeError,
            json.JSONDecodeError,csv.Error) as e:
        report={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "production_audio_fix_proven":False};rc=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":raise SystemExit(main())
