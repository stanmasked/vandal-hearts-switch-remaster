#!/usr/bin/env python3
"""Stage314 same-process libc poll enter/return evidence for native-tagged CPAL.

Replays REAL Stage313 exact ELF/NRO + private native-TID-to-/proc source before
reading new 200ms cumulative wait phases. Only exported poll(), ppoll(),
epoll_wait(), epoll_pwait() are intercepted, not direct kernel syscalls,
internal glibc calls, CPAL wakeup contracts, or eventfd semantics.
No call duration or permanent deadlock is provable from bounded snapshots.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_private_proc_tls_join_stage313 import audit as audit_stage313
from audit_map02_alsa_inflight_stage311 import parse as parse_alsa_phase
from audit_map02_real_direct_tls_guests_stage310 import read_tag
from capture_map02_libc_wait_stage314 import LIBC_WAIT_NAMES,LIBC_WAIT_HEADER

SCHEMA="vh-map02-stage314-real-native-cpal-libc-poll-boundary/v1"
MAX_SOURCE_ROWS=100000

def require(ok,reason):
    if not ok:raise ValueError(reason)

def read_libc(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),
            "True original source poll/ppoll/epoll wait CSV absent")
    data=path.read_bytes()
    require(100<len(data)<12_000_000,"Stage314 bounded libc source missing/oversized")
    try: reader=csv.reader(data.decode("ascii").splitlines())
    except UnicodeError as e:raise ValueError("Libc wait source is not ASCII") from e
    require(next(reader,None)==list(LIBC_WAIT_HEADER),
            "Unknown poll source columns / potential private TID disclosure")
    samples=[]
    last={}
    for i,row in enumerate(reader):
        require(i<MAX_SOURCE_ROWS and len(row)==7,
                "Unexpected or unbounded poll phase row width")
        kind,ns,alias,op,*counts=row
        try:
            ns=int(ns);alias=int(alias)
            counts=tuple(int(x) for x in counts)
        except ValueError as e:raise ValueError("Libc wait source counter is nonnumeric") from e
        require(0<ns<2**64 and all(0<=v<2**64 for v in counts),
                "Invalid bounded relaxed atomic wait counts")
        if kind=="P":
            require(alias==-1 and op=="sample" and counts[1:]==(0,0)
                    and 0<=counts[0]<=64,
                    "Malformed libc P sample source")
            require(not samples or ns>samples[-1]["clock"],
                    "Nonmonotonic libc P source timestamps")
            samples.append({"clock":ns,"allocated":counts[0],"ops":{}})
        elif kind=="B":
            require(samples and ns==samples[-1]["clock"]
                    and 0<=alias<samples[-1]["allocated"]
                    and op in LIBC_WAIT_NAMES and counts[0]>0,
                    "Libc B row outside native sampled alias or known exports")
            key=(alias,op)
            require(key not in samples[-1]["ops"],"Duplicate libc phase row in a sample")
            prior=last.get(key,(0,0,0))
            require(all(x>=y for x,y in zip(counts,prior)),
                    "Libc poll entry/return/error source counter decreased")
            last[key]=counts
            samples[-1]["ops"][key]=counts
        else:raise ValueError("Unknown libc phase sample row tag")
    require(len(samples)>=15,"Missing real 200ms libc observation window")
    return samples,hashlib.sha256(data).hexdigest()

def summarize(frames,first,last,auth_cpal_aliases):
    require(0<first<last,"Invalid actual guest clock interval")
    start=max((i for i,f in enumerate(frames) if f["clock"]<=first),default=None)
    end=max((i for i,f in enumerate(frames) if f["clock"]<=last),default=None)
    require(start is not None and end is not None and end-start>=10,
            "Too few real libc snapshots spanning generated guest input")
    require(first-frames[start]["clock"]<1_000_000_000
            and last-frames[end]["clock"]<1_000_000_000,
            "Libc wait snapshots too far from guest markers")
    window=frames[start:end+1]
    observed={(alias,op) for f in window for alias,op in f["ops"]}
    observed.update((alias,op) for alias in auth_cpal_aliases
                    for op in LIBC_WAIT_NAMES)
    rows=[]
    for alias,op in sorted(observed):
        begin=window[0]["ops"].get((alias,op),(0,0,0))
        finish=window[-1]["ops"].get((alias,op),(0,0,0))
        require(all(a>=b for a,b in zip(finish,begin)),
                "Libc source counter regressed during exact guest markers")
        points=[f["ops"].get((alias,op),(0,0,0)) for f in window]
        pending=[max(0,x[0]-x[1]) for x in points]
        rows.append({
            "anonymous_native_TLS_alias":alias,
            "intercepted_libc_export":op,
            "belongs_to_pre_input_CPAL_callback_thread":alias in auth_cpal_aliases,
            "entry_count_delta":finish[0]-begin[0],
            "return_count_delta":finish[1]-begin[1],
            "negative_return_count_delta":finish[2]-begin[2],
            "sample_instants_with_ongoing_entry":sum(p>0 for p in pending),
            "max_sampled_ongoing_calls":max(pending),
            "pending_calls_at_guest_last_observation":pending[-1],
            "entry_counter_before_input":begin[0],
            "return_counter_before_input":begin[1],
            "entry_counter_at_last":finish[0],
            "return_counter_at_last":finish[1],
            "exact_block_duration_NOT_observed":True,
        })
    cp=[x for x in rows if x["belongs_to_pre_input_CPAL_callback_thread"]]
    return {
        "matched_libc_source_sample_timestamps":len(window),
        "source_first_guest_window_snapshot_ns":window[0]["clock"],
        "source_final_guest_window_snapshot_ns":window[-1]["clock"],
        "cpal_same_native_thread_libc_waits":cp,
        "all_anonymous_TLS_libc_waits":rows,
        "CPAL_thread_libc_export_entries_observed":sum(x["entry_count_delta"] for x in cp),
        "CPAL_thread_libc_export_returns_observed":sum(x["return_count_delta"] for x in cp),
        "CPAL_thread_outstanding_libc_calls_at_last_sample":sum(
            x["pending_calls_at_guest_last_observation"] for x in cp),
        "CPAL_pre_input_callback_thread_identity_must_be_source_proven":True,
        "no_periodic_poll_sample_can_establish_exact_kernel_block_duration":True,
        "absence_of_intercepted_libc_calls_may_mean_direct_syscalls_or_unobserved_paths":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    baseline=audit_stage313(root,hint,run_id)
    require(baseline["result"]==
            "REAL_STAGE313_TAGGED_CPAL_TO_LINUX_TASK_PRIVATE_JOIN_REPARSED",
            "Exact true Stage313 private TID native thread join source rejected")
    require(baseline==json.loads(
            (root/"stage313-private-proc-cpal-TLS-audit.json").read_text()),
            "Stage313 prior source reverified result mismatched")
    raw,sha=read_libc(root/"libc-wait-anonymous-atomic.csv")
    tags,tag_sha=read_tag(root/"cpal-tag-anonymous-atomic.csv")
    # True Stage311 ALSA phases share precisely the same monotonic sampler.
    alsa,alsa_sha=parse_alsa_phase(root/"alsa-inflight-anonymous-atomic.csv")
    require(len(raw)==len(tags)==len(alsa),
            "Poll/CPAL/ALSA 200ms sample counts differ")
    require(all(x["clock"]==y["time"]==z["time"]
                for x,y,z in zip(raw,tags,alsa)),
            "Poll and genuine native CPAL TLS source snapshots not simultaneous")
    cp=baseline["cpal_tagged_pre_input_native_task_wait_evidence"]
    aliases={row["anonymous_tls_alias"] for row in cp
             if row["CPAL_callback_mark_pre_input_positive"]}
    result=summarize(raw,baseline["guest_first_input_monotonic_ns"],
                     baseline["guest_last_observation_monotonic_ns"],aliases)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE314_AUTHENTIC_CPAL_LIBC_WAIT_PHASES_SOURCE_REPARSED",
        "real_actions_run_id":run_id,
        "hint_ms":hint,
        "host_experimental_neXium_ELF_sha256":
            baseline["exact_stage309_experimental_host_ELF_sha256"],
        "original_romfree_nro_sha256":
            baseline["original_source_pinned_guest_NRO_sha256"],
        "genuine_post_input_CPAL_callback_entries":
            baseline["actual_stage312_original_guest_CPAL_callback_delta"],
        "pre_input_tagged_native_CPAL_task_count":
            baseline["source_cpal_tagged_pre_input_task_count"],
        "private_native_tid_to_proven_tls_alias_join_source_verified":True,
        "stage313_previous_anonymized_join_sha256":
            baseline["source_private_anonymized_proc_TLS_join_csv_sha256"],
        "libc_poll_200ms_source_sha256":sha,
        "cpal_tag_source_sha256":tag_sha,
        "alsa_export_phase_source_sha256":alsa_sha,
        **result,
        "research_LD_PRELOAD_instruments_libc_and_changes_scheduler_timing":True,
        "experimental_first_thread_callback_SYS_gettid_remains_intrusive":True,
        "unobserved_direct_kernel_syscall_paths_not_covered":True,
        "snapshot_of_unreturned_call_is_not_a_permanent_deadlock":True,
        "no_audio_wakeup_root_cause_or_production_fix_proven":True,
        "original_Vandal_Hearts_ROM_music_or_physical_Switch_DAC_used":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try: data=audit(args.evidence,args.hint,args.run_id);rc=0
    except (ValueError,KeyError,TypeError,OSError,
            UnicodeError,json.JSONDecodeError,csv.Error) as e:
        data={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
              "no_audio_wakeup_root_cause_or_production_fix_proven":True}
        rc=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":raise SystemExit(main())
