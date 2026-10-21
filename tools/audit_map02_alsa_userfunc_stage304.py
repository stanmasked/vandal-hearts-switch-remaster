#!/usr/bin/env python3
"""Stage304 source-pinned genuine NeXium LD_PRELOAD ALSA-call summaries.

The preloader interposes the public snd_pcm_avail_delay symbol only. It is
NOT proven that every internal libasound call traverses the public symbol.
Timestamps of *negative returns* are measured by the wrapper after return;
success calls are cumulative samples every ~200ms, not exact events.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_pulse_event_clocks_stage301 import audit as reparse_prior

SCHEMA="vh-map02-stage304-real-alsa-userspace-availability-interpose/v1"
SLOTS=64
HOST_SHA="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
FIELDS=("calls","success","eio","epipe","eagain","other","first_negative_ns",
        "last_negative_ns")
COUNTERS=FIELDS[:6]

def need(ok,why):
    if not ok: raise ValueError(why)

def raw(path):
    p=Path(path)
    need(p.is_file() and not p.is_symlink(),"Missing original Stage304 ALSA public symbol trace")
    b=p.read_bytes()
    need(150<=len(b)<=5_000_000,"ALSA user-space trace missing or unbounded")
    try: lines=list(csv.reader(b.decode("ascii").splitlines()))
    except (UnicodeDecodeError,csv.Error) as ex:
        raise ValueError("ALSA user-space trace should contain only bounded ASCII CSV") from ex
    need(10<=len(lines)<=SLOTS*240+240,"ALSA user-space snapshots missing or unbounded")
    h=[]; snapshots=defaultdict(dict)
    old={}
    for row in lines:
        need(row and row[0] in ("H","T"),"Unexpected preloader record")
        try: vals=[int(v) for v in row[1:]]
        except ValueError as ex: raise ValueError("Nonnumeric preloader counter") from ex
        need(all(0<=v<2**64 for v in vals),"Invalid negative or overflowing preloader data")
        if row[0]=="H":
            need(len(row)==5,"Malformed ALSA usertrace heartbeat")
            now,slots,overflow,found=vals
            need(now>0 and slots<10000 and found in (0,1),
                 "Invalid preloader symbol and heartbeat")
            if h:
                need(h[-1]["clock"]<now<=h[-1]["clock"]+2_000_000_000,
                    "Preloader sampled heartbeat clock regression")
            h.append({"clock":now,"slots":slots,
                      "overflow":overflow,"symbol_found":bool(found)})
            need(len(h)<=240,"Too many ALSA observer heartbeats")
        else:
            need(len(row)==11 and h,"T row without correct H heartbeat")
            now,alias,*numbers=vals
            need(now==h[-1]["clock"] and 1<=alias<=SLOTS
                 and alias<=h[-1]["slots"],
                 "ALSA slot row sample clock/alias mismatched")
            data=dict(zip(FIELDS,numbers))
            need(alias not in snapshots[now],"Duplicate ALSA per-thread slot row")
            need(sum(data[k] for k in COUNTERS[1:])<=data["calls"],
                 "ALSA error/success totals exceed intercepted call count")
            need((data["first_negative_ns"]==0)==
                 (data["last_negative_ns"]==0),
                 "Unpaired first/last negative return timestamp")
            if data["first_negative_ns"]:
                need(0<data["first_negative_ns"]<=data["last_negative_ns"]<=
                     now+1_000_000_000,
                     "Impossible monotonic ALSA return timestamp")
            if alias in old:
                prior=old[alias]
                need(all(data[k]>=prior[k] for k in COUNTERS),
                     "Monotonic ALSA per-thread counts decreased")
                need(prior["first_negative_ns"] in (0,data["first_negative_ns"]),
                     "First negative timestamp changed")
                need(data["last_negative_ns"]>=prior["last_negative_ns"],
                     "Last negative timestamp regressed")
            old[alias]=data
            snapshots[now][alias]=data
    need(len(h)>=12,"Insufficient live NeXium reporter heartbeats")
    need(h[-1]["slots"]<=SLOTS and h[-1]["overflow"]==0,
         "Exceeded validated finite anonymized ALSA task slots")
    return h,snapshots,hashlib.sha256(b).hexdigest()

def audit(root,hint,run_id):
    root=Path(root)
    need(root.is_dir() and not root.is_symlink(),"Actual guest evidence missing")
    prior=reparse_prior(root,hint,run_id)
    need(prior["result"]=="REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED"
         and prior["exact_compiled_neXium_elf_sha256"]==HOST_SHA
         and prior["exact_generated_research_nro_sha256"]==NRO_SHA,
         "Original opt-in NRO/P/L/Pulse provenance not verified")
    saved=json.loads((root/"stage301-pulse-subscribe-verified.json").read_text())
    need(saved==prior,"Original Stage301 raw guest/P/L proof changed")
    heartbeats,snaps,digest=raw(root/"host-alsa-avail-delay-usertrace.csv")
    first=prior["guest_first_input_monotonic_ns"]
    last=prior["guest_last_observation_monotonic_ns"]
    need(heartbeats[0]["clock"]<first
         and heartbeats[-1]["clock"]>=last-1_000_000_000,
         "ALSA user-space trace did not span the actual guest observation")
    pre=[h for h in heartbeats if h["clock"]<=first]
    final=[h for h in heartbeats if h["clock"]<=last]
    need(pre and final and final[-1]["clock"]>pre[-1]["clock"],
         "No independently bracketing ALSA guest evidence")
    left=snaps[pre[-1]["clock"]]
    right=snaps[final[-1]["clock"]]
    totals={}
    for key in COUNTERS:
        totals[key]=sum(x[key] for x in right.values())-sum(x[key] for x in left.values())
        need(totals[key]>=0,"Decreasing ALSA cumulative counts over actual guest")
    need(sum(totals[k] for k in COUNTERS[1:])<=totals["calls"],
         "Guest ALSA status totals exceed actual captured calls")
    final_slots=[]
    for alias,vals in sorted(right.items()):
        base=left.get(alias,{key:0 for key in FIELDS})
        final_slots.append({
            "anonymous_thread_slot":alias,
            "guest_interval_captured_calls":vals["calls"]-base["calls"],
            "guest_interval_successful_returns":vals["success"]-base["success"],
            "guest_interval_EIO_returns":vals["eio"]-base["eio"],
            "guest_interval_EPIPE_returns":vals["epipe"]-base["epipe"],
            "guest_interval_EAGAIN_returns":vals["eagain"]-base["eagain"],
            "guest_interval_other_negative_returns":vals["other"]-base["other"],
            "first_observed_negative_return_monotonic_ns":
                vals["first_negative_ns"] or None,
            "last_observed_negative_return_monotonic_ns":
                vals["last_negative_ns"] or None,
        })
    sha_path=root/"research-alsa-preload-sha256.txt"
    digest_text=sha_path.read_text(encoding="ascii").strip()
    need(len(digest_text)==64 and all(c in "0123456789abcdef" for c in digest_text),
         "Actual built ALSA interposer hash absent")
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE304_GUEST_USERSPACE_ALSA_AVAIL_DELAY_REPARSED",
        "requested_pulse_latency_hint_ms":hint,
        "real_github_actions_run_id":run_id,
        "new_preload_shared_object_sha256":digest_text,
        "preload_reporter_interceptor_symbol_resolved":
            any(x["symbol_found"] for x in heartbeats),
        "actual_stage298_nexium_elf_sha256":HOST_SHA,
        "unchanged_generated_rom_free_guest_nro_sha256":NRO_SHA,
        "original_stage301_guest_audit_sha256":hashlib.sha256(
            (root/"stage301-pulse-subscribe-verified.json").read_bytes()).hexdigest(),
        "raw_ALSA_usertrace_sha256":digest,
        "heartbeats":len(heartbeats),
        "first_preloader_heartbeat_ns":heartbeats[0]["clock"],
        "last_preloader_heartbeat_ns":heartbeats[-1]["clock"],
        "pre_guest_baseline_sample_ns":pre[-1]["clock"],
        "last_guest_sample_ns":final[-1]["clock"],
        "source_guest_post_input_CPAL_callback_entries":
            prior["host_guest_window_cpal_callback_entries"],
        "source_guest_research_optical_CRC_8_of_8":
            prior["guest_final_8_page_crc_verified"],
        "source_virtual_48k_PCM_nonzero_samples":
            prior["virtual_pcm_nonzero_samples"],
        "intercepted_ALSA_avail_delay_guest_counts":totals,
        "anonymized_per_thread_ALSA_counters":final_slots,
        "zero_calls_does_not_prove_ALSA_not_running":True,
        "LD_PRELOAD_public_symbol_can_miss_internal_or_versioned_calls":True,
        "only_negative_returns_have_individual_monotonic_timestamps":True,
        "preloader_and_separate_reporter_perturb_host_timing":True,
        "failure_returns_not_proven_guest_CPAL_error_callback_cause":True,
        "original_PS1_game_assets_or_audio_used":False,
        "no_alsa_root_cause_or_physical_switch_output_proven":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--hint",type=int,required=True)
    ap.add_argument("--run-id",type=int,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        report=audit(a.evidence,a.hint,a.run_id);code=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as ex:
        report={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(ex),
            "no_alsa_root_cause_or_physical_switch_output_proven":True}
        code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True,indent=2))
    return code

if __name__=="__main__":
    raise SystemExit(main())
