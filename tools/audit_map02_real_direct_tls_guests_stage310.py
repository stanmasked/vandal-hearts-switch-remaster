#!/usr/bin/env python3
"""Stage310 source-verified SAME native execution-thread TLS alias from CPAL and ALSA.

Unlike Stage307 temporal inference, the opt-in Stage308 callback marker and
ALSA interposer use one process-internal C __thread alias allocator. Source
proof applies ONLY to the separately built and instrumented Stage309 ELF.
The old frozen Stage298 uninstrumented ELF has no direct marker.

The CSVs carry no PID/TID/pointer, no native stack identity, no audio PCM.
Cumulative sampled counters cannot reveal precise individual call timestamps.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_lifetime_stage299 import analyze as analyze_original_host_p_l
from audit_map02_alsa_userspace_stage305 import samples as analyze_alsa
from capture_map02_alsa_userspace_stage305 import KINDS,OPS,SLOTS

SCHEMA="vh-map02-stage310-real-direct-cpal-alsa-same-TLS-guest/v1"
NRO_SHA="371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b"
TAG_HEADER=["kind","monotonic_ns","anonymous_tls_alias","cpal_callback_mark_entries"]
MAX_RECORDS=26000

def require(ok,reason):
    if not ok:raise ValueError(reason)

def read_tag(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"Original tagged callback CSV missing")
    b=p.read_bytes()
    require(100<len(b)<3_000_000,"Bounded raw CPAL alias CSV missing")
    try:rows=list(csv.reader(b.decode("ascii").splitlines()))
    except UnicodeError as e:raise ValueError("Non-ASCII callback marker source") from e
    require(rows and rows[0]==TAG_HEADER,"CPAL marker source header changed")
    require(20<len(rows)<=MAX_RECORDS,"Tag source row count invalid")
    samples=[]
    last_seen={}
    for line in rows[1:]:
        require(len(line)==4,"Invalid CPAL marker row")
        kind,when,alias,count=line
        try:now=int(when);who=int(alias);v=int(count)
        except ValueError as e:raise ValueError("Invalid callback marker integer") from e
        require(0<now<2**64 and 0<=v<2**64,"Invalid callback marker u64")
        if kind=="P":
            require(who==-1 and 0<=v<100000,"Invalid per-snapshot alias allocator high-water")
            require(not samples or samples[-1]["time"]<now,
                    "CPAL tag timestamps not strictly increasing")
            samples.append({"time":now,"allocated":v,"alias":{}})
        elif kind=="C":
            require(samples and now==samples[-1]["time"] and 0<=who<SLOTS and v>0
                    and who<samples[-1]["allocated"],
                    "CPAL marker non-anonymous or outside timestamp/allocator")
            obj=samples[-1]["alias"]
            require(who not in obj,"Duplicate per-thread callback count")
            require(v>=last_seen.get(who,0),"CPAL callback per-TLS count regressed")
            last_seen[who]=v
            obj[who]=v
        else:raise ValueError("Unknown CPAL marker row kind")
    require(len(samples)>=15,"Too few true stage310 timestamp snapshots")
    return samples,hashlib.sha256(b).hexdigest()

def read_alsa_frames(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"ALSA source CSV not retained")
    b=p.read_bytes()
    rows=list(csv.reader(b.decode("ascii").splitlines()))
    header=["kind","monotonic_ns","anonymous_alias","operation",*KINDS]
    require(rows and rows[0]==header,"ALSA source schema changed")
    frames=[]
    previous={}
    for line in rows[1:]:
        require(len(line)==len(header),"Invalid ALSA source column count")
        kind,when,alias,op,*counts=line
        try:when=int(when);alias=int(alias);vals=[int(x) for x in counts]
        except ValueError as e:raise ValueError("ALSA source nonnumeric") from e
        require(0<when<2**64 and all(0<=n<2**64 for n in vals),
                "ALSA snapshot invalid uint64")
        if kind=="P":
            require(alias==-1 and op=="sample" and all(x==0 for x in vals[1:]),
                    "ALSA sampled P source corrupted")
            require(not frames or when>frames[-1]["time"],
                    "ALSA P source not strictly monotonic")
            frames.append({"time":when,"allocated":vals[0],"alias_op":{}})
        elif kind=="S":
            require(frames and when==frames[-1]["time"]
                    and 0<=alias<SLOTS and op in OPS
                    and vals[0]>0 and sum(vals[1:])<=vals[0],
                    "ALSA source operation/alias outside source")
            key=(alias,op)
            require(key not in frames[-1]["alias_op"],"Duplicate ALSA alias/op")
            require(vals[0]>=previous.get(key,0),"ALSA source call counter decreased")
            previous[key]=vals[0]
            frames[-1]["alias_op"][key]=dict(zip(KINDS,vals))
        else:raise ValueError("Invalid ALSA S/P source row type")
    require(len(frames)>=15,"Too few ALSA source snapshots")
    return frames,hashlib.sha256(b).hexdigest()

def source_window(alsa,tag,first,last):
    require(0<first<last,"Guest input timestamps invalid")
    a0=max((f for f in alsa if f["time"]<=first),key=lambda f:f["time"],default=None)
    a1=max((f for f in alsa if f["time"]<=last),key=lambda f:f["time"],default=None)
    t0=max((f for f in tag if f["time"]<=first),key=lambda f:f["time"],default=None)
    t1=max((f for f in tag if f["time"]<=last),key=lambda f:f["time"],default=None)
    require(all(x is not None for x in (a0,a1,t0,t1)),"No ALSA/tag bracketing snapshots")
    require(a0["time"]==t0["time"] and a1["time"]==t1["time"],
            "CPAL and ALSA identities not sampled by same observer")
    require(first-a0["time"]<1_000_000_000 and last-a1["time"]<1_000_000_000,
            "Source snapshots too distant from guest window")
    result=[]
    aliases=set(t0["alias"])|set(t1["alias"])|{
        x for (x,op) in a0["alias_op"]}|{x for (x,op) in a1["alias_op"]}
    for alias in sorted(aliases):
        before=t0["alias"].get(alias,0)
        after=t1["alias"].get(alias,0)
        require(after>=before,"Source CPAL per alias markers regressed")
        op_counts={}
        for op in OPS:
            old=a0["alias_op"].get((alias,op),{}).get("total",0)
            new=a1["alias_op"].get((alias,op),{}).get("total",0)
            require(new>=old,"ALSA per alias/source op count regressed")
            op_counts[op]=new-old
        result.append({
            "anonymous_tls_alias":alias,
            "real_tagged_cpal_callback_entry_delta":after-before,
            "alsa_export_total_deltas":op_counts,
            "tagged_cpal_and_alsa_writei_same_native_thread":
                after-before>0 and op_counts["writei"]>0,
            "tagged_cpal_and_other_exported_alsa_same_native_thread":
                after-before>0 and any(v>0 for v in op_counts.values()),
        })
    return {
        "sample_first_ns":a0["time"],
        "sample_last_ns":a1["time"],
        "snapshots_share_exact_same_monotonic_observer_ticks":True,
        "alias_allocations_at_last_source_marker":t1["allocated"],
        "guest_window_source_tagged_cpal_marker_increments":sum(
            x["real_tagged_cpal_callback_entry_delta"] for x in result),
        "matched_native_thread_aliases":result,
        "any_same_thread_cpal_marker_and_alsa_export":any(
            x["tagged_cpal_and_other_exported_alsa_same_native_thread"]
            for x in result),
        "any_same_thread_cpal_marker_and_alsa_writei":any(
            x["tagged_cpal_and_alsa_writei_same_native_thread"]
            for x in result),
        "zero_marker_does_not_prove_hook_resolution_or_no_backend_thread":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    manifest=json.loads((root/"stage310-host-source-sha-manifest.json").read_text())
    require(manifest["schema"]=="vh-map02-stage309-real-compiled-opt-in-cpal-alsa-tls-host/v1"
            and manifest["result"]==
               "STAGE309_EXPERIMENTAL_SAME_TLS_TAGGED_NEXIUM_LINUX_BINARY_COMPILED"
            and manifest["stage309_direct_cpal_alsa_tls_probe_function_compiled"] is True,
            "Actual separately compiled Stage309 host provenance not confirmed")
    host_hash=manifest["executable_sha256"]
    require(type(host_hash) is str and len(host_hash)==64
            and host_hash!="fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a",
            "New host ELF SHA must differ from historical Stage298 control")
    pair=json.loads((root/"stage310-actual-elf-nro-pair.json").read_text())
    require(pair["schema"]=="vh-map02-stage310-direct-tls-new-host-romfree-guest-pair/v1"
            and pair["experimental_stage309_host_sha256"]==host_hash
            and pair["unchanged_romfree_original_guest_sha256"]==NRO_SHA
            and pair["actual_run_id"]==run_id and pair["hint_ms"]==hint,
            "New tagged host and original guest source SHA pair disagree")
    shim=json.loads((root/"stage310-new-tagged-shim.json").read_text())
    require(shim["schema"]=="vh-map02-stage310-alsainterposer-v1"
            and shim["synthetic_two_thread_stage308_proof_rechecked"] is True
            and shim["native_tagged_host_and_alsa_share_same_shim"] is True,
            "Direct marker identity not proven by Stage308 synthetic source")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    cp=analyze_original_host_p_l(root/"host-cpal-lifetime-p.csv",
                                 root/"host-cpal-audioout-timeline.csv",first,last)
    require(cp==json.loads((root/"host-cpal-lifetime-audit.json").read_text()),
            "Real P/L CPAL marker evidence invalid")
    a,hash_a=read_alsa_frames(root/"alsa-userspace-anonymous-atomic.csv")
    t,hash_t=read_tag(root/"cpal-tag-anonymous-atomic.csv")
    require(len(a)==len(t) and all(x["time"]==y["time"] for x,y in zip(a,t)),
            "Direct same-TLS source samples not precisely paired")
    original=analyze_alsa(root/"alsa-userspace-anonymous-atomic.csv")
    require(original["original_sanitized_sha256"]==hash_a,
            "Original Stage305 ALSA parser rejected new guest")
    window=source_window(a,t,first,last)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE310_NEW_HOST_DIRECT_CPAL_ALSA_TLS_SNAPSHOT_REPARSED",
        "source_github_actions_run_id":run_id,
        "requested_pulse_latency_hint_ms":hint,
        "experimental_stage309_host_sha256":host_hash,
        "original_romfree_guest_nro_sha256":NRO_SHA,
        "stage308_compiled_shim_sha256":shim["shim_elf_sha256"],
        "source_alsa_CSV_sha256":hash_a,
        "source_cpal_tls_tag_CSV_sha256":hash_t,
        "host_original_cpal_p_reported_callback_entry_delta":
            cp["guest_window_original_l_cpal_entry_delta"],
        **window,
        "marker_and_alsa_export_same_alias_is_direct_source_thread_identity":True,
        "new_host_marker_is_opt_in_and_perturbs_callback_timing":True,
        "not_original_uninstrumented_Stage298_ELF":True,
        "same_thread_may_not_be_guest_generated_audio_pcm":True,
        "no_original_ps1_music_or_rom_used":True,
        "no_audio_root_cause_or_production_switch_sound_fix_proven":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    v=p.parse_args()
    try: result=audit(v.evidence,v.hint,v.run_id);rc=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            csv.Error,json.JSONDecodeError) as e:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_audio_root_cause_or_production_switch_sound_fix_proven":True}
        rc=1
    v.output.parent.mkdir(parents=True,exist_ok=True)
    v.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))
    return rc

if __name__=="__main__":raise SystemExit(main())
