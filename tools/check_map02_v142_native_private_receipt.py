#!/usr/bin/env python3
"""Reconcile a PRIVATE native PCSX receipt against independent synthetic source.

Only synthetic v129/v136 MIPS EXE+ELF fixtures are supported in public CI.
No raw PC, program codeword, MMIO address, stored value or file path is logged.
The retail v141 tool remains a separate local-only identity-gated workflow.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .analyze_map02_v131_private_mips_mmio import Refused
from .apply_map02_v139_mips_word_stages import codeword_expectations
from .apply_map02_v140_mmio_effects import expected_actual_mmio
from .verify_map02_v141_private_original_mmio_claims import (
    read_private_exact_mmio_trace,parse_exact_mmio_trace,
    verify_source_bound_exact_mmio_claims,
)

def verify_source_authored_native_receipt(path):
    root=Path(__file__).resolve().parents[1]
    # Reuse the v136 independently generated PS-X and MIPS ELF pair.
    sys.path.insert(0,str(root/"tests"))
    from test_map02_v136_original_code_sections import synthetic_with_exec_section

    raw=read_private_exact_mmio_trace(path)
    events=parse_exact_mmio_trace(raw)
    exe,elf=synthetic_with_exec_section()
    sites,words,prefixes=codeword_expectations()
    pairs=expected_actual_mmio()
    expected=[
        (pc,word,addr,value)
        for (pc,*_),word,(addr,value) in zip(sites,words,pairs)
    ]
    if (len(events)!=19 or len(expected)!=19 or
            prefixes!=(7,11,15,19) or events!=expected):
        raise Refused("native synthetic receipt did not match generated source")
    report=verify_source_bound_exact_mmio_claims(exe,elf,events)
    if (report["source_bound_candidate_events"]!=19 or
            report["source_bound_distinct_mips_sw_sites"]!=19 or
            report["claimed_mmio_register_class_counts"]["gpu_gp0"]!=6 or
            report["statically_bound_linked_list_start_claims"]!=3 or
            report["trace_producer_authenticated"] is not False or
            report["original_map02_loaded_or_rendered"] is not False):
        raise Refused("native synthetic receipt aggregate refused")
    if read_private_exact_mmio_trace(path)!=raw:
        raise Refused("native private receipt changed during comparison")
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_native_receipt",type=Path)
    p.add_argument("--expect-refusal",action="store_true")
    args=p.parse_args()
    try:
        report=verify_source_authored_native_receipt(args.private_native_receipt)
    except (Refused,OSError,ValueError,TypeError):
        if args.expect_refusal:
            print("VH142_CORRUPTED_NATIVE_RECEIPT_REJECTED raw_trace_exported=0")
            return
        p.exit(2,"VH142_NATIVE_PRIVATE_RECEIPT_REFUSED\n")
    if args.expect_refusal:
        p.exit(3,"VH142_NEGATIVE_CONTROL_FALSE_ACCEPT_REFUSED\n")
    print("VH142_NATIVE_SOURCE_EXE_ELF_RECEIPT_PASS "
          "events=19 source_bytes=synthetic "
          "pc_word_address_value_matched=1 retail_map02=0 raw_trace_exported=0")


if __name__=="__main__":
    main()
