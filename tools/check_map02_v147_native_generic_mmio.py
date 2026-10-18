#!/usr/bin/env python3
"""Verify generic ordered PCSX GPU/DMA receipts using private original code.

Public CI: source-authored synthetic native receipt, independently generated
PS-X EXE/ELF and fresh challenge. Private local option: user-owned pinned US
SLUS_004.47 plus extracted MIPS ELF and independently retained challenge,
with exact codeword and MMIO source checks by v141. Accepted *claimed* retail
events do not establish that they actually executed or were MAP02 gameplay.
"""
from __future__ import annotations

import argparse
import hmac
from pathlib import Path

from .analyze_map02_v131_private_mips_mmio import Refused
from .check_map02_v144_run_challenge import (
    SIDECAR,_read_private_challenge,verify_native_run_challenge,
)
from .verify_map02_v141_private_original_mmio_claims import (
    audit_private_source_and_claimed_effects,
    parse_exact_mmio_trace,read_private_exact_mmio_trace,
)

MAX_GENERIC_EVENTS=1024
RESULT_PREFIX="VH147_NATIVE_GENERIC_MMIO_SOURCE_BOUND_PASS"


def verify_bounded_synthetic(receipt_path,expected_challenge_path):
    events=parse_exact_mmio_trace(read_private_exact_mmio_trace(receipt_path))
    if not 1<=len(events)<=MAX_GENERIC_EVENTS:
        raise Refused("bounded synthetic MIPS event count refused")
    report=verify_native_run_challenge(receipt_path,expected_challenge_path)
    if report["events"]!=19 or report["retail_original_executed"] is not False:
        raise Refused("synthetic generic native source witness refused")
    return {
        "events":len(events),
        "scope":"native_source_authored_synthetic_only",
        "source_matching_passed":True,
        "runtime_retail_execution_authenticated":False,
        "original_map02_rendered":False,
        "gpu_hd_parity_proven":False,
    }


def verify_bounded_original_claims(receipt_path,expected_challenge_path,
                                   private_original_exe,private_original_elf):
    # The native collector might be invoked under local operator control in
    # a FUTURE stage. A sidecar alone does not attest the runtime producer.
    receipt_path=Path(receipt_path)
    expected_challenge_path=Path(expected_challenge_path)
    if receipt_path.parent==expected_challenge_path.parent:
        raise Refused("independent run challenge must be outside receipt directory")
    before=_read_private_challenge(expected_challenge_path)
    if not hmac.compare_digest(before,
                               _read_private_challenge(receipt_path.parent/SIDECAR)):
        raise Refused("generic original-event challenge mismatch")
    events=parse_exact_mmio_trace(read_private_exact_mmio_trace(receipt_path))
    if not 1<=len(events)<=MAX_GENERIC_EVENTS:
        raise Refused("generic original MIPS event count overflow")
    report=audit_private_source_and_claimed_effects(
        private_original_exe,private_original_elf,receipt_path)
    if (report["source_bound_candidate_events"]!=len(events) or
            report["trace_producer_authenticated"] is not False or
            report["original_map02_loaded_or_rendered"] is not False):
        raise Refused("original MIPS source correlation scope changed")
    if (before!=_read_private_challenge(expected_challenge_path)
            or not hmac.compare_digest(before,_read_private_challenge(
                    receipt_path.parent/SIDECAR))):
        raise Refused("private challenge changed during source validation")
    return {
        "events":len(events),
        "scope":"private_original_us_exe_elf_source_consistent_claim_only",
        "source_matching_passed":True,
        "runtime_retail_execution_authenticated":False,
        "original_map02_rendered":False,
        "gpu_hd_parity_proven":False,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_mmio_receipt",type=Path)
    parser.add_argument("independent_private_challenge",type=Path)
    parser.add_argument("--private-original-exe",type=Path)
    parser.add_argument("--private-original-elf",type=Path)
    parser.add_argument("--expect-refusal",action="store_true")
    args=parser.parse_args()
    try:
        if bool(args.private_original_exe)!=bool(args.private_original_elf):
            raise Refused("original sources must be supplied together")
        if args.private_original_exe:
            result=verify_bounded_original_claims(
                args.private_mmio_receipt,args.independent_private_challenge,
                args.private_original_exe,args.private_original_elf)
        else:
            result=verify_bounded_synthetic(
                args.private_mmio_receipt,args.independent_private_challenge)
    except (Refused,OSError,ValueError,TypeError):
        if args.expect_refusal:
            print("VH147_GENERIC_MIPS_CLAIM_REFUSED "
                  "exported_private_values=0 retail_executed=0")
            return
        parser.exit(2,"VH147_GENERIC_MIPS_SOURCE_REFUSED\n")
    if args.expect_refusal:
        parser.exit(3,"VH147_FALSE_ACCEPT_REFUSED\n")
    print(RESULT_PREFIX+
          " events=%d source_verified=1 scope=%s"
          " retail_executed=0 private_bytes_exported=0"
          % (result["events"],result["scope"]))


if __name__=="__main__":
    main()
