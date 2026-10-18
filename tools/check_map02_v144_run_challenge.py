#!/usr/bin/env python3
"""Privately reject receipt replay across native PCSX synthetic test runs.

A separate, independently retained fresh random 128-bit operator challenge
must match the sidecar written by the actual pinned interpreter process
before its receipt was atomically published. Retains v142's exact complete
synthetic PS-X / MIPS ELF tuple comparison. No path, nonce, hash, PC or GPU
word leaves the private process. This does NOT cryptographically authenticate
the native trace producer or prove any retail MAP02 execution.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re

from .analyze_map02_v131_private_mips_mmio import Refused
from .apply_map02_v139_mips_word_stages import codeword_expectations
from .apply_map02_v140_mmio_effects import expected_actual_mmio
from .check_map02_v142_native_private_receipt import (
    verify_source_authored_native_receipt,
)
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,
)

SIDECAR="vh144-run-challenge.hex"
EXPECTED_COUNT=19
CHALLENGE_PATTERN=re.compile(rb"[0-9a-f]{32}\n\Z",re.ASCII)


def _read_private_challenge(path):
    raw=read_private_exact_mmio_trace(path)
    if not CHALLENGE_PATTERN.fullmatch(raw):
        raise Refused("private native challenge is not canonical 128-bit hex")
    return raw


def _independent_synthetic_receipt_bytes():
    sites,words,prefixes=codeword_expectations()
    effects=expected_actual_mmio()
    if not (len(sites)==len(words)==len(effects)==EXPECTED_COUNT
            and prefixes==(7,11,15,19)):
        raise Refused("synthetic source identity changed")
    return b"".join(
        (json.dumps({
            "address":address,"pc":pc,
            "schema":"vh.map02.private-exact-mmio-claim.v1",
            "seq":i,"value":value,"word":word,
        },sort_keys=True,separators=(",",":"))+"\n").encode()
        for i,((pc,*_),word,(address,value))
        in enumerate(zip(sites,words,effects))
    )


def verify_native_run_challenge(receipt_path,expected_challenge_path):
    receipt_path=Path(receipt_path)
    expected_challenge_path=Path(expected_challenge_path)
    sidecar_path=receipt_path.parent/SIDECAR
    # Require an externally retained challenge file outside the output
    # directory, rather than trusting a replayed receipt + sidecar alone.
    if expected_challenge_path.parent==receipt_path.parent:
        raise Refused("expected challenge must be independently retained")
    expected=_read_private_challenge(expected_challenge_path)
    actual=_read_private_challenge(sidecar_path)
    if not hmac.compare_digest(expected,actual):
        raise Refused("private native run challenge mismatch")
    source_report=verify_source_authored_native_receipt(receipt_path)
    raw=read_private_exact_mmio_trace(receipt_path)
    original_bytes=_independent_synthetic_receipt_bytes()
    if not hmac.compare_digest(
            hashlib.sha256(raw).digest(),
            hashlib.sha256(original_bytes).digest()):
        raise Refused("native event journal SHA-256 did not match source")
    if (_read_private_challenge(expected_challenge_path)!=expected or
            _read_private_challenge(sidecar_path)!=actual or
            read_private_exact_mmio_trace(receipt_path)!=raw):
        raise Refused("private run receipt or challenge changed")
    return {
        "events":EXPECTED_COUNT,
        "fresh_externally_supplied_run_challenge_matched":True,
        "complete_source_authored_mips_tuple_sha256_matched":True,
        "private_receipt_source_verified":source_report[
            "source_bound_candidate_events"]==EXPECTED_COUNT,
        "retail_original_executed":False,
        "original_map02_rendered":False,
        "runtime_producer_cryptographically_authenticated":False,
        "physical_ps1_equivalence_proven":False,
        "nintendo_switch_hd_parity_proven":False,
        "raw_challenge_paths_pcs_gpu_data_or_hashes_exported":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_native_receipt",type=Path)
    parser.add_argument("private_expected_challenge",type=Path)
    parser.add_argument("--expect-refusal",action="store_true")
    args=parser.parse_args()
    try:
        result=verify_native_run_challenge(
            args.private_native_receipt,args.private_expected_challenge)
    except (Refused,OSError,ValueError,TypeError):
        if args.expect_refusal:
            print("VH144_REPLAYED_OR_CHANGED_NATIVE_RECEIPT_REJECTED "
                  "raw_private_data_exported=0")
            return
        parser.exit(2,"VH144_PRIVATE_NATIVE_RUN_BINDING_REFUSED\n")
    if args.expect_refusal:
        parser.exit(3,"VH144_NEGATIVE_CONTROL_FALSE_ACCEPT_REFUSED\n")
    assert result["events"]==EXPECTED_COUNT
    print("VH144_NATIVE_RUN_CHALLENGE_BOUND_PASS "
          "events=19 source_sha256_matched=1 "
          "fresh_run_challenge_matched=1 retail_map02=0 "
          "raw_private_data_exported=0")


if __name__=="__main__":
    main()
