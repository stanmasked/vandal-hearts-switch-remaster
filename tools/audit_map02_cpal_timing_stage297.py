#!/usr/bin/env python3
"""Stage297: independent, source-pinned temporal analysis of Stage296 REAL CPAL snapshots.

Only cumulative CPAL counters sampled every ~200ms exist. The last positive
delta brackets an event interval; it is NOT a precise callback timestamp.
A stream-play-success lifecycle state is NOT proof a CPAL stream is alive.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from audit_map02_cpal_lifecycle_snapshots import FIELDS,parse
from audit_map02_filelogger_repeatability_stage296 import (
    audit as audit_source_cohort,TRIALS
)

SCHEMA="vh-map02-stage297-real-lifecycle-temporal-window/v1"
PINNED_RUN=39506142824
PINNED_HEAD="3734b12fc2556481a702117175401d80b360db20"
TRACKED=("cpal_entries","cpal_returns","error_callbacks","audioout_appends")
MAX_INPUT_LAG_NS=1_000_000_000


def require(ok,reason):
    if not ok:
        raise ValueError(reason)


def snapshots(path):
    with Path(path).open("r",encoding="ascii",newline="") as f:
        rows=list(csv.reader(f))
    result=[]
    for line in rows:
        require(len(line)==11 and line[0]=="L","Unexpected lifecycle CSV row")
        values=[int(v) for v in line[1:]]
        result.append({"monotonic_ns":values[0],"lifecycle_state":values[1],
                       **dict(zip(FIELDS,values[2:]))})
    return result


def metric_intervals(samples,metric,first_input_ns,last_window_sample_ns):
    """Only count deltas between real samples up through the verified guest window.

    Boundaries are conservatively categorized as pre, post, or crossing input.
    """
    considered=[r for r in samples if r["monotonic_ns"]<=last_window_sample_ns]
    require(len(considered)>=2,"Insufficient samples within guest observation")
    changes=[]
    for previous,current in zip(considered,considered[1:]):
        delta=current[metric]-previous[metric]
        require(delta>=0,"Negative cumulative counter delta")
        if delta:
            low=previous["monotonic_ns"]
            high=current["monotonic_ns"]
            relation=("BEFORE_INPUT" if high<=first_input_ns
                      else "AFTER_INPUT" if low>=first_input_ns
                      else "STRADDLES_INPUT")
            changes.append({"lower_bound_ns":low,"upper_bound_ns":high,
                            "increment":delta,"relative_to_first_input":relation})
    counts={relation:sum(d["increment"] for d in changes
                          if d["relative_to_first_input"]==relation)
            for relation in ("BEFORE_INPUT","STRADDLES_INPUT","AFTER_INPUT")}
    last=changes[-1] if changes else None
    earliest=changes[0] if changes else None
    if last:
        # Guaranteed amount of time without any *sampled* positive delta
        # between the last increment's latest possible time and final sample.
        quiet_ns=max(0,last_window_sample_ns-last["upper_bound_ns"])
        quiet_ms=round(quiet_ns/1_000_000,3)
    else:
        # Could have been callbacks before CSV sampling began; do not claim
        # never-running stream or a known actual stream-stop timestamp.
        quiet_ms=round((last_window_sample_ns-considered[0]["monotonic_ns"])/1_000_000,3)
    return {
        "metric":metric,
        "first_sample_counter":considered[0][metric],
        "final_guest_sample_counter":considered[-1][metric],
        "observed_increment_total":considered[-1][metric]-considered[0][metric],
        "increments_unambiguously_before_input":counts["BEFORE_INPUT"],
        "increments_in_window_straddling_first_input":counts["STRADDLES_INPUT"],
        "increments_unambiguously_after_input":counts["AFTER_INPUT"],
        "first_positive_increment_bracket_ns":
            [earliest["lower_bound_ns"],earliest["upper_bound_ns"]] if earliest else None,
        "last_positive_increment_bracket_ns":
            [last["lower_bound_ns"],last["upper_bound_ns"]] if last else None,
        "last_positive_increment_relation_to_input":
            last["relative_to_first_input"] if last else "NO_INCREMENT_SEEN_IN_CSV",
        "observed_no_new_increment_tail_ms":quiet_ms,
        "tail_is_only_snapshot_observation_not_proven_hardware_pause":True,
        "no_increment_does_not_mean_zero_callbacks_before_first_sample":True,
    }


def analyze_one(csv_file,first_input_ns,last_guest_observation_ns):
    original=parse(csv_file,first_input_ns,last_guest_observation_ns)
    require(original["result"]=="BOUNDED_LIFECYCLE_ATOMIC_SNAPSHOTS_PARSED"
            and original["guest_monotonic_window_verified"] is True,
            "Original Stage288 validated lifecycle window absent")
    rows=snapshots(csv_file)
    require(len(rows)==original["samples"],"Parser/re-reader row disagreement")
    final_stamp=original["final_window_sample_clock_ns"]
    baseline_stamp=original["baseline_clock_ns"]
    # Prevent inferring a timing relation from logs on a different clock.
    require(rows[0]["monotonic_ns"]<baseline_stamp<=first_input_ns
            <last_guest_observation_ns
            and final_stamp<=last_guest_observation_ns
            and last_guest_observation_ns-final_stamp<=MAX_INPUT_LAG_NS,
            "Clock markers do not bound original guest window")
    baseline=next(x for x in rows if x["monotonic_ns"]==baseline_stamp)
    final=next(x for x in rows if x["monotonic_ns"]==final_stamp)
    require({k:final[k]-baseline[k] for k in FIELDS}==
            original["guest_window_atomic_counter_deltas"],
            "Fresh CSV window deltas disagree with Stage288 original parser")
    metrics={m:metric_intervals(rows,m,first_input_ns,final_stamp)
             for m in TRACKED}
    # Never assert that a no-entry observation proves an OS pause/drop event.
    if original["guest_window_atomic_counter_deltas"]["cpal_entries"]>0:
        status="NEW_CPAL_CALLBACK_ENTRIES_AFTER_INPUT_WINDOW"
    elif metrics["cpal_entries"]["observed_increment_total"]==0:
        status="NO_CPAL_CALLBACK_ENTRY_INCREMENT_SEEN_ANYWHERE_IN_OBSERVED_TRACE"
    elif metrics["cpal_entries"]["last_positive_increment_relation_to_input"]=="BEFORE_INPUT":
        status="LATEST_OBSERVED_CPAL_ENTRY_INCREMENT_UNAMBIGUOUSLY_PRE_INPUT"
    else:
        status="NO_WINDOW_DELTA_BUT_PRE_INPUT_BOUNDARY_AMBIGUOUS"
    return {
        "schema":"vh-map02-stage297-per-trial-temporal-analysis/v1",
        "result":"REAL_MONOTONIC_CPAL_COUNTER_WINDOWS_REPARSED",
        "original_csv_sha256":hashlib.sha256(Path(csv_file).read_bytes()).hexdigest(),
        "first_sample_clock_ns":rows[0]["monotonic_ns"],
        "first_input_clock_ns":first_input_ns,
        "guest_final_observation_clock_ns":last_guest_observation_ns,
        "baseline_clock_ns":baseline_stamp,
        "final_window_sample_clock_ns":final_stamp,
        "full_window_lifecycle_state":original["final_lifecycle_state"],
        "original_guest_window_observation":original["guest_window_observation"],
        "stage297_observation":status,
        "metrics":metrics,
        "last_sample_without_new_calls_is_not_stream_drop_event_proof":True,
        "stream_play_returned_ok_does_not_mean_stream_running":True,
        "no_exact_cpal_callback_timestamp_or_hardware_period":True,
        "permanent_deadlock_or_alsa_root_cause_proven":False,
        "physical_switch_speaker_proven":False,
    }


def audit_archived_cohort(root):
    root=Path(root)
    provenance=audit_source_cohort(root,PINNED_RUN,PINNED_HEAD)
    require(provenance["result"]=="FIVE_INDEPENDENT_GUEST_FILELOGGER_RECEIPTS_VERIFIED",
            "Original independently validated five-run cohort missing")
    observations=[]
    for hint,replica in TRIALS:
        p=root/("map02-stage296-hint%d-r%d-evidence"%(hint,replica))
        first=int((p/"guest-first-input-monotonic-ns.txt").read_text().strip())
        last=int((p/"guest-final-observation-monotonic-ns.txt").read_text().strip())
        raw=p/"host-cpal-audioout-timeline.csv"
        receipt=analyze_one(raw,first,last)
        earlier=json.loads((p/"host-cpal-lifecycle-audit.json").read_text())
        require(receipt["original_guest_window_observation"]==
                earlier["guest_window_observation"] and
                receipt["full_window_lifecycle_state"]==
                earlier["final_lifecycle_state"],"Historical lifecycle audit mismatches")
        proof=json.loads((p/"stage294-filelogger-derived-receipt.json").read_text())
        require(proof["guest_window_cpal_entries"]==
                earlier["guest_window_atomic_counter_deltas"]["cpal_entries"],
                "FileLogger proof and raw temporal snapshots disagree")
        observations.append({"hint_ms":hint,"replica":replica,
                             "observed_optical_result":proof["guest_final_optical_result"],
                             "cpal_error_callback_window_delta":
                                 proof["guest_window_cpal_error_callback_delta"],
                             "temporal_analysis":receipt})
    return {
        "schema":SCHEMA,
        "result":"FIVE_SOURCE_PINNED_REAL_CPAL_TEMPORAL_TRACES_REPARSED",
        "original_run_id":PINNED_RUN,
        "original_head_sha":PINNED_HEAD,
        "same_immutable_elf_sha256":provenance["same_pinned_elf_sha256"],
        "same_generated_guest_nro_sha256":provenance["same_rom_free_guest_nro_sha256"],
        "trials":observations,
        "per_callback_exact_timestamps_proven":False,
        "lifecycle_state_3_is_not_current_running_state_proof":True,
        "physical_nintendo_switch_audio_proven":False,
        "audio_root_cause_or_permanent_deadlock_proven":False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        r=audit_archived_cohort(a.root)
        status=0
    except (OSError,ValueError,KeyError,OverflowError,TypeError,
            UnicodeError,csv.Error,json.JSONDecodeError) as exc:
        r={"schema":SCHEMA,"result":"UNVERIFIED","reason":str(exc),
           "physical_nintendo_switch_audio_proven":False,
           "audio_root_cause_or_permanent_deadlock_proven":False}
        status=1
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True))
    return status


if __name__=="__main__":
    raise SystemExit(main())
