#!/usr/bin/env python3
"""Stage312 source-replay /proc read-only scheduler observation for REAL tagged guests.

The source task sampler (Stage302) produces per-process sequential anonymous
task aliases. There is NO proven bridge between a /proc task alias and the
separate Stage308 CPAL/ALSA native TLS alias. Never claim this is a stack,
kernel futex owner, ALSA recovery cause or permanent deadlock.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from audit_map02_alsa_inflight_stage311 import audit as audit_stage311
from audit_map02_linux_task_state_stage302 import read_tasks

SCHEMA="vh-map02-stage312-genuine-linux-task-state-wait-bucket/v1"

def require(ok,reason):
    if not ok:raise ValueError(reason)

def summarize(rows,first,last):
    require(isinstance(first,int) and isinstance(last,int) and 0<first<last,
            "Original generated-only NRO guest time window invalid")
    guest=[x for x in rows if first<=x["clock"]<=last and x["alias"]>0]
    require(len({x["sample"] for x in guest})>=12,
            "Fewer than 12 real guest-window task observations")
    by_alias=defaultdict(list)
    for row in guest:
        by_alias[row["alias"]].append(row)
    report=[]
    all_states=Counter()
    waits=Counter()
    labels=Counter()
    for alias,seen in sorted(by_alias.items()):
        a,b=seen[0],seen[-1]
        require(b["ticks"]>=a["ticks"],"Per-task CPU tick source regression")
        for v in seen:
            all_states[v["state"]]+=1
            waits[v["wait"]]+=1
            labels[v["label"]]+=1
        longest={}
        for attr in ("state","wait"):
            value=None;length=0;best=0;bestvalue=None
            for entry in seen:
                current=entry[attr]
                if current==value:length+=1
                else:value=current;length=1
                if length>best:best=length;bestvalue=current
            longest[attr]={"sample_count":best,"value":bestvalue}
        report.append({
            "anonymous_proc_task_alias":alias,
            "thread_name_substring_only":a["label"],
            "samples_inside_guest":len(seen),
            "first_observation_clock_ns":a["clock"],
            "last_observation_clock_ns":b["clock"],
            "cpu_tick_difference_between_samples":b["ticks"]-a["ticks"],
            "states_in_observation_window":dict(sorted(Counter(x["state"] for x in seen).items())),
            "wait_buckets_in_observation_window":dict(sorted(Counter(x["wait"] for x in seen).items())),
            "longest_consecutive_same_state_samples":longest["state"],
            "longest_consecutive_same_wait_bucket_samples":longest["wait"],
            "last_observed_state":b["state"],
            "last_observed_wait_bucket":b["wait"],
            "source_only_coarse_sampling_not_kernel_stack":True,
        })
    return {
        "source_linux_task_samples_during_guest":len(guest),
        "source_distinct_anonymous_proc_task_aliases":len(report),
        "source_distinct_proc_sample_instants":len({x["sample"] for x in guest}),
        "task_aliases_showing_CPU_tick_growth":sum(
            v["cpu_tick_difference_between_samples"]>0 for v in report),
        "audio_name_hint_aliases":sum(
            v["thread_name_substring_only"]=="AUDIO_NAMED" for v in report),
        "audio_name_hint_aliases_showing_CPU_tick_growth":sum(
            v["thread_name_substring_only"]=="AUDIO_NAMED"
            and v["cpu_tick_difference_between_samples"]>0 for v in report),
        "guest_task_state_observations":dict(sorted(all_states.items())),
        "guest_sanitized_wait_bucket_observations":dict(sorted(waits.items())),
        "guest_task_name_hints":dict(sorted(labels.items())),
        "anonymous_proc_task_details":report[:128],
        "anonymous_proc_task_details_truncated":len(report)>128,
        "independent_proc_task_alias_not_same_as_CPAL_ALSA_TLS_alias":True,
        "task_name_substring_does_not_establish_CPAL_ownership":True,
        "stable_wait_category_not_permanent_deadlock_proof":True,
        "task_CPU_ticks_may_not_advance_during_finite_wait":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    prev=audit_stage311(root,hint,run_id)
    require(prev["result"]=="REAL_STAGE311_SOURCE_PINNED_NEW_HOST_ALSA_RETURN_PHASES_REPARSED",
            "Source-bounded Stage311 original guest and TLS phase evidence invalid")
    saved=json.loads((root/"stage311-real-alsa-entry-return-audit.json").read_text())
    require(prev==saved,"Existing source-reparsed Stage311 receipt changed")
    rows,times,sha=read_tasks(root/"linux-task-state-samples.csv")
    ready=int((root/"linux-task-monitor-ready-ns.txt").read_text().strip())
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    require(0<ready<=times[0]<first<last,
            "Task monitor not ready before original guest input")
    require(times[max(times)]>=last-1_000_000_000,
            "Task monitor did not observe end of original guest window")
    result=summarize(rows,first,last)
    require(prev["compiled_stage309_new_host_sha256"]==
            "e5ddfc61ac9435dc5a6e2dcd569766db0c444bbdeef8a3fa6a65c9c2e9fc6f25",
            "Actual Stage309 opt-in Linux NeXium ELF SHA mismatch")
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE312_TAGGED_GUEST_PROC_TASK_WAIT_BUCKETS_REPARSED",
        "real_actions_run_id":run_id,
        "hint_ms":hint,
        "source_task_csv_sha256":sha,
        "source_stage311_previous_receipt_sha256":hashlib.sha256(
            (root/"stage311-real-alsa-entry-return-audit.json").read_bytes()).hexdigest(),
        "host_stage309_compiled_experimental_ELF_sha256":
            prev["compiled_stage309_new_host_sha256"],
        "original_unchanged_ROM_free_guest_NRO_sha256":
            prev["generated_original_unchanged_nro_sha256"],
        "original_CPAL_P_L_guest_callback_count":
            prev["guest_original_cpal_P_L_callback_delta"],
        "original_same_TLS_CPAL_callback_mark_count":
            prev["guest_cpal_shared_TLS_callback_mark_delta"],
        "verified_native_CPAL_ALSA_TLS_aliases_are_not_proc_aliases":True,
        "observer_started_ns":ready,
        "source_first_task_observation_ns":times[0],
        "source_last_task_observation_ns":times[max(times)],
        "source_guest_first_input_ns":first,
        "source_guest_final_observation_ns":last,
        **result,
        "read_only_proc_sampling_can_perturb_scheduler_timing":True,
        "wchan_unavailable_or_zero_classified_UNKNOWN_not_failure":True,
        "no_kernel_wait_site_or_CPAL_scheduler_root_cause_proven":True,
        "no_original_PS1_music_ROM_or_physical_Switch_audio_used":True,
        "no_production_audio_fix_proven":True,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try: out=audit(a.evidence,a.hint,a.run_id);code=0
    except (ValueError,TypeError,KeyError,OSError,
            UnicodeError,json.JSONDecodeError) as e:
        out={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
             "no_production_audio_fix_proven":True};code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps(out,indent=2,sort_keys=True))
    return code

if __name__=="__main__":raise SystemExit(main())
