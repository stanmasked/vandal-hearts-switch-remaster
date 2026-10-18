#!/usr/bin/env python3
"""Stage335: three ORIGINAL NeXium guest-service/host-control source cohorts.

Re-audit original Stage320/322/325 source files separately for two archived
captures and one NEW capture. Require the new capture's saved Stage334 receipt
to exactly match source-derived evidence; retain the old pinned SHA-256s.

The guest software clock is never mapped or subtracted from the host recorder
clock. A new capture is allowed to disagree with either old median ordering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_guest_exit_timeline import ExitTimelineError
from audit_nexium_stage334_capture_manifest import (
    SCHEMA as STAGE334_SCHEMA,
    RESULT as STAGE334_RESULT,
    audit_original_capture,
    load,
)

SCHEMA="vh-stage335-three-original-NeXium-independent-guest-host-source-cohorts/v1"
RESULT="THREE_DISTINCT_ORIGINAL_NEXIUM_GUEST_HOST_SOURCE_COHORTS_REPLAYED"
SHA=re.compile(r"[0-9a-f]{64}\Z")
GUEST="original_guest_history_csv_sha256"
LAST="original_guest_last_call_csv_sha256"
HOST="original_host_legacy_csv_sha256"
MONO="original_host_monotonic_csv_sha256"
ALL_PINS=(GUEST,LAST,HOST,MONO)


def locate_runtime_root(archive:Path)->Path:
    if archive.is_symlink() or not archive.is_dir():
        raise ExitTimelineError("original NeXium artifact root missing or symlinked")
    candidates=list(archive.rglob("host-dual-clock-stage325.json"))
    good=[p for p in candidates
          if p.is_file() and not p.is_symlink()
          and all(not a.is_symlink() for a in p.relative_to(archive).parents)]
    if len(candidates)!=1 or len(good)!=1:
        raise ExitTimelineError("missing, ambiguous, or symlinked original Stage325 capture")
    return good[0].parent


def audit_three(sources:list[dict],old_pins:list[dict],third_receipt:dict)->dict:
    if (len(sources)!=3 or len(old_pins)!=2
            or not isinstance(third_receipt,dict)):
        raise ExitTimelineError("require exactly two original and one new source capture")
    reports=[audit_original_capture(src) for src in sources]
    for i,receipt in enumerate(reports):
        if (receipt.get("schema")!=STAGE334_SCHEMA
                or receipt.get("result")!=STAGE334_RESULT
                or receipt.get("original_stage320_322_325_receipts_recomputed_from_exact_sources") is not True
                or receipt.get("original_stage304_305_strict_success_receipts_checked") is not True
                or receipt.get("physical_Nintendo_Switch_audio_tested") is not False
                or receipt.get("no_guest_to_host_clock_alignment_proven") is not True):
            raise ExitTimelineError("per-capture original guest and host provenance incomplete")
        for key in ALL_PINS:
            value=receipt.get(key)
            if not isinstance(value,str) or not SHA.fullmatch(value):
                raise ExitTimelineError("missing original per-run guest/host SHA-256")
        if i<2:
            pins=old_pins[i]
            if not isinstance(pins,dict) or set(pins)!=set(ALL_PINS):
                raise ExitTimelineError("incomplete pinned original archived source identifiers")
            if any(receipt[k]!=pins[k] for k in ALL_PINS):
                raise ExitTimelineError("original archived source bytes differ from frozen hashes")
    if reports[2]!=third_receipt:
        raise ExitTimelineError("new original Stage334 artifact differs from independent source replay")
    for key in (GUEST,LAST,HOST,MONO):
        if len({r[key] for r in reports})!=3:
            raise ExitTimelineError("three genuine source archives are not independent on a captured source")

    rows=[]
    for name,r in zip(("first","second","third"),reports):
        rows.append({
            "source":"original_"+name,
            **{k:r[k] for k in ALL_PINS},
            "guest_normal_call_count":r["original_guest_normal_call_count"],
            "guest_retained_call_count":r["original_guest_retained_call_count"],
            "guest_previous_successful_calls_in_window":
                r["original_guest_previous_successful_calls_in_window"],
            "guest_last_software_duration_ns":r[
                "original_guest_last_call_duration_software_ns"],
            "guest_prior_lower_median_software_ns":r[
                "original_guest_prior_lower_median_software_ns"],
            "guest_prior_median_minus_last_software_ns":r[
                "original_guest_prior_median_minus_last_software_ns"],
            "guest_previous_faster_equal_slower_counts":r[
                "original_guest_prior_faster_equal_slower_counts"],
            "guest_last_first_possible_rank":r[
                "original_guest_last_call_first_possible_rank"],
            "host_control_intervals":r["original_host_control_deltas"],
        })
    third=rows[2]
    differences=[]
    for index in (0,1):
        old=rows[index]
        oldmedian=old["guest_prior_lower_median_software_ns"]
        newmedian=third["guest_prior_lower_median_software_ns"]
        differences.append({
            "third_minus_original_guest_software_last_duration_ns":
                third["guest_last_software_duration_ns"]-
                old["guest_last_software_duration_ns"],
            "third_minus_original_guest_software_prior_median_ns":
                newmedian-oldmedian if newmedian is not None and oldmedian is not None else None,
        })
    return {
        "schema":SCHEMA,
        "result":RESULT,
        "cohorts":rows,
        "third_minus_each_earlier_guest_software_deltas":differences,
        "new_original_stage334_receipt_reproduced_exactly":True,
        "all_three_stage320_322_325_sources_independently_replayed":True,
        "all_three_strict_stage304_305_success_receipts_checked":True,
        "all_four_original_source_shas_distinct_across_three_captures":True,
        "no_guest_software_clock_subtracted_from_host_clock":True,
        "no_original_absolute_guest_or_host_timestamps_exposed":True,
        "host_pcm_byte_changes_are_not_playback_latency":True,
        "three_captures_not_a_population_sample_or_audible_quality_proof":True,
        "original_soundtrack_or_plus_audible_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-archive",type=Path,required=True)
    p.add_argument("--second-archive",type=Path,required=True)
    p.add_argument("--third-archive",type=Path,required=True)
    p.add_argument("--old-pins",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    try:
        archives=(a.first_archive,a.second_archive,a.third_archive)
        if len({p.resolve() for p in archives})!=3:
            raise ExitTimelineError("three different original NeXium archive roots required")
        if a.output.is_symlink() or a.output.exists():
            raise ExitTimelineError("refuse to overwrite original three-cohort report")
        if (a.old_pins.is_symlink() or not a.old_pins.is_file()
                or a.old_pins.stat().st_size>4096):
            raise ExitTimelineError("missing or oversized old source SHA pins")
        old=json.loads(a.old_pins.read_text(encoding="utf-8"))
        roots=[locate_runtime_root(p) for p in archives]
        receipt=roots[2]/"source-guest-host-stage334.json"
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size>32_000:
            raise ExitTimelineError("new real Stage334 archived receipt missing")
        saved=json.loads(receipt.read_text(encoding="utf-8"))
        reports=audit_three([load(p) for p in roots],old,saved)
        a.output.parent.mkdir(parents=True,exist_ok=True)
        with a.output.open("x",encoding="utf-8") as f:
            json.dump(reports,f,indent=2,sort_keys=True)
            f.write("\n")
        print(json.dumps({
            "result":reports["result"],
            "cohorts":reports["cohorts"],
            "physical_audio_verified":False,
        },sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as exc:
        print(json.dumps({
            "result":"STAGE335_THREE_ORIGINAL_CAPTURE_SOURCES_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_verified":False,
        },sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
