#!/usr/bin/env python3
"""MAP02 v196: independently execute nine native synthetic guest MIPS-I ops.

v195 pins exact original PS1 opcode bytes. This narrowly scoped interpreter
independently reproduces the actual register, load-delay and scratch-RAM
effects, refusing a syntactically valid program that no longer depends on
the preceding guest SW->LW chain. No original retail code is run.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from struct import unpack_from

from .apply_map02_v183_native_ram_values import make_variants
from .check_map02_v190_native_log_stability import sample_file
from .check_map02_v195_independent_mips_opcodes import audit_opcode_lineage, verify_opcode_image

BASE = 0x001E0000
INITIAL_WORD = 0x1478295A
INITIAL_NEXT = 0xD15EA5ED
NEIGHBOR_GUARD = 0xA1B2C3D4
AUTHORED_WORD = 0x51A7C3D9
COMPUTED_WORD = 0x51A73C26
MASK = 0xFFFFFFFF

PASS_MARKER = (
    "VH196_INDEPENDENT_GUEST_MIPS_RAM_PASS modes=10 words=9 "
    "guest_sw=2 guest_lw=1 load_delay=1 negative_paths=2 "
    "unchanged_neighbor=1 original_retail=0"
)


def sign_extend_16(bits: int) -> int:
    return bits - 0x10000 if bits & 0x8000 else bits


def execute_words(words: tuple[int, ...]) -> tuple[dict[int, int], int, int, tuple[int, ...]]:
    """Isolated MIPS-I subset with one-instruction LW register delay.

    Implements only the opcodes actually present in the signed guest window.
    A delayed load is committed *after* the instruction following LW, never
    before that next instruction executes.
    """
    if len(words) != 9:
        raise ValueError("guest program must contain exactly nine MIPS instructions")
    regs = [0] * 32
    memory = {BASE: INITIAL_WORD, BASE + 4: INITIAL_NEXT, BASE + 8: NEIGHBOR_GUARD}
    pending: tuple[int, int] | None = None
    stores = 0
    loads = 0
    committed_at: list[int] = []
    for pc, word in enumerate(words):
        op = word >> 26
        rs = (word >> 21) & 31
        rt = (word >> 16) & 31
        imm = word & 0xFFFF
        load_on_this_instruction = None
        # Reads below use registers BEFORE a previous load commits.
        if word == 0:
            pass
        elif op == 0x0F and rs == 0 and rt:
            regs[rt] = (imm << 16) & MASK  # LUI
        elif op == 0x0D and rt:
            regs[rt] = (regs[rs] | imm) & MASK  # ORI
        elif op == 0x0E and rt:
            regs[rt] = (regs[rs] ^ imm) & MASK  # XORI
        elif op == 0x2B:  # SW
            address = (regs[rs] + sign_extend_16(imm)) & MASK
            if address not in (BASE, BASE + 4):
                raise ValueError("guest SW attempted an unexpected RAM address")
            memory[address] = regs[rt]
            stores += 1
        elif op == 0x23 and rt:  # LW
            address = (regs[rs] + sign_extend_16(imm)) & MASK
            if address not in (BASE, BASE + 4):
                raise ValueError("guest LW attempted an unexpected RAM address")
            load_on_this_instruction = (rt, memory[address])
            loads += 1
        else:
            raise ValueError(f"unexpected synthetic MIPS-I operation at instruction {pc}")

        if pending is not None:
            target, value = pending
            regs[target] = value
            committed_at.append(pc)
        pending = load_on_this_instruction
        regs[0] = 0
    if pending is not None:
        raise ValueError("guest LW would commit outside nine-word program")
    if memory[BASE + 8] != NEIGHBOR_GUARD:
        raise ValueError("guest incorrectly modified neighboring RAM")
    return memory, stores, loads, tuple(committed_at)


def signed_window(raw: bytes, offset: int) -> tuple[int, ...]:
    if offset < 2048 or offset + 36 > len(raw) or offset % 4 != 0:
        raise ValueError("guest signed MIPS opcode window out of bounds")
    return tuple(unpack_from("<9I", raw, offset))


def audit_guest_ram(directory: Path) -> tuple[int, int, int]:
    original = directory / "V183_RAM_CORRECT.EXE"
    identity = sample_file(original)
    image = original.read_bytes()
    if hashlib.sha256(image).hexdigest() != identity[0]:
        raise ValueError("guest EXE changed during native RAM semantic audit")
    offset = verify_opcode_image(image)
    memory, sw_count, lw_count, delay_points = execute_words(signed_window(image, offset))
    if (
        memory[BASE] != AUTHORED_WORD
        or memory[BASE + 4] != COMPUTED_WORD
        or (sw_count, lw_count, delay_points) != (2, 1, (6,))
    ):
        raise ValueError("native guest SW/LW dependency or MIPS load delay is wrong")
    variants = make_variants()
    if set(variants) != {"CORRECT", "MISSING_SW", "MISSING_LW"}:
        raise ValueError("missing one original negative MIPS program variant")
    expected = {
        "MISSING_SW": (INITIAL_WORD, (INITIAL_WORD ^ 0xFFFF) & MASK, 1, 1),
        "MISSING_LW": (AUTHORED_WORD, 0xFF00, 2, 0),
    }
    for label, (raw0, raw1, sw, lw) in expected.items():
        effects, stores, loads, commits = execute_words(signed_window(variants[label], offset))
        if (
            effects[BASE] != raw0
            or effects[BASE + 4] != raw1
            or stores != sw or loads != lw
            or (label == "MISSING_SW" and commits != (6,))
            or (label == "MISSING_LW" and commits != ())
            or effects[BASE + 8] != NEIGHBOR_GUARD
        ):
            raise ValueError(f"{label}: guest negative MIPS RAM trajectory unexpectedly passed")
        if effects[BASE + 4] == COMPUTED_WORD:
            raise ValueError(f"{label}: broken guest data path falsely computed positive RAM")
    if audit_opcode_lineage(directory) != (10, 9, 2):
        raise ValueError("inherited pinned native opcode/EXE/PCXS receipts incomplete")
    if sample_file(original) != identity:
        raise ValueError("native EXE changed after independent MIPS RAM audit")
    return 10, 9, 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    options = parser.parse_args()
    if audit_guest_ram(options.verify_dir) != (10, 9, 2):
        raise ValueError("independent MIPS RAM semantic audit failed")
    print(PASS_MARKER)


if __name__ == "__main__":
    main()
