#!/usr/bin/env python3
"""MAP02 Stage307 source-only 200ms CPAL / exported ALSA coactivity analysis.

The ORIGINAL Stage305 guest ALSA TLS aliases never encode a Linux native thread
identity. No "owner", deadlock, root cause or actual hardware period is deduced.
Match Stage298 P reporter samples with the latest completed Stage305 ALSA P
sample at/before each CPAL P timestamp (max 250ms lag), and compare cumulative
differences, not exact-time function calls. Source-authenticated Stage306
receipts, both actual original Stage305 artifacts, and raw P/L+ALSA are required.
"""
import argparse
from bisect import bisect_right
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_alsa_guest_window_stage306 import (
    compare as reverify_stage306_pair, EXPECTED_NAMES, SOURCE_RUN)
from audit_map02_cpal_lifetime_stage299 import read_p
from capture_map02_alsa_userspace_stage305 import OPS,KINDS,SLOTS

SCHEMA="vh-map02-stage307-alsa-cpal-temporal-coactivity/v1"
MAX_LAG_NS=250_000_000
MIN_BINS=30

def require(value,reason):
    if not value:raise ValueError(reason)

def alsa_frames(path):
    path=Path(path)
    require(path.is_file() and not path.is_symlink(),
            "Actual Stage305 ALSA timestamp source file missing")
    raw=path.read_bytes()
    require(120<len(raw)<16_000_000,"Stage305 ALSA source size invalid")
    try: reader=csv.reader(raw.decode("ascii").splitlines())
    except UnicodeError as e:raise ValueError("ALSА must be ASCII") from e
    require(next(reader,None)==["kind","monotonic_ns","anonymous_alias",
                               "operation",*KINDS],"Stage305 AL​SA source schema changed")
    frames=[]
    for row in reader:
        require(len(row)==10,"Invalid Stage305 TLS row width")
        kind,when,alias,op,*values=row
        try: clock=int(when);who=int(alias);nums=[int(v) for v in values]
        except ValueError as e:raise ValueError("Invalid ALSA numeric source") from e
        require(0<clock<2**64 and all(0<=n<2**64 for n in nums),
                "Invalid ALSA bounded atomic count or clock")
        if kind=="P":
            require(who==-1 and op=="sample" and not any(nums[1:]),
                    "Invalid ALSA P sample marker")
            require(not frames or frames[-1]["clock"]<clock,
                    "Nonmonotonic ALSA source P marker")
            frames.append({"clock":clock,"values":{}})
        elif kind=="S":
            require(frames and clock==frames[-1]["clock"]
                    and 0<=who<SLOTS and op in OPS,
                    "ALSA anonymous alias/operation outside sample")
            key=(who,op)
            require(key not in frames[-1]["values"],
                    "Duplicate ALSA TLS alias and operation inside frame")
            require(nums[0]>0 and sum(nums[1:])<=nums[0],
                    "ALSA status categories exceed call count")
            frames[-1]["values"][key]=dict(zip(KINDS,nums))
        else:
            raise ValueError("Stage305 source frame tag unexpected")
    require(len(frames)>=MIN_BINS,"Too few actual 200ms ALSA samples")
    return frames,hashlib.sha256(raw).hexdigest()

def compare_intervals(p_rows,alsa,first,last):
    require(type(first) is int and type(last) is int and 0<first<last,
            "Original guest monotonic window invalid")
    base=max((i for i,x in enumerate(p_rows) if x["sample_ns"]<=first),
             default=None)
    end=max((i for i,x in enumerate(p_rows) if x["sample_ns"]<=last),
            default=None)
    require(base is not None and end is not None and end-base>=MIN_BINS,
            "Not enough actual P reporter samples within guest interval")
    cp=p_rows[base:end+1]
    clocks=[row["clock"] for row in alsa]
    bound=[]
    lags=[]
    for obj in cp:
        idx=bisect_right(clocks,obj["sample_ns"])-1
        require(idx>=0,"CPAL sample precedes all ALSA samples")
        lag=obj["sample_ns"]-clocks[idx]
        require(0<=lag<=MAX_LAG_NS,
                "CPAL-to-ALSA sample matching exceeds 250ms uncertainty")
        bound.append(alsa[idx]);lags.append(lag)
    aliases=sorted({key[0] for frame in bound
                    for key in frame["values"]})
    require(aliases,"No ALSA TLS alias observed across original guest")
    cpal=[cp[i+1]["cpal_entry_counter"]-cp[i]["cpal_entry_counter"]
          for i in range(len(cp)-1)]
    require(all(x>=0 for x in cpal),"CPAL P callback counter decreased")
    summaries=[]
    for alias in aliases:
        rec={"anonymous_alias":alias,"source_temporal_bins":len(cpal),
             "host_cpal_callback_entry_delta":sum(cpal),
             "alsa_writei_return_total_delta":0,
             "alsa_avail_delay_return_total_delta":0,
             "alsa_avail_delay_eio_delta":0,
             "alsa_avail_delay_epipe_delta":0,
             "bins_both_cpal_and_alsa_writei_increment":0,
             "bins_cpal_increment_only":0,
             "bins_alsa_writei_increment_only":0,
             "bins_neither_increment":0,
             "bins_exact_same_cpal_and_alsa_writei_delta":0,
             "sum_absolute_cpal_vs_alsa_writei_bin_differences":0,
             "max_single_bin_absolute_delta_difference":0}
        for i,c in enumerate(cpal):
            left,right=bound[i]["values"],bound[i+1]["values"]
            def delta(op,key):
                old=left.get((alias,op),{}).get(key,0)
                new=right.get((alias,op),{}).get(key,0)
                require(new>=old,"ALSA sample cumulative category regressed")
                return new-old
            write=delta("writei","total")
            rec["alsa_writei_return_total_delta"]+=write
            rec["alsa_avail_delay_return_total_delta"]+=delta("avail_delay","total")
            rec["alsa_avail_delay_eio_delta"]+=delta("avail_delay","eio")
            rec["alsa_avail_delay_epipe_delta"]+=delta("avail_delay","epipe")
            if c and write:
                rec["bins_both_cpal_and_alsa_writei_increment"]+=1
            elif c:
                rec["bins_cpal_increment_only"]+=1
            elif write:
                rec["bins_alsa_writei_increment_only"]+=1
            else:
                rec["bins_neither_increment"]+=1
            diff=abs(c-write)
            rec["bins_exact_same_cpal_and_alsa_writei_delta"]+=int(c==write)
            rec["sum_absolute_cpal_vs_alsa_writei_bin_differences"]+=diff
            rec["max_single_bin_absolute_delta_difference"]=max(
                rec["max_single_bin_absolute_delta_difference"],diff)
        summaries.append(rec)
    return {
        "actual_host_cpal_P_source_samples_in_window":len(cp),
        "compared_consecutive_200ms_sampling_intervals":len(cpal),
        "first_host_CPAL_P_clock_ns":cp[0]["sample_ns"],
        "last_host_CPAL_P_clock_ns":cp[-1]["sample_ns"],
        "first_guest_input_monotonic_ns":first,
        "last_guest_observation_monotonic_ns":last,
        "host_cpal_guest_interval_entry_delta":sum(cpal),
        "alsa_frame_alignment_max_lag_ns":max(lags),
        "alsa_frame_alignment_mean_lag_ns":sum(lags)//len(lags),
        "tls_alias_coactivity":summaries,
        "matching_P_and_ALSA_snapshots_not_exact_atomic_same_instant":True,
        "source_cumulative_call_total_does_not_prove_buffer_delivery":True,
        "anonymous_tls_alias_is_NOT_cpal_thread_identity":True,
    }

def run(source,stage306):
    source=Path(source)
    prior=reverify_stage306_pair(source)
    require(prior["result"]==
            "REAL_STAGE305_PAIR_POST_INPUT_ALSA_SNAPSHOT_DELTAS_REPARSED"
            and prior["original_source_github_actions_run_id"]==SOURCE_RUN,
            "Source-only Stage306 real pair evidence not verified")
    saved=json.loads(Path(stage306).read_text())
    require(prior==saved,"Original completed Stage306 Actions receipt disagrees")
    trials=[]
    for original in prior["trials"]:
        hint=original["requested_pulse_hint_ms"]
        root=source/EXPECTED_NAMES[hint]
        p=read_p(root/"host-cpal-lifetime-p.csv")
        alsa,sha=alsa_frames(root/"alsa-userspace-anonymous-atomic.csv")
        require(sha==original["source_alsa_csv_sha256"],
                "Original Stage306 authenticated ALSA CSV SHA mismatch")
        first=original["actual_guest_first_input_ns"]
        last=original["actual_guest_final_observation_ns"]
        result=compare_intervals(p,alsa,first,last)
        require(result["host_cpal_guest_interval_entry_delta"]==
                original["actual_guest_CPAL_post_input_entries"],
                "Source-aligned CPAL P delta disagrees with Stage306")
        trials.append({
            "requested_pulse_hint_ms":hint,
            "original_actions_run_id":SOURCE_RUN,
            "original_guest_8_page_optical_crc_verified":
                original["actual_guest_optical_crc_8_of_8_verified"],
            "source_stage305_ALSA_csv_sha256":sha,
            **result,
        })
    require([x["requested_pulse_hint_ms"] for x in trials]==[21,22],
            "Source exact two experiments missing")
    return {
        "schema":SCHEMA,
        "result":"REAL_STAGE307_CPAL_ALSA_200MS_SOURCE_ALIGNED_COACTIVITY",
        "real_stage305_source_actions_run_id":SOURCE_RUN,
        "prior_stage306_success_result_sha256":hashlib.sha256(
            Path(stage306).read_bytes()).hexdigest(),
        "prior_stage306_replay_identical_to_GitHub_verified_receipt":True,
        "trials":trials,
        "coactivity_is_not_actual_native_thread_identity":True,
        "timing_coincidence_does_not_prove_causation":True,
        "ld_preload_perturbs_uninstrumented_process":True,
        "physical_Nintendo_Switch_audio_or_game_ROM_or_original_soundtrack_used":False,
        "no_permanent_audio_deadlock_or_production_audio_fix_proven":True,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",required=True,type=Path)
    ap.add_argument("--stage306-receipt",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try: data=run(args.source,args.stage306_receipt);rc=0
    except (ValueError,KeyError,TypeError,OSError,
            UnicodeError,json.JSONDecodeError,csv.Error) as e:
        data={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(e),
              "no_permanent_audio_deadlock_or_production_audio_fix_proven":True}
        rc=1
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print(json.dumps(data,indent=2,sort_keys=True))
    return rc

if __name__=="__main__":raise SystemExit(main())
