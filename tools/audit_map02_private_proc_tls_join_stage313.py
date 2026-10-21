#!/usr/bin/env python3
"""Stage313 direct live private TID join, revalidating actual Stage312 /proc and CPAL.

Never output kernel TID or PID, thread names, native starttime, pointers or
private mmap. The anonymous /proc alias -> CPAL TLS alias relationship is
established ONLY through the Stage313 private mmap on the SAME live process.
A tagged callback before input does not prove that thread is required for
later callbacks, and an observed finite poll does NOT prove wakeup deadlock.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_proc_task_wait_stage312 import audit as audit_prior,read_tasks
from audit_map02_real_direct_tls_guests_stage310 import read_tag

SCHEMA="vh-map02-stage313-live-private-tid-same-native-task-join/v1"
HEADER=["sample","observed_ns","anonymous_proc_task_alias",
        "anonymous_tls_alias","cpal_tag_cumulative"]

def require(ok,why):
    if not ok:raise ValueError(why)

def parse_join(path,rows):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),
            "Private TID sanitized joined source unavailable")
    raw=p.read_bytes()
    require(100<len(raw)<5_000_000,"Joined source size absent/outside bounds")
    try:decoded=raw.decode("ascii")
    except UnicodeDecodeError as e:raise ValueError("Non-ASCII joined alias source") from e
    reader=csv.reader(decoded.splitlines())
    require(next(reader,None)==HEADER,
            "Raw native TID or wrong schema exposed in join output")
    expected={(r["sample"],r["clock"],r["alias"])
              for r in rows if r["alias"]>0}
    result=[]
    seen=set()
    lastmarks={}
    tls_to_proc={}
    for line in reader:
        require(len(result)<45000 and len(line)==5,"Unbounded or invalid join row")
        try:sample,clock,proc,tls,marks=map(int,line)
        except ValueError as e:raise ValueError("Bad numeric joined alias row") from e
        require((sample,clock,proc) in expected,
                "Join row not from source-verified /proc task sample")
        key=(sample,clock,proc)
        require(key not in seen,"Duplicate same source task join")
        seen.add(key)
        require(-1<=tls<64 and 0<=marks<2**64 and (tls>=0 or marks==0),
                "Invalid bounded anonymized TLS join and callback counter")
        if tls>=0:
            require(tls not in tls_to_proc or tls_to_proc[tls]==proc,
                    "Private TLS alias changed source /proc task ownership")
            tls_to_proc[tls]=proc
            require(marks>=lastmarks.get(tls,0),
                    "Live CPAL callback marker counter decreased")
            lastmarks[tls]=marks
        result.append({"sample":sample,"clock":clock,"proc":proc,
                       "tls":tls,"tag":marks})
    require(seen==expected,"Source /proc task rows not fully covered by sanitized join")
    require(len(result)>500,"Too few joined source-task observations")
    return result,hashlib.sha256(raw).hexdigest()

def analyze(join_rows,tasks,first,last,tag_sample):
    require(0<first<last,"Guest first-input/final monotonic markers invalid")
    indexed={(r["sample"],r["clock"],r["alias"]):r for r in tasks if r["alias"]>0}
    grouping=defaultdict(list)
    for j in join_rows:
        if j["tls"]<0:continue
        source=indexed[(j["sample"],j["clock"],j["proc"])]
        grouping[j["tls"]].append((j,source))
    require(grouping,"No stage313 live private TLS -> /proc join ever observed")
    itemized=[]
    callback_candidates=[]
    for tls,paired in sorted(grouping.items()):
        before=[(j,p) for j,p in paired if j["clock"]<first]
        inside=[(j,p) for j,p in paired if first<=j["clock"]<=last]
        marker_pre=max((j["tag"] for j,p in before),default=0)
        marker_at_end=max((j["tag"] for j,p in inside),default=marker_pre)
        require(marker_at_end>=marker_pre,
                "Callback marker regressed across source guest interval")
        # These are different 250ms /proc vs 200ms callback snapshots.
        # Only compare a sample with the latest later callback sample,
        # allowing bounded observer skew but NOT requiring identical counts.
        candidates=[v for v in tag_sample if v["time"]>=paired[0][0]["clock"]]
        if candidates:
            value=candidates[0]["alias"].get(tls,0)
            require(paired[0][0]["tag"]<=value,
                    "Private joined callback marker exceeds later audited source marker")
        c=Counter(p["state"] for j,p in inside)
        w=Counter(p["wait"] for j,p in inside)
        seen_proc={j["proc"] for j,p in paired}
        require(len(seen_proc)==1,"TLS alias joined to multiple native task aliases")
        rec={
            "anonymous_tls_alias":tls,
            "anonymous_proc_task_alias":next(iter(seen_proc)),
            "total_proven_native_task_join_samples":len(paired),
            "samples_before_guest_input":len(before),
            "samples_within_guest_window":len(inside),
            "CPAL_callback_mark_pre_input_positive":marker_pre>0,
            "CPAL_callback_cumulative_before_input":marker_pre,
            "CPAL_callback_cumulative_last_inside":marker_at_end,
            "CPAL_callback_tag_growth_inside_observed_window":
                marker_at_end-marker_pre,
            "guest_source_task_CPU_tick_change":
                inside[-1][1]["ticks"]-inside[0][1]["ticks"]
                if len(inside)>=2 else 0,
            "guest_source_task_state_counts":dict(sorted(c.items())),
            "guest_source_wait_buckets":dict(sorted(w.items())),
            "guest_last_wait_category":inside[-1][1]["wait"] if inside else None,
            "guest_last_state":inside[-1][1]["state"] if inside else None,
            "task_audio_named_substring_only":
                (paired[0][1]["label"]=="AUDIO_NAMED"),
            "join_is_direct_native_task_identity_only_for_this_process":True,
        }
        require(rec["guest_source_task_CPU_tick_change"]>=0,
                "Verified native proc task CPU tick regression")
        itemized.append(rec)
        if marker_pre>0:callback_candidates.append(rec)
    return {
        "direct_same_process_source_join_count":len(itemized),
        "source_cpal_tagged_pre_input_task_count":len(callback_candidates),
        "cpal_tagged_pre_input_native_task_wait_evidence":callback_candidates,
        "all_joined_tls_to_proc_source_tasks":itemized,
        "tagged_21ms_callback_once_does_not_prove_future_deadlock":True,
        "future_callback_not_invoked_cannot_prove_wakeup_expectation":True,
        "multiple_unattributed_threads_may_exist":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    baseline=audit_prior(root,hint,run_id)
    require(baseline["result"]==
            "REAL_STAGE312_TAGGED_GUEST_PROC_TASK_WAIT_BUCKETS_REPARSED",
            "Stage312 source-replay guest/proc baseline invalid")
    require(baseline==json.loads(
            (root/"stage312-linux-task-wait-source-audit.json").read_text()),
            "Stage312 saved source receipt differs from independently reparsed")
    tasks,times,_=read_tasks(root/"linux-task-state-samples.csv")
    join,digest=parse_join(root/"linux-task-private-tls-join-anonymous.csv",tasks)
    tags,tag_sha=read_tag(root/"cpal-tag-anonymous-atomic.csv")
    first=baseline["source_guest_first_input_ns"]
    last=baseline["source_guest_final_observation_ns"]
    result=analyze(join,tasks,first,last,tags)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE313_TAGGED_CPAL_TO_LINUX_TASK_PRIVATE_JOIN_REPARSED",
        "actual_CI_run_id":run_id,
        "requested_pulse_hint_ms":hint,
        "original_source_pinned_guest_NRO_sha256":
            baseline["original_unchanged_ROM_free_guest_NRO_sha256"],
        "exact_stage309_experimental_host_ELF_sha256":
            baseline["host_stage309_compiled_experimental_ELF_sha256"],
        "actual_stage312_original_guest_CPAL_callback_delta":
            baseline["original_CPAL_P_L_guest_callback_count"],
        "actual_stage312_original_CPAL_TLScallback_delta":
            baseline["original_same_TLS_CPAL_callback_mark_count"],
        "guest_first_input_monotonic_ns":first,
        "guest_last_observation_monotonic_ns":last,
        "source_private_anonymized_proc_TLS_join_csv_sha256":digest,
        "original_source_verified_CPAL_tag_csv_sha256":tag_sha,
        **result,
        "private_native_TID_never_uploaded":True,
        "both_anonymous_alias_namespaces_are_joined_only_within_live_process":True,
        "one_gettid_syscall_on_first_TLS_alias_allocation_may_perturb_RT_thread":True,
        "absence_of_callback_may_not_be_sleep_deadlock":True,
        "not_uninstrumented_Stage298_or_Nintendo_Switch_speaker_output":True,
        "no_original_PS1_game_ROM_or_music":True,
        "no_audio_root_cause_or_production_fix_proven":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True,type=Path)
    p.add_argument("--hint",required=True,type=int)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:record=audit(a.evidence,a.hint,a.run_id);rc=0
    except (ValueError,TypeError,KeyError,OSError,
            UnicodeError,json.JSONDecodeError,csv.Error) as e:
        record={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_audio_root_cause_or_production_fix_proven":True}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")
    print(json.dumps(record,sort_keys=True,indent=2))
    return rc
if __name__=="__main__":raise SystemExit(main())
