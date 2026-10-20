#!/usr/bin/env python3
"""Stage326 source-bound two-cohort NeXium host-clock comparison.

Re-derive both Stage325 source receipts from original control CSVs.
Compare original host wall and monotonic intervals only; no PCM contents,
guest-to-host timing conversion, audibility or causal latency inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from audit_nexium_host_clock_pairs import audit,ClockPairError
from audit_nexium_pcm_exit_controls import control_events

SCHEMA="vh-stage326-original-neXium-two-cohort-host-clock-comparison/v1"
STAGE304_OK="SOURCE_BOUND_BUFFERED_EXIT_CONTROL_TIMELINE_RECONCILED"
STAGE305_OK="SOURCE_BOUND_PLUS_BUFFERED_ZERO_RUN_ONSET_FENCED"
SHA_RE=re.compile(r"[0-9a-f]{64}\Z")


def verify_cohort(source:dict, *, expected_legacy_sha:str,
                  expected_dual_sha:str)->dict:
    if (not SHA_RE.fullmatch(expected_legacy_sha) or
            not SHA_RE.fullmatch(expected_dual_sha)):
        raise ClockPairError("missing or malformed pinned original hashes")
    legacy=source["legacy_csv"]
    companion=source["dual_csv"]
    if (hashlib.sha256(legacy).hexdigest()!=expected_legacy_sha or
            hashlib.sha256(companion).hexdigest()!=expected_dual_sha):
        raise ClockPairError("original source SHA-256 not pinned to approved capture")
    derived=audit(legacy,companion)
    if derived!=source["stage325"]:
        raise ClockPairError("original Stage325 source receipt did not reproduce")
    strict=source["stage304"]
    later=source["stage305"]
    if (strict.get("result")!=STAGE304_OK
            or strict.get("all_original_source_witnesses_replayed") is not True
            or strict.get("physical_Nintendo_Switch_audio_tested") is not False
            or later.get("result")!=STAGE305_OK
            or later.get("all_original_stage299_through_stage304_evidence_replayed") is not True
            or later.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise ClockPairError("original Stage304/305 strict successful receipt missing")
    try:
        controls=control_events(legacy)
    except ValueError as exc:
        raise ClockPairError("original strict Stage304 legacy CSV rejected") from exc
    stage304_controls=strict.get("exit_control_snapshots")
    if not isinstance(stage304_controls,list) or len(stage304_controls)!=len(controls):
        raise ClockPairError("original strict Stage304 host controls incomplete")
    for csv_row,report_row in zip(controls,stage304_controls):
        for k in ("event","pcm_bytes","host_epoch_ms"):
            if csv_row[k]!=report_row.get(k):
                raise ClockPairError("original legacy controls differ from strict Stage304")
    if (derived["wall_epoch_backwards_pair_count"]!=0
            or derived["wall_epoch_equal_pair_count"]!=0
            or derived["pcm_size_regression_pair_count"]!=0):
        raise ClockPairError("cohort original host control source not monotone")
    return derived


def compare_cohorts(a:dict,b:dict,*,first_pins:tuple[str,str],
                    second_pins:tuple[str,str])->dict:
    if first_pins==second_pins:
        raise ClockPairError("cohort source pins are not independently distinct")
    first=verify_cohort(a,expected_legacy_sha=first_pins[0],
                        expected_dual_sha=first_pins[1])
    second=verify_cohort(b,expected_legacy_sha=second_pins[0],
                         expected_dual_sha=second_pins[1])
    p=first["adjacent_host_clock_deltas"]
    q=second["adjacent_host_clock_deltas"]
    if len(p)!=2 or len(q)!=2:
        raise ClockPairError("unexpected original host event-pair count")
    rows=[]
    for x,y in zip(p,q):
        if (x["first_event"]!=y["first_event"] or
                x["second_event"]!=y["second_event"]):
            raise ClockPairError("different host control pair order")
        rows.append({
            "first_event":x["first_event"],
            "second_event":x["second_event"],
            "first_wall_delta_ms":x["host_wall_delta_ms"],
            "second_wall_delta_ms":y["host_wall_delta_ms"],
            "second_minus_first_wall_delta_ms":
                y["host_wall_delta_ms"]-x["host_wall_delta_ms"],
            "first_monotonic_delta_ns":x["host_monotonic_delta_ns"],
            "second_monotonic_delta_ns":y["host_monotonic_delta_ns"],
            "second_minus_first_monotonic_delta_ns":
                y["host_monotonic_delta_ns"]-x["host_monotonic_delta_ns"],
            "first_pcm_file_size_delta_bytes":x["pcm_file_size_delta_bytes"],
            "second_pcm_file_size_delta_bytes":y["pcm_file_size_delta_bytes"],
        })
    return {
        "schema":SCHEMA,
        "result":"TWO_DISTINCT_ORIGINAL_NEXIUM_HOST_CLOCK_COHORTS_REPLAYED",
        "first_source_sha256":{"legacy":first_pins[0],"monotonic":first_pins[1]},
        "second_source_sha256":{"legacy":second_pins[0],"monotonic":second_pins[1]},
        "original_control_pair_comparison":rows,
        "each_original_stage325_receipt_recomputed_from_original_csv":True,
        "each_original_stage304_host_controls_matched_strict_receipt":True,
        "each_original_stage305_success_receipt_present":True,
        "entire_stage304_or_stage305_pcm_chain_independently_rerun":False,
        "guest_to_host_clock_alignment_proven":False,
        "sound_latency_or_dropout_verified":False,
        "physical_Nintendo_Switch_audio_tested":False,
    }


def load_from_root(root:Path)->dict:
    filenames={
        "legacy_csv":"scene-exit-controls.csv",
        "dual_csv":"scene-exit-controls-monotonic.csv",
        "stage325":"host-dual-clock-stage325.json",
        "stage304":"pcm-exit-controls-stage304.json",
        "stage305":"pcm-plus-onset-fence-stage305.json",
    }
    if root.is_symlink() or not root.is_dir():
        raise ClockPairError("original source extraction root missing or symlink")
    paths={}
    for key,name in filenames.items():
        candidates=list(root.rglob(name))
        safe=[p for p in candidates
              if p.is_file() and not p.is_symlink()
              and all(not q.is_symlink() for q in p.relative_to(root).parents)]
        if len(candidates)!=1 or len(safe)!=1:
            raise ClockPairError("original source missing or ambiguous: "+name)
        paths[key]=safe[0]
    result={}
    for key,p in paths.items():
        if key.endswith("_csv"):
            if p.stat().st_size>4096:
                raise ClockPairError("original control CSV unexpectedly large")
            result[key]=p.read_bytes()
        else:
            if p.stat().st_size>1000000:
                raise ClockPairError("original receipt unexpectedly large")
            result[key]=json.loads(p.read_text(encoding="utf-8"))
    return result


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-root",required=True,type=Path)
    p.add_argument("--second-root",required=True,type=Path)
    p.add_argument("--first-legacy-sha256",required=True)
    p.add_argument("--first-monotonic-sha256",required=True)
    p.add_argument("--second-legacy-sha256",required=True)
    p.add_argument("--second-monotonic-sha256",required=True)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    try:
        if args.first_root.resolve()==args.second_root.resolve():
            raise ClockPairError("original cohort roots must be distinct")
        if args.output.exists() or args.output.is_symlink():
            raise ClockPairError("refuse overwrite Stage326 source comparison")
        result=compare_cohorts(
            load_from_root(args.first_root),
            load_from_root(args.second_root),
            first_pins=(args.first_legacy_sha256,args.first_monotonic_sha256),
            second_pins=(args.second_legacy_sha256,args.second_monotonic_sha256))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as f:
            json.dump(result,f,sort_keys=True,indent=2)
            f.write("\n")
        print(json.dumps({
            "result":result["result"],
            "original_control_pair_comparison":
                result["original_control_pair_comparison"],
            "physical_audio_tested":False},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({
            "result":"STAGE326_ORIGINAL_TWO_COHORT_COMPARISON_NOT_VERIFIED",
            "error_kind":type(exc).__name__,
            "physical_audio_tested":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
