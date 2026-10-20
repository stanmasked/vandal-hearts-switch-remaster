#!/usr/bin/env python3
"""Stage302 verify real Linux /proc NeXium TASK sampling against Stage301 P/L.

Only coarse user-visible anonymous task aliases, coarse Linux scheduler state,
cumulative tick counts and a whitelist of wait-channel *categories* can be
validated. A thread whose name contains 'audio'/'cpal'/'alsa' is NOT necessarily
the owned CPAL callback or ALSA hardware thread. No stack traces or root cause.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_pulse_event_clocks_stage301 import audit as audit_prior
from capture_map02_linux_task_samples_stage302 import BUCKETS, STATES

SCHEMA="vh-map02-stage302-real-neXium-linux-proc-tasks/v1"
ALLOWED_WAITS=set(BUCKETS)|{"OTHER","UNKNOWN"}
LABELS={"AUDIO_NAMED","UNATTRIBUTED"}

def require(cond,reason):
    if not cond:raise ValueError(reason)

def read_tasks(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"Actual Linux proc sampler CSV unavailable")
    raw=p.read_bytes()
    require(400<=len(raw)<=8_000_000,"Sampler CSV missing or exceeds limit")
    try:
        text=raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Expected anonymized ASCII proc sampler file") from exc
    reader=csv.DictReader(text.splitlines())
    required=["sample","observed_ns","task_alias","name_hint",
              "linux_state","cpu_ticks","wait_bucket"]
    require(reader.fieldnames==required,"Anonymized proc task row schema changed")
    rows=[]
    last_sample=-1
    stamps={}
    aliases={}
    seen=set()
    sample_counts=Counter()
    for row in reader:
        require(len(rows)<45_000,"Unbounded proc task sample records")
        try:
            sample=int(row["sample"]);clock=int(row["observed_ns"])
            alias=int(row["task_alias"]);ticks=int(row["cpu_ticks"])
        except (ValueError,KeyError,TypeError) as e:
            raise ValueError("Invalid proc task numeric field") from e
        require(0<=sample<220 and 0<clock<2**64 and 0<=alias<65_536
                and 0<=ticks<2**64,
                "Invalid bounded Linux task sample")
        require(sample>=last_sample,"Proc sample index decreased")
        last_sample=sample
        if sample in stamps:
            require(stamps[sample]==clock,"Same sample has inconsistent observed clock")
        else:
            stamps[sample]=clock
            if sample>0:
                require(sample-1 in stamps and stamps[sample-1]<clock
                        and clock-stamps[sample-1]<=2_000_000_000,
                        "Proc samples missing/out of bounded monotonic order")
        if row["name_hint"]=="NO_TASKS":
            require(alias==0 and ticks==0 and row["linux_state"]=="X"
                    and row["wait_bucket"]=="UNKNOWN" and sample_counts[sample]==0,
                    "Malformed guest-exit sentinel")
            seen.add((sample,0))
        else:
            require(alias>0 and row["name_hint"] in LABELS,
                    "Sampler leaked actual Linux process/thread names or alias")
            require(row["linux_state"] in STATES,
                    "Unexpected Linux task state")
            require(row["wait_bucket"] in ALLOWED_WAITS,
                    "Unexpected raw Linux wait-channel name")
            require((sample,alias) not in seen,"Duplicate task in one sampled instant")
            seen.add((sample,alias))
            sample_counts[sample]+=1
            old=aliases.get(alias)
            if old:
                require(old["cpu_ticks"]<=ticks,"Linux task CPU tick count decreased")
                require(old["name_hint"]==row["name_hint"],
                        "Task alias changed anonymized identity")
            aliases[alias]={"cpu_ticks":ticks,"name_hint":row["name_hint"]}
        rows.append({"sample":sample,"clock":clock,"alias":alias,"ticks":ticks,
                     "state":row["linux_state"],"label":row["name_hint"],
                     "wait":row["wait_bucket"]})
    require(len(stamps)>=12,"Real guest process has too few task observations")
    require(sum(sample_counts.values())>=25,"No actual threads observed")
    return rows,stamps,hashlib.sha256(raw).hexdigest()

def audit(root,hint,run_id):
    root=Path(root)
    prior=audit_prior(root,hint,run_id)
    require(prior["result"]=="REAL_STAGE301_GUEST_CPAL_PULSE_RECEIPT_CLOCKS_REPARSED",
            "Stage301 exact ELF/P/L/optical/PCM proofs absent")
    saved=json.loads((root/"stage301-pulse-subscribe-verified.json").read_text())
    require(prior==saved,"Stage301 re-parsed guest proof mismatch")
    csvrows,stamps,digest=read_tasks(root/"linux-task-state-samples.csv")
    ready=(root/"linux-task-monitor-ready-ns.txt").read_text().strip()
    try: ready=int(ready)
    except ValueError as e:raise ValueError("Bad proc observer readiness marker") from e
    first=prior["guest_first_input_monotonic_ns"]
    last=prior["guest_last_observation_monotonic_ns"]
    require(0<ready<=stamps[0]<first<last
            and stamps[max(stamps)]>=last-1_000_000_000,
            "Proc sampler did not cover actual guest interactive interval")
    window=[r for r in csvrows if first<=r["clock"]<=last and r["alias"]>0]
    require(len({r["sample"] for r in window})>=10,
            "Fewer than 10 genuine guest-window Linux task observations")
    counts=Counter(r["state"] for r in window)
    hints=Counter(r["label"] for r in window)
    waits=Counter(r["wait"] for r in window)
    per_task=defaultdict(list)
    for r in window:
        per_task[r["alias"]].append(r)
    deltas=[]
    for alias,seen in per_task.items():
        a,b=seen[0],seen[-1]
        require(b["ticks"]>=a["ticks"],"Guest task CPU tick regression")
        deltas.append({
            "anonymous_alias":alias,
            "name_hint":a["label"],
            "guest_window_cpu_tick_delta_sampled":b["ticks"]-a["ticks"],
            "guest_window_sampled_at_least_twice":len(seen)>=2,
            "guest_window_number_of_samples":len(seen),
            "first_seen_wait_bucket":a["wait"],
            "last_seen_wait_bucket":b["wait"],
            "first_seen_linux_state":a["state"],
            "last_seen_linux_state":b["state"],
        })
    named=[x for x in deltas if x["name_hint"]=="AUDIO_NAMED"]
    cpu_active=sum(x["guest_window_cpu_tick_delta_sampled"]>0
                   and x["guest_window_sampled_at_least_twice"]
                   for x in deltas)
    named_cpu_active=sum(x["guest_window_cpu_tick_delta_sampled"]>0
                         and x["guest_window_sampled_at_least_twice"]
                         for x in named)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE302_NEXIUM_PROC_THREAD_SAMPLES_SOURCE_REPARSED",
        "hint_ms":hint,
        "actual_actions_run_id":run_id,
        "exact_compiled_nexium_elf_sha256":prior["exact_compiled_neXium_elf_sha256"],
        "exact_research_nro_sha256":prior["exact_generated_research_nro_sha256"],
        "original_stage301_receipt_sha256":hashlib.sha256(
            (root/"stage301-pulse-subscribe-verified.json").read_bytes()).hexdigest(),
        "anonymized_proc_csv_sha256":digest,
        "independent_real_stage301_proof_reparsed":True,
        "number_of_sample_instant_timestamps":len(stamps),
        "first_task_sample_monotonic_ns":stamps[0],
        "last_task_sample_monotonic_ns":stamps[max(stamps)],
        "monotonic_guest_input_ns":first,
        "monotonic_guest_final_ns":last,
        "task_rows_during_guest":len(window),
        "distinct_anonymous_task_aliases_during_guest":len(deltas),
        "task_aliases_with_sampled_CPU_tick_growth":cpu_active,
        "task_aliases_named_like_audio_alsa_or_cpal":len(named),
        "audio_like_aliases_with_sampled_CPU_tick_growth":named_cpu_active,
        "linux_task_states_during_guest":dict(sorted(counts.items())),
        "sanitized_wait_buckets_during_guest":dict(sorted(waits.items())),
        "anonymized_name_hints_during_guest":dict(sorted(hints.items())),
        "sampled_anonymous_task_summaries":deltas[:128],
        "task_summaries_truncated":len(deltas)>128,
        "source_guest_CPAL_entry_delta":
            prior["host_guest_window_cpal_callback_entries"],
        "source_guest_8_page_optical_crc_verified":
            prior["guest_final_8_page_crc_verified"],
        "source_virtual_PCM_nonzero_samples":prior["virtual_pcm_nonzero_samples"],
        "OS_task_name_hint_does_not_establish_CPAL_thread_identity":True,
        "OS_wait_bucket_is_not_a_stack_trace_or_backend_failure_proof":True,
        "absence_of_task_cpu_ticks_does_not_prove_deadlock":True,
        "read_only_observer_may_perturb_scheduler_timing":True,
        "no_ALSA_root_cause_or_Nintendo_Switch_DAC_proven":True,
        "original_PS1_audio_or_game_ROM_used":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--hint",type=int,required=True)
    p.add_argument("--run-id",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        result=audit(a.evidence,a.hint,a.run_id);code=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as e:
        result={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_ALSA_root_cause_or_Nintendo_Switch_DAC_proven":True}
        code=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print(json.dumps(result,sort_keys=True,indent=2))
    return code

if __name__=="__main__":
    raise SystemExit(main())
