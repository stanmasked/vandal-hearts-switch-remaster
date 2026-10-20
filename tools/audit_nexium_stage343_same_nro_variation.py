#!/usr/bin/env python3
"""Stage343: verify original same-NRO cross-run PlayBuffer service-time variability.

The input must be the independently verified Stage342 original four-source
receipt. Software clock and host clock comparisons remain separate. No
physical audio or causal inference follows from these selected source runs.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SCHEMA="vh-stage343-original-same-NRO-service-call-variability/v1"
RESULT="TWO_INDEPENDENT_SAME_NRO_GUEST_SOFTWARE_CAPTURE_OBSERVATIONS_VERIFIED"
PARENT="FOUR_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_CAPTURE_COHORTS_SOURCE_VERIFIED"
NRO_SHA=re.compile(r"[0-9a-f]{64}\Z")
SOURCE_KEYS=("original_guest_history_csv_sha256","original_guest_last_call_csv_sha256",
             "original_host_legacy_csv_sha256","original_host_monotonic_csv_sha256")
FLAGS=("all_three_previous_stage335_original_sources_replayed",
       "original_fourth_stage334_receipt_recomputed_exactly",
       "original_fourth_stage336_receipt_recomputed_exactly",
       "historical_third_and_new_fourth_NRO_PCM_monitor_source_bound",
       "all_four_original_guest_host_CSV_source_hashes_distinct",
       "no_software_guest_clock_converted_into_host_PCM_clock",
       "no_absolute_original_host_or_guest_timestamps_published")
NAMES=("original_first","original_second","original_third","original_fourth")

def report(original:dict)->dict:
    if (not isinstance(original,dict)
        or original.get("result")!=PARENT
        or original.get("schema")!="vh-stage337-four-genuine-neXium-guest-host-source-to-nro-cohorts/v1"
        or any(original.get(key) is not True for key in FLAGS)
        or original.get("physical_Nintendo_Switch_audio_tested") is not False
        or original.get("original_PS1_soundtrack_or_audible_dropout_verified") is not False):
        raise ValueError("missing original four-capture provenance")
    rows=original.get("cohorts")
    if (not isinstance(rows,list) or len(rows)!=4
        or tuple(x.get("source") if isinstance(x,dict) else None for x in rows)!=NAMES
        or original.get("original_third_run_id")!=39175592570
        or original.get("original_fourth_run_id")!=39182548276):
        raise ValueError("original four separate source runs not identified")
    for key in SOURCE_KEYS:
        digests=[r.get(key) for r in rows]
        if (any(not isinstance(v,str) or not NRO_SHA.fullmatch(v) for v in digests)
                or len(set(digests))!=4):
            raise ValueError("original source evidence repeated or malformed")
    for row in rows:
        for key in ("guest_last_software_duration_ns",
                    "guest_prior_lower_median_software_ns",
                    "guest_prior_median_minus_last_software_ns",
                    "guest_last_first_possible_rank"):
            if type(row.get(key)) is not int:
                raise ValueError("source guest software timing absent")
        if (row["guest_prior_median_minus_last_software_ns"]!=
                row["guest_prior_lower_median_software_ns"]-row["guest_last_software_duration_ns"]
            or row["guest_last_first_possible_rank"]<1
            or row["guest_last_first_possible_rank"]>16):
            raise ValueError("guest software median or rank inconsistent")
        host=row.get("host_control_intervals")
        if not isinstance(host,list) or len(host)!=2:
            raise ValueError("original host event intervals absent")
        for h in host:
            if (type(h.get("host_monotonic_delta_ns")) is not int
                or h["host_monotonic_delta_ns"]<=0
                or type(h.get("host_wall_delta_ms")) is not int
                or h["host_wall_delta_ms"]<=0):
                raise ValueError("invalid original host event intervals")
    a,b=rows[2],rows[3]
    sha=original.get("third_same_run_nro_sha256")
    if (not isinstance(sha,str) or not NRO_SHA.fullmatch(sha)
        or original.get("fourth_same_run_nro_sha256")!=sha
        or original.get("third_and_fourth_nro_sha256_match") is not True):
        raise ValueError("third and fourth original captures did not use identical executable")
    delta_last=b["guest_last_software_duration_ns"]-a["guest_last_software_duration_ns"]
    delta_median=b["guest_prior_lower_median_software_ns"]-a["guest_prior_lower_median_software_ns"]
    delta_host=[x["host_monotonic_delta_ns"]-y["host_monotonic_delta_ns"]
                for x,y in zip(b["host_control_intervals"],a["host_control_intervals"])]
    old_deltas=original.get("fourth_minus_previous_three_own_clock_differences")
    if not isinstance(old_deltas,list) or len(old_deltas)!=3:
        raise ValueError("original Stage342 cross-capture deltas missing")
    comparison=old_deltas[2]
    if (comparison.get("fourth_minus_earlier_guest_last_software_ns")!=delta_last
        or comparison.get("fourth_minus_earlier_guest_prior_median_software_ns")!=delta_median
        or comparison.get("fourth_minus_earlier_host_monotonic_control_deltas_ns")!=delta_host):
        raise ValueError("original source-derived cross-run deltas altered")
    if delta_last==0 or delta_median==0:
        raise ValueError("expected original cross-run software observations lost")
    return {
        "schema":SCHEMA,"result":RESULT,
        "third_run_id":39175592570,"fourth_run_id":39182548276,
        "source_bound_identical_NRO_sha256":sha,
        "last_guest_software_call_ns":[a["guest_last_software_duration_ns"],b["guest_last_software_duration_ns"]],
        "prior_guest_software_lower_median_ns":[a["guest_prior_lower_median_software_ns"],b["guest_prior_lower_median_software_ns"]],
        "fourth_minus_third_last_guest_software_ns":delta_last,
        "fourth_minus_third_previous_median_guest_software_ns":delta_median,
        "fourth_minus_third_median_margin_guest_software_ns":delta_median-delta_last,
        "fourth_minus_third_host_only_monotonic_interval_deltas_ns":delta_host,
        "four_original_source_guest_last_software_ns":[c["guest_last_software_duration_ns"] for c in rows],
        "original_guest_and_host_source_SHA256s_are_distinct":True,
        "software_guest_clock_not_subtracted_from_host_clock":True,
        "different_software_durations_do_not_prove_audio_glitch_or_cause":True,
        "population_confidence_or_unseen_sessions_not_inferred":True,
        "physical_Nintendo_Switch_audio_tested":False,
        "original_soundtrack_or_audible_dropout_verified":False,
    }

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage342-report",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        if (args.stage342_report.is_symlink() or not args.stage342_report.is_file()
            or args.stage342_report.stat().st_size>100000
            or args.output.exists() or args.output.is_symlink()):
            raise ValueError("untrusted Stage342 source or output overwrite")
        original=json.loads(args.stage342_report.read_text(encoding="utf-8"))
        result=report(original)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps(result,sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as e:
        print(json.dumps({"result":"STAGE343_UNVERIFIED","error_type":type(e).__name__,
                          "physical_Nintendo_Switch_audio_tested":False}))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
