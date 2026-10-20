#!/usr/bin/env python3
"""MAP02 v191: bind native pixel phase-pass receipts to RAM/VBlank chronology.

After the read-only v190 stability proof, inspect the same ten private,
original PCSX ReARMed/Unai synthetic-guest process logs. Every native
VH78_PHASE_PASS must follow its real VBlank event and precede the next
pre-execution guest RAM readback. Fault runs must stop at the expected phase,
with NO final VRAM all-phases success. No original retail MAP02 execution.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from .check_map02_v188_native_ram_receipts import refusal_phase
from .check_map02_v190_native_log_stability import audit_stability, snapshot_directory

PHASE = re.compile(r"VH78_PHASE_PASS phase=([0-3]) checked=595 guard=499")
FINAL_VRAM = (
    "VH78_VBLANK_VRAM_PASS vblanks=4 phases=4 samples=2380 "
    "gpu_fifo_reset_kept_state=1 gpu_full_reset_cleared_state=1"
)
PASS_MARKER = (
    "VH191_NATIVE_PHASE_MARKER_CHAIN_PASS modes=10 native_phase_passes=22 "
    "ram_snapshots=21 fault_modes=9 false_final_vram=0 "
    "original_retail=0"
)

def verify_phase_log(data: str, mode: int) -> int:
    """Require 4/1/2/3 exact 595-pixel phase passes after authentic VBlanks."""
    failure = refusal_phase(mode)
    lines = data.splitlines()
    timeline: list[tuple[str, int]] = []
    whole_passes: list[int] = []
    phase_markers = 0
    for ix, line in enumerate(lines):
        if "VH78_PHASE_PASS" in line:
            match = PHASE.fullmatch(line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed or hidden native phase marker")
            timeline.append(("P", int(match.group(1))))
            phase_markers += 1
        elif "VH78_VBLANK_OBSERVED" in line:
            if not line.startswith("VH78_VBLANK_OBSERVED phase="):
                raise ValueError(f"mode {mode}: obfuscated native VBlank marker")
            match = re.match(r"VH78_VBLANK_OBSERVED phase=([0-3]) event=", line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed VBlank marker")
            timeline.append(("V", int(match.group(1))))
        elif re.search(r"\bVH187_NATIVE_RAM_SNAPSHOT\b", line):
            if not line.startswith("VH187_NATIVE_RAM_SNAPSHOT phase="):
                raise ValueError(f"mode {mode}: obfuscated RAM readback marker")
            match = re.match(r"VH187_NATIVE_RAM_SNAPSHOT phase=([1-3]) vblanks=", line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed RAM marker")
            timeline.append(("S", int(match.group(1))))
        if "VH78_VBLANK_VRAM_PASS" in line:
            if line != FINAL_VRAM:
                raise ValueError(f"mode {mode}: malformed or hidden final VRAM success")
            whole_passes.append(ix)

    expected: list[tuple[str, int]] = []
    for phase in range(4):
        if phase:
            expected.append(("S", phase))
        if phase == failure:
            break
        expected.append(("V", phase))
        expected.append(("P", phase))
    if timeline != expected:
        raise ValueError(f"mode {mode}: wrong native phase/VRAM RAM/VBlank order")
    if phase_markers != (4 if failure is None else failure):
        raise ValueError(f"mode {mode}: wrong number of proven 595-pixel samples")
    if failure is None:
        last_phase_idx = max(
            i for i, line in enumerate(lines) if PHASE.fullmatch(line)
        )
        if len(whole_passes) != 1 or whole_passes[0] <= last_phase_idx:
            raise ValueError("clean mode missing final VRAM pass after phase-three pixels")
    elif whole_passes:
        raise ValueError(f"mode {mode}: negative native RAM fault falsely passed all VRAM")
    return phase_markers

def audit_directory(directory: Path) -> tuple[int, int, int, int]:
    before = snapshot_directory(directory)
    modes, shots, mutations = audit_stability(directory)
    total_phases = 0
    for mode in range(10):
        name = f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log"
        # v190 already rejects symlinks, hard links, metadata mutations and
        # file replacement. v191 does not mutate the original input bytes.
        total_phases += verify_phase_log(
            (directory / name).read_text(encoding="utf-8"), mode
        )
    if snapshot_directory(directory) != before:
        raise ValueError("native log file identity or hash changed during phase audit")
    if (modes, shots, mutations, total_phases) != (10, 21, 159, 22):
        raise ValueError("incorrect native pixel checkpoint matrix")
    return modes, shots, mutations, total_phases

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    args = parser.parse_args()
    audit_directory(args.verify_dir)
    print(PASS_MARKER)

if __name__ == "__main__":
    main()
