#!/usr/bin/env python3
"""Stage315 source-reparsed poll parameters on source-verified CPAL native thread.

No raw file descriptor, event mask, pollfd struct, stack or TID is captured.
Only last timeout (timeout_ms+1; 0=blocking -1, U64_MAX=invalid < -1),
capped nfds (0..64, 65=>greater), timeout-class entry counts and
return categories. Identifies proven native CPAL callback thread only after
independently re-auditing Stage314/313 same-process private TID join.
No assumption that missed wakeup, finite timeout or deadlock is causal.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_libc_wait_stage314 import audit as audit_stage314,read_libc
from capture_map02_poll_arguments_stage315 import POLL_META_FIELDS,POLL_META_HEADER

SCHEMA="vh-map02-stage315-source-reparsed-native-CPAL-poll-parameters/v1"
U64MAX=(1<<64)-1
MAX_SOURCE_ROWS=100000

def require(ok,reason):
    if not ok:raise ValueError(reason)

def parse(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"Stage315 source poll-args CSV absent")
    data=p.read_bytes()
    require(100<len(data)<10_000_000,"Stage315 source poll-args size outside bound")
    try:reader=csv.reader(data.decode("ascii").splitlines())
    except UnicodeError as e:raise ValueError("Stage315 source non-ASCII") from e
    require(next(reader,None)==list(POLL_META_HEADER),
            "Stage315 poll-args source schema wrong/private fields")
    frames=[]
    last={}
    for i,row in enumerate(reader):
        require(i<MAX_SOURCE_ROWS and len(row)==len(POLL_META_HEADER),
                "Poll-args source unexpected CSV row")
        k,ns,alias,*numbers=row
        try:clock=int(ns);who=int(alias);nums=tuple(int(n) for n in numbers)
        except ValueError as e:raise ValueError("Source poll args noninteger") from e
        require(0<clock<2**64 and all(0<=n<2**64 for n in nums),
                "Source poll argument counter not uint64")
        if k=="P":
            require(who==-1 and 0<=nums[0]<=64 and not any(nums[1:]),
                    "Invalid poll-args sample marker")
            require(not frames or clock>frames[-1]["clock"],
                    "Nonmonotonic poll-args source samples")
            frames.append({"clock":clock,"allocated":nums[0],"aliases":{}})
        elif k=="M":
            require(frames and clock==frames[-1]["clock"]
                    and 0<=who<frames[-1]["allocated"]
                    and nums[1]<=65,
                    "Metadata alias/bucket outside anonymized source snapshot")
            require(who not in frames[-1]["aliases"],
                    "Duplicate native TLS poll metadata row")
            previous=last.get(who,(0,)*len(POLL_META_FIELDS))
            require(all(nums[idx]>=previous[idx] for idx in range(2,len(nums))),
                    "Monotonic native poll argument/return count decreased")
            # Counts may be read between independent relaxed-atomic stores
            # during active poll, so no atomic transaction equality enforced.
            last[who]=nums
            frames[-1]["aliases"][who]=dict(zip(POLL_META_FIELDS,nums))
        else:raise ValueError("Invalid source poll arguments row tag")
    require(len(frames)>=15,"Insufficient original Stage315 200ms samples")
    return frames,hashlib.sha256(data).hexdigest()

def decode_timeout(v):
    if v==0:return {"kind":"infinite","timeout_ms":-1}
    if v==U64MAX:return {"kind":"invalid_negative","timeout_ms":None}
    require(1<=v<=2**31,"Poll timeout argument exceeded original signed int")
    return {"kind":"finite_or_immediate","timeout_ms":v-1}

def summarize(frames,first,last,cpal_aliases):
    require(0<first<last,"Original guest monotonic window invalid")
    a=max((i for i,x in enumerate(frames) if x["clock"]<=first),default=None)
    b=max((i for i,x in enumerate(frames) if x["clock"]<=last),default=None)
    require(a is not None and b is not None and b-a>=10,
            "Poll source not spanning 10+ guest samples")
    require(first-frames[a]["clock"]<1_000_000_000
            and last-frames[b]["clock"]<1_000_000_000,
            "Poll-args source markers too far from guest boundary")
    keys=sorted(set().union(*(set(f["aliases"]) for f in frames[a:b+1]))
                |set(cpal_aliases))
    reports=[]
    fields=POLL_META_FIELDS
    cumulative=fields[2:]
    for alias in keys:
        old=frames[a]["aliases"].get(alias,{})
        new=frames[b]["aliases"].get(alias,{})
        require(all(new.get(k,0)>=old.get(k,0) for k in cumulative),
                "Actual native TLS poll category count decreased in guest")
        delta={k:new.get(k,0)-old.get(k,0) for k in cumulative}
        reports.append({
            "anonymous_native_TLS_alias":alias,
            "belongs_to_pre_input_proven_CPAL_callback_thread":alias in cpal_aliases,
            "last_poll_timeout_class":decode_timeout(
                new.get("last_timeout_plus_one",0))["kind"],
            "last_poll_timeout_ms_or_null":decode_timeout(
                new.get("last_timeout_plus_one",0))["timeout_ms"],
            "last_poll_nfds_capped_65_means_more_than_64":new.get("last_nfds_capped",0),
            "poll_timeout_infinite_entries_delta":delta["timeout_infinite_entries"],
            "poll_timeout_immediate_entries_delta":delta["timeout_immediate_entries"],
            "poll_timeout_finite_entries_delta":delta["timeout_finite_entries"],
            "poll_timeout_invalid_negative_entries_delta":delta["timeout_invalid_negative_entries"],
            "poll_return_ready_count_delta":delta["returned_ready"],
            "poll_return_zero_count_delta":delta["returned_zero"],
            "poll_return_negative_count_delta":delta["returned_negative"],
            "pollfd_contents_or_file_descriptors_NEVER_captured":True,
        })
    cp=[x for x in reports if x["belongs_to_pre_input_proven_CPAL_callback_thread"]]
    return {
        "source_sample_count_in_guest":b-a+1,
        "source_proven_CPAL_poll_timeout_and_return_class":cp,
        "all_anonymous_native_poll_timeout_and_return_classes":reports,
        "timeout_requested_not_proof_of_actual_kernel_wakeup_cause":True,
        "poll_positive_return_does_not_reveal_POLLIN_POLLOUT_or_event_source":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    parent=audit_stage314(root,hint,run_id)
    require(parent["result"]==
            "REAL_STAGE314_AUTHENTIC_CPAL_LIBC_WAIT_PHASES_SOURCE_REPARSED",
            "Previous source-pinned actual native CPAL poll boundary audit failed")
    require(parent==json.loads(
            (root/"stage314-real-native-cpal-libc-wait-audit.json").read_text()),
            "Previous verified Stage314 receipt changed")
    raw,sha=parse(root/"poll-parameters-anonymous-atomic.csv")
    libc,libc_sha=read_libc(root/"libc-wait-anonymous-atomic.csv")
    require(len(raw)==len(libc) and all(x["clock"]==y["clock"] for x,y in zip(raw,libc)),
            "Same-source CPAL libc poll and parameter clocks must be identical")
    actual_cpal=parent["cpal_same_native_thread_libc_waits"]
    aliases={x["anonymous_native_TLS_alias"] for x in actual_cpal
             if x["belongs_to_pre_input_CPAL_callback_thread"]}
    result=summarize(raw,
                     parent["source_first_guest_window_snapshot_ns"],
                     parent["source_final_guest_window_snapshot_ns"],
                     aliases)
    # The source interval's absolute bounds are Stage314 source sample markers
    # rather than guessed clock times; Stage314 itself was independently
    # checked against true guest first-input/final markers.
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE315_SOURCE_VERIFIED_CPAL_POLL_TIMEOUT_RETURN_CLASSES",
        "real_actions_run_id":run_id,"hint_ms":hint,
        "experimental_stage309_host_ELF_sha256":parent["host_experimental_neXium_ELF_sha256"],
        "original_romfree_NRO_sha256":parent["original_romfree_nro_sha256"],
        "real_post_input_CPAL_callback_entries":parent["genuine_post_input_CPAL_callback_entries"],
        "source_poll_argument_metadata_sha256":sha,
        "source_stage314_libc_call_counters_sha256":libc_sha,
        "prior_source_verified_private_CPAL_task_join":True,
        **result,
        "LD_PRELOAD_new_argument_counters_can_perturb_poll_timing":True,
        "no_exact_event_fd_revent_mask_or_kernel_syscall_origin_traced":True,
        "no_lost_wakeup_backend_audio_root_cause_or_production_fix_proven":True,
        "original_game_ROM_music_or_Switch_DAC_used":False,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--hint",type=int,required=True)
    ap.add_argument("--run-id",type=int,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:record=audit(a.evidence,a.hint,a.run_id);rc=0
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,
            json.JSONDecodeError,csv.Error) as e:
        record={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
                "no_lost_wakeup_backend_audio_root_cause_or_production_fix_proven":True}
        rc=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    print(json.dumps(record,indent=2,sort_keys=True))
    return rc

if __name__=="__main__":raise SystemExit(main())
