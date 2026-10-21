#!/usr/bin/env python3
"""Stage316 source-replayed poll ordinal requested/returned event categories.

The original 2 pollfd *positions* are anonymous and cannot be resolved to FD
numbers or their kernel event producers. Category counters are cumulative,
relaxed and do not form a transactional snapshot. Only a source-proven Stage313
native CPAL TLS identity, reverified through Stage315, can be attributed.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from audit_map02_poll_arguments_stage315 import audit as previous_audit,parse as read_previous
from capture_map02_poll_events_stage316 import POLL_EVENT_FIELDS,POLL_EVENT_HEADER

SCHEMA="vh-map02-stage316-source-reparsed-cpal-poll-ordinal-event-categories/v1"
MAX_LINES=120000

def require(ok,why):
    if not ok:raise ValueError(why)

def read_source(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),"Original poll ordinal event source unavailable")
    data=p.read_bytes()
    require(100<len(data)<12_000_000,"Source poll ordinal events absent/oversized")
    try:r=csv.reader(data.decode("ascii").splitlines())
    except UnicodeError as e:raise ValueError("Poll ordinal source not ASCII") from e
    require(next(r,None)==list(POLL_EVENT_HEADER),"Poll ordinal source changed/leaks raw fd or TID")
    frames=[]
    previous={}
    for i,line in enumerate(r):
        require(i<MAX_LINES and len(line)==len(POLL_EVENT_HEADER),
                "Poll ordinal event source row width/length invalid")
        kind,tm,alias,*values=line
        try:tm=int(tm);alias=int(alias);v=tuple(int(x) for x in values)
        except ValueError as e:raise ValueError("Poll ordinal counters nonnumeric") from e
        require(0<tm<2**64 and all(0<=x<2**64 for x in v),
                "Poll ordinal unsigned source invalid")
        if kind=="P":
            require(alias==-1 and 0<=v[0]<=64 and not any(v[1:]),
                    "Poll ordinal sample count/marker invalid")
            require(not frames or tm>frames[-1]["time"],"Poll ordinal source timestamp regression")
            frames.append({"time":tm,"allocated":v[0],"alias":{}})
        elif kind=="M":
            require(frames and tm==frames[-1]["time"]
                    and 0<=alias<frames[-1]["allocated"],
                    "Poll ordinal metadata alias or sample timestamp invalid")
            require(alias not in frames[-1]["alias"],"Duplicated ordinal TLS alias snapshot")
            require(all(x>=y for x,y in zip(v,previous.get(alias,(0,)*len(v)))),
                    "Poll request or return ordinal counter decreased")
            previous[alias]=v
            frames[-1]["alias"][alias]=dict(zip(POLL_EVENT_FIELDS,v))
        else:raise ValueError("Unknown poll ordinal source row type")
    require(len(frames)>=15,"Poll ordinal source lacks real observation samples")
    return frames,hashlib.sha256(data).hexdigest()

def summarize(frames,first,last,cpal_aliases):
    require(0<first<last,"Invalid bounded guest input interval")
    a=max((i for i,s in enumerate(frames) if s["time"]<=first),default=None)
    b=max((i for i,s in enumerate(frames) if s["time"]<=last),default=None)
    require(a is not None and b is not None and b-a>=10
            and first-frames[a]["time"]<1_000_000_000
            and last-frames[b]["time"]<1_000_000_000,
            "True source poll event snapshots do not bracket guest input")
    seen=set(cpal_aliases)
    for frame in frames[a:b+1]:seen.update(frame["alias"])
    detail=[]
    for alias in sorted(seen):
        before=frames[a]["alias"].get(alias,{})
        after=frames[b]["alias"].get(alias,{})
        values={}
        for field in POLL_EVENT_FIELDS:
            o=before.get(field,0);n=after.get(field,0)
            require(n>=o,"Poll ordinal guest window counter regressed")
            values[field+"_guest_delta"]=n-o
        detail.append({
            "anonymous_same_process_native_TLS_alias":alias,
            "source_proven_preinput_CPAL_callback_thread":alias in cpal_aliases,
            **values,
            "two_ordinal_positions_are_not_linux_fd_numbers":True,
            "POLLIN_or_POLLOUT_count_may_coexist_in_one_return":True,
        })
    return {
        "guest_source_snapshot_count":b-a+1,
        "all_anonymous_tls_poll_event_categories":detail,
        "cpal_proven_native_thread_poll_event_categories":[x for x in detail
           if x["source_proven_preinput_CPAL_callback_thread"]],
        "requested_events_and_returned_revents_are_not_one_to_one":True,
        "no_descriptors_or_raw_masks_captured":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    prev=previous_audit(root,hint,run_id)
    require(prev["result"]==
            "REAL_STAGE315_SOURCE_VERIFIED_CPAL_POLL_TIMEOUT_RETURN_CLASSES",
            "Actual source-verifiable Stage315 CPAL poll parameter run unavailable")
    receipt=json.loads((root/"stage315-real-native-cpal-poll-arguments.json").read_text())
    require(receipt==prev,"Actual Stage315 prior receipt differs from raw source replay")
    fresh,sha=read_source(root/"poll-events-anonymous-atomic.csv")
    original,original_sha=read_previous(root/"poll-parameters-anonymous-atomic.csv")
    require(len(fresh)==len(original)
            and all(x["time"]==y["clock"] for x,y in zip(fresh,original)),
            "New poll ordinal events NOT sampled at previous source poll timestamps")
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    aliases={x["anonymous_native_TLS_alias"] for x in
             prev["source_proven_CPAL_poll_timeout_and_return_class"]
             if x["belongs_to_pre_input_proven_CPAL_callback_thread"]}
    result=summarize(fresh,first,last,aliases)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE316_NATIVE_CPAL_POLL_ORDINAL_EVENTS_SOURCE_REPARSED",
        "source_actions_run_id":run_id,
        "requested_pulse_hint_ms":hint,
        "stage309_experimental_host_ELF_sha256":
            prev["experimental_stage309_host_ELF_sha256"],
        "original_romfree_NRO_sha256":prev["original_romfree_NRO_sha256"],
        "actual_postinput_CPAL_callback_entries":
            prev["real_post_input_CPAL_callback_entries"],
        "stage315_source_poll_parameter_sha256":original_sha,
        "stage316_source_event_categories_sha256":sha,
        "source_matched_CPAL_native_thread_identity_verified":True,
        **result,
        "poll_nfds_other_than_exactly_two_not_captured":True,
        "userland_interceptor_adds_RT_read_of_pollfd_mask_and_perturbs_timing":True,
        "ready_category_does_not_prove_sender_eventfd_or_wakeup_loss":True,
        "no_original_game_ROM_music_or_switch_hardware_sound":True,
        "no_production_audio_root_cause_or_fix_proven":True,
    }

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--evidence",required=True,type=Path)
    a.add_argument("--hint",required=True,type=int)
    a.add_argument("--run-id",required=True,type=int)
    a.add_argument("--output",required=True,type=Path)
    x=a.parse_args()
    try:data=audit(x.evidence,x.hint,x.run_id);rc=0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,csv.Error,
            json.JSONDecodeError) as e:
        data={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
              "no_production_audio_root_cause_or_fix_proven":True}
        rc=1
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    print(json.dumps(data,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":raise SystemExit(main())
