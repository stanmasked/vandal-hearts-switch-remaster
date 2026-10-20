#!/usr/bin/env python3
"""MAP02 v195: inspect signed guest MIPS-I instruction bytes independently.

v194's source-generated EXE hash is checked against a byte array built by
that same Python source generator. v195 independently pins the nine *literal*
MIPS-I machine words that implement the genuine guest SW/LW/XORI chain,
including the PS1 load-delay-slot NOP and untouched RAM-neighbor writes.
No retail game data is used or printed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from struct import iter_unpack, unpack_from

from .check_map02_v190_native_log_stability import sample_file
from .check_map02_v194_source_bound_exe import audit_canonical_source
from .apply_map02_v183_native_ram_values import make_variants

# Fixed independently reviewed MIPS-I codes, NOT from signed_sequence(),
# make_variants() or any helper used to generate native input. Each number
# encodes rd/rt/rs/imm directly, making a broken generator detectable.
WORDS = (
    0x3C16001E,  # lui s6,0x001e       scratch physical RAM base 0x001e0000
    0x3C1751A7,  # lui s7,0x51a7
    0x36F7C3D9,  # ori s7,s7,0xc3d9   authored original word 0x51a7c3d9
    0xAED70000,  # sw s7,0(s6)       actual guest write
    0x341700FF,  # ori s7,zero,0xff  clobber value; later LW is obligatory
    0x8ED70000,  # lw s7,0(s6)       actual guest read
    0x00000000,  # NOP               MIPS-I load-delay slot
    0x3AF7FFFF,  # xori s7,s7,0xffff transform to 0x51a73c26
    0xAED70004,  # sw s7,4(s6)       guest-computed neighbor
)
MAGIC = b"PS-X EXE"
SIGNATURE = b"VH78SYN!"
PASS_MARKER = (
    "VH195_INDEPENDENT_MIPS_OPCODES_PASS modes=10 words=9 "
    "signed_sequence_unique=1 missing_sw_refused=1 missing_lw_refused=1 "
    "canonical_source=1 original_retail=0"
)


def verify_opcode_image(raw: bytes) -> int:
    """Locate an exact unique 9-instruction chain in signed guest code."""
    if len(raw) != 10240 or raw[:8] != MAGIC or raw[0x4C:0x54] != SIGNATURE:
        raise ValueError("noncanonical or unsigned guest PS-X executable")
    payload = raw[2048:]
    opcodes = tuple(word for (word,) in iter_unpack("<I", payload))
    matches = [
        idx for idx in range(len(opcodes) - len(WORDS) + 1)
        if opcodes[idx:idx + len(WORDS)] == WORDS
    ]
    if len(matches) != 1:
        raise ValueError("expected exactly one hardcoded guest SW/LW MIPS opcode chain")
    idx = matches[0]
    # Reject a surviving duplicate of any of the source-defining stores
    # within the nine-instruction window, even if other instructions remain.
    if opcodes[idx + 3] != 0xAED70000 or opcodes[idx + 5] != 0x8ED70000:
        raise ValueError("MIPS guest physical scratch RAM SW/LW missing")
    return 2048 + 4 * idx


def audit_opcode_lineage(directory: Path) -> tuple[int, int, int]:
    exe_path = directory / "V183_RAM_CORRECT.EXE"
    before = sample_file(exe_path)
    raw = exe_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != before[0]:
        raise ValueError("native EXE was replaced during independent opcode read")
    offset = verify_opcode_image(raw)
    variants = make_variants()
    if set(variants) != {"CORRECT", "MISSING_SW", "MISSING_LW"}:
        raise ValueError("MIPS source lacks exactly three signed variants")
    original = variants["CORRECT"]
    if original != raw:
        raise ValueError("source and native MIPS input differ")
    for label, index in (("MISSING_SW", 3), ("MISSING_LW", 5)):
        corrupt = variants[label]
        if len(corrupt) != len(raw) or corrupt[offset:offset + 36] != (
            b"".join((0 if j == index else word).to_bytes(4, "little")
                     for j, word in enumerate(WORDS))
        ):
            raise ValueError(f"{label} is not the canonical one-opcode guest refusal")
        if corrupt[:offset] != raw[:offset] or corrupt[offset + 36:] != raw[offset + 36:]:
            raise ValueError(f"{label} mutated bytes outside signed nine-word guest wait")
    if audit_canonical_source(directory) != (10, 3, 20):
        raise ValueError("inherited v194/v193 native source proof incomplete")
    if sample_file(exe_path) != before:
        raise ValueError("native guest executable changed across independent opcode audit")
    return 10, 9, 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    options = parser.parse_args()
    if audit_opcode_lineage(options.verify_dir) != (10, 9, 2):
        raise ValueError("guest MIPS instruction lineage not proven")
    print(PASS_MARKER)


if __name__ == "__main__":
    main()
