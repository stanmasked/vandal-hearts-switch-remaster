#!/usr/bin/env python3
"""Assert pinned PCSX interpreter routes for unaligned MIPS GPU operations.

Fail closed on changed LWL/LWR/SWL/SWR implementations. In combination
with native signed self-authored MIPS mutations, proves the existing
v173-v176 8/16/32-bit wait observers cover these interpreter paths.
No original game data are accessed.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

FUNCTIONS = (
    "doLWL", "doLWR", "doSWL", "doSWR",
)
MARKER = "VH178_PINNED_MIPS_UNALIGNED_GPU_ROUTES_PASS lwl32=1 lwr32=1 swl16plus8=1 swr8plus16=1 original_retail=0"


def get_function(source: str, name: str) -> str:
    start = f"static void {name}(psxRegisters *regs, u32 rt, u32 addr) {{"
    if source.count(start) != 1:
        raise ValueError(f"missing/duplicate pinned interpreter {name}")
    chunk = source.split(start, 1)[1]
    next_function = chunk.find("\nstatic void ")
    next_handler = chunk.find("\nOP(psx")
    ends = [i for i in (next_function, next_handler) if i >= 0]
    if not ends:
        raise ValueError(f"unterminated pinned interpreter {name}")
    return chunk[:min(ends)]


def require(pattern: str, source: str, description: str) -> None:
    if not re.search(pattern, source, re.S):
        raise ValueError(f"pinned interpreter route missing: {description}")


def check(source: str) -> dict[str, bool]:
    fragments = {name: get_function(source, name) for name in FUNCTIONS}
    for name in ("doLWL", "doLWR"):
        require(r"mem\s*=\s*psxMemRead32\(regs,\s*addr\s*&\s*~3\)\s*;",
                fragments[name], f"{name} must use 32-bit read accessor")
        require(r"doLoad\(regs,\s*rt,\s*val\)\s*;",
                fragments[name], f"{name} load result")
    swl = fragments["doSWL"]
    swr = fragments["doSWR"]
    require(r"switch\s*\(addr\s*&\s*3\)", swl, "SWL offset switch")
    require(r"switch\s*\(addr\s*&\s*3\)", swr, "SWR offset switch")
    if swl.count("case 2:") != 1 or swl.count("case 3:") != 1:
        raise ValueError("SWL must dispatch offset 2 separately")
    if swr.count("case 1:") != 1 or swr.count("case 2:") != 1:
        raise ValueError("SWR must dispatch offset 1 separately")
    swl_two = swl.split("case 2:", 1)[1].split("case 3:", 1)[0]
    swr_one = swr.split("case 1:", 1)[1].split("case 2:", 1)[0]
    require(r"psxMemWrite16\(regs,\s*addr\s*&\s*~3,.*?psxMemWrite8\(\s*regs,\s*addr\s*,",
            swl_two, "SWL offset 2 uses 16-bit and 8-bit writes")
    require(r"psxMemWrite8\s*\(\s*regs,\s*addr\s*,.*?psxMemWrite16\(regs,\s*addr\s*\+\s*1,",
            swr_one, "SWR offset 1 uses 8-bit and 16-bit writes")
    for name in ("doSWL", "doSWR"):
        require(r"psxMemWrite32\(regs,\s*addr", fragments[name],
                f"{name} aligned full-word case must use 32-bit accessor")
    return {name: True for name in FUNCTIONS}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_psxinterpreter", type=Path)
    args = p.parse_args()
    check(args.pinned_psxinterpreter.read_text())
    print(MARKER)


if __name__ == "__main__":
    main()
