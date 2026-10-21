#!/usr/bin/env python3
"""Stage311 source-reparsed optional userspace ALSA enter/return phase counters.

The 13 exported functions are observed through an intrusive LD_PRELOAD shim.
Counts are relaxed atomic samples every ~200ms; a temporarily in-flight call
is NOT evidence of a permanent deadlock. No native Linux TID / PID / PCM is
recorded. Stage310's exact new ELF/NRO/CPAL/ALSA provenance audit is required.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_real_direct_tls_guests_stage310 import audit as previous
from capture_map02_alsa_inflight_stage311 import PHASE_OPS,PHASE_HEADER
from capture_map02_alsa_userspace_stage305 import SLOTS

SCHEMA="vh-map02-stage311-source-reparsed-alsa-user-entry-return-phases/v1"
MAX_ROW_COUNT=200000

def require(test,msg):
    if not test: raise ValueError(msg)

def parse(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),
            "Actual Stage311 source ALSA phase data missing")
    raw=p.read_bytes()
    require(100<len(raw)<=15_000_000,"ALSA phase source size outside bounds")
    try: rows=csv.reader(raw.decode("ascii").splitlines())
    except UnicodeDecodeError as e:raise ValueError("Stage311 phase source not ASCII") from e
    require(next(rows,None)==list(PHASE_HEADER),"Actual ALSA phase CSV schema invalid")
    frames=[]
    observed_last={}
    for no,line in enumerate(rows):
        require(no<MAX_ROW_COUNT,"Too many ALSA phase source lines")
        require(len(line)==len(PHASE_HEADER),"Unexpected phase source row width")
        kind,ns,alias,op,*values=line
        try: when=int(ns);who=int(alias);counts=tuple(int(n) for n in values)
        except ValueError as e:raise ValueError("Noninteger phase source counter") from e
        require(0<when<2**64 and all(0<=v<2**64 for v in counts),
                "Unbounded or negative source ALSA phase counters")
        if kind=="P":
            require(who==-1 and op=="sample" and counts[1:]==(0,0)
                    and 0<=counts[0]<100000,
                    "Malformed Stage311 observation P sample marker")
            require(not frames or when>frames[-1]["time"],
                    "ALSA P phase snapshots not monotonic")
            frames.append({"time":when,"allocated":counts[0],"ops":{}})
        elif kind=="B":
            require(frames and when==frames[-1]["time"]
                    and 0<=who<SLOTS and who<frames[-1]["allocated"]
                    and op in PHASE_OPS,
                    "Phase row not covered by source sampling clock/alias")
            key=(who,op)
            require(key not in frames[-1]["ops"],"Duplicate phase alias/op in source tick")
            require(counts[0]>0,"Phase row claimed nonempty but begin count is zero")
            older=observed_last.get(key,(0,0,0))
            require(all(now>=old for now,old in zip(counts,older)),
                    "Real ALSA per-alias entry/return phase counter decreased")
            observed_last[key]=counts
            # With independent relaxed atomics, read begin/return/neg at
            # different instants. Do not assert instantaneous phase ordering.
            frames[-1]["ops"][key]=counts
        else:raise ValueError("Unknown phase source tag")
    require(len(frames)>=15,"Too few real Stage311 200ms phase snapshots")
    return frames,hashlib.sha256(raw).hexdigest()

def guest_window(frames,first,last,source_aliases):
    require(type(first) is int and type(last) is int and 0<first<last,
            "Original NeXium guest window invalid")
    before=max((i for i,x in enumerate(frames) if x["time"]<=first),default=None)
    after=max((i for i,x in enumerate(frames) if x["time"]<=last),default=None)
    require(before is not None and after is not None and after>before,
            "Source phases do not cover guest input and observation")
    require(first-frames[before]["time"]<1_000_000_000
            and last-frames[after]["time"]<1_000_000_000,
            "Stage311 user ALSA phase sample too far from guest boundary")
    ops=sorted({key for frame in frames[before:after+1]
                for key in frame["ops"]})
    result=[]
    for alias,op in ops:
        old=frames[before]["ops"].get((alias,op),(0,0,0))
        new=frames[after]["ops"].get((alias,op),(0,0,0))
        require(all(a>=b for a,b in zip(new,old)),
                "Guest-window userspace ALSA begin/return counters regressed")
        points=[frame["ops"].get((alias,op),(0,0,0))
                for frame in frames[before:after+1]]
        # A begin may have no corresponding return at one particular source
        # snapshot, even during normal ALSA polling; only describe sampling.
        outstanding=[max(0,entered-left) for entered,left,negative in points]
        result.append({
            "anonymous_tls_alias":alias,"exported_alsa_function":op,
            "has_cpal_marker_in_same_tls_guest_window":alias in source_aliases,
            "source_window_begun_delta":new[0]-old[0],
            "source_window_returned_delta":new[1]-old[1],
            "source_window_negative_return_delta":new[2]-old[2],
            "observed_snapshots_with_unreturned_calls":sum(1 for n in outstanding if n>0),
            "maximum_sampled_unreturned_calls":max(outstanding),
            "last_sampled_unreturned_calls":outstanding[-1],
            "per_function_exact_duration_not_measured":True,
        })
    return {
        "first_source_snapshot_ns":frames[before]["time"],
        "last_source_snapshot_ns":frames[after]["time"],
        "sample_instants_in_guest_interval":after-before+1,
        "per_tls_alias_and_function":result,
        "attribution_to_cpal_requires_actual_positive_callback_marker":True,
        "sampled_in_flight_never_equates_to_permanent_thread_deadlock":True,
        "extra_alsa_export_symbol_calls_may_be_bypassed_by_dynamic_dispatch":True,
    }

def audit(root,hint,run_id):
    root=Path(root)
    prior=previous(root,hint,run_id)
    require(prior["result"]=="REAL_STAGE310_NEW_HOST_DIRECT_CPAL_ALSA_TLS_SNAPSHOT_REPARSED"
            and prior["source_github_actions_run_id"]==run_id,
            "Existing source-pinned Stage310 instrumented guest not reverified")
    original=json.loads((root/"stage310-direct-tls-guest-audit.json").read_text())
    require(original==prior,"Original Stage310 direct same-thread audit changed")
    source,rawsha=parse(root/"alsa-inflight-anonymous-atomic.csv")
    from audit_map02_real_direct_tls_guests_stage310 import read_tag
    tags,sha=read_tag(root/"cpal-tag-anonymous-atomic.csv")
    require(len(source)==len(tags)
            and all(x["time"]==y["time"] for x,y in zip(source,tags)),
            "ALSA phase snapshots and SAME native CPAL TLS tags not simultaneous")
    a=prior["host_original_cpal_p_reported_callback_entry_delta"]
    tagged=prior["guest_window_source_tagged_cpal_marker_increments"]
    # Separate counters are observed at nonidentical instants: do NOT force
    # equality or claim the same precise count in callback code.
    aliases={x["anonymous_tls_alias"] for x in prior["matched_native_thread_aliases"]
             if x["real_tagged_cpal_callback_entry_delta"]>0}
    first=int((root/"guest-first-input-monotonic-ns.txt").read_text().strip())
    last=int((root/"guest-final-observation-monotonic-ns.txt").read_text().strip())
    window=guest_window(source,first,last,aliases)
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE311_SOURCE_PINNED_NEW_HOST_ALSA_RETURN_PHASES_REPARSED",
        "real_ci_run_id":run_id,
        "hint_ms":hint,
        "sha256_phase_CSV":rawsha,
        "sha256_matched_cpal_tags_CSV":sha,
        "compiled_stage309_new_host_sha256":prior["experimental_stage309_host_sha256"],
        "generated_original_unchanged_nro_sha256":prior["original_romfree_guest_nro_sha256"],
        "guest_original_cpal_P_L_callback_delta":a,
        "guest_cpal_shared_TLS_callback_mark_delta":tagged,
        "real_cpal_callback_thread_aliases_during_guest":sorted(aliases),
        **window,
        "results_are_for_new_intrusively_instrumented_NeXium_only":True,
        "actual_alsa_wait_can_succeed_after_long_observation":True,
        "no_bounded_snapshot_proves_permanent_blockage_or_audio_root_cause":True,
        "no_original_ps1_soundtrack_or_switch_hardware_test":True,
        "production_audio_fixed":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",required=True,type=Path)
    p.add_argument("--hint",required=True,type=int)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--output",required=True,type=Path)
    x=p.parse_args()
    try: value=audit(x.evidence,x.hint,x.run_id);rc=0
    except (OSError,TypeError,ValueError,KeyError,UnicodeError,
            json.JSONDecodeError,csv.Error) as e:
        value={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
               "production_audio_fixed":False};rc=1
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
    print(json.dumps(value,sort_keys=True,indent=2))
    return rc

if __name__=="__main__":raise SystemExit(main())
