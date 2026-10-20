#!/usr/bin/env python3
"""MAP02 v194: attest that the ten native runs used the source-built PS-X EXE.

Unlike v193 (which compares the same file across ten native subprocesses),
this proof independently regenerates the *canonical* signed synthetic guest
MIPS executable from its checked-in Python machine-code builder, compares
its SHA-256 to the real private native input, and then runs the complete
v193/v192/v191/v190/v189 evidence chain. No private bytes are printed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from .apply_map02_v183_native_ram_values import make_variants
from .check_map02_v190_native_log_stability import sample_file
from .check_map02_v193_guest_exe_identity import (
    EXE_NAME, audit_executable, private_receipts
)

PASS_MARKER = (
    "VH194_NATIVE_SOURCE_EXE_REBUILD_PASS modes=10 rebuilt_variants=3 "
    "canonical_exe_sha_match=1 native_exe_receipts=20 "
    "native_exit_receipts=10 original_retail=0"
)


def audit_canonical_source(directory: Path) -> tuple[int, int, int]:
    """Fail closed for a consistent but incorrect native guest executable."""
    prior = sample_file(directory / EXE_NAME)
    receipts_before = private_receipts(directory)
    rebuilt = make_variants()
    if set(rebuilt) != {"CORRECT", "MISSING_SW", "MISSING_LW"}:
        raise ValueError("source builder returned a noncanonical variant set")
    correct = rebuilt["CORRECT"]
    # v183 emits 2048-byte PS-X header and a signed 8192-byte MIPS payload.
    if len(correct) != 10240 or correct[:8] != b"PS-X EXE" or correct[0x4c:0x54] != b"VH78SYN!":
        raise ValueError("source regenerated an invalid synthetic PS-X EXE")
    digests = {key: hashlib.sha256(blob).hexdigest() for key, blob in rebuilt.items()}
    if len(set(digests.values())) != 3:
        raise ValueError("canonical bad SW/LW sources are not distinct")
    if digests["CORRECT"] != prior[0]:
        raise ValueError("native input EXE does not match checked-in source-generated MIPS bytes")
    if audit_executable(directory) != (10, 20, 10):
        raise ValueError("inherited native EXE/exit/log proof failed")
    if sample_file(directory / EXE_NAME) != prior or private_receipts(directory) != receipts_before:
        raise ValueError("native EXE evidence or receipts changed during independent source rebuild")
    return 10, 3, 20


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    args = parser.parse_args()
    if audit_canonical_source(args.verify_dir) != (10, 3, 20):
        raise ValueError("native source-bound executable proof failed")
    print(PASS_MARKER)


if __name__ == "__main__":
    main()
