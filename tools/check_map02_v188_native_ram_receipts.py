#!/usr/bin/env python3
"""MAP02 v188: fail-closed audit of real native PCSX VBlank/RAM log sequences.

Read the ten private synthetic-guest logs from v187 native PCSX. Demand
ordered, unique RAM snapshots and genuine native VBlank reports, the exact
one-bit delta in nine negative cases, and absence of false success markers.
This does not execute original retail Vandal Hearts MAP02 or Switch hardware.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from .apply_map02_v183_native_ram_values import VALUE, TRANSFORMED
from .apply_map02_v185_ram_vblank_persistence import GUARD_VALUE
from .apply_map02_v187_native_ram_snapshots import SNAPSHOT_SUCCESS

VALUES = (VALUE, TRANSFORMED, GUARD_VALUE)
VBLANK = re.compile(
    r"VH78_VBLANK_OBSERVED phase=([0-3]) event=([1-4]) "
    r"frame=([0-9]+) loops=([0-9]+)"
)
SNAPSHOT = re.compile(
    r"VH187_NATIVE_RAM_SNAPSHOT phase=([1-3]) vblanks=([1-3]) "
    r"first=([0-9a-f]{8}) derived=([0-9a-f]{8}) guard=([0-9a-f]{8})"
)
REFUSAL = re.compile(
    r"VH185_NATIVE_RAM_PERSISTENCE_REFUSED phase=([1-3]) "
    r"first_ok=([01]) derived_ok=([01]) guard_ok=([01])"
)
FORBIDDEN_IN_NEGATIVES = (
    "VH187_NATIVE_RAM_SNAPSHOTS_PASS",
    "VH185_NATIVE_RAM_PERSISTENCE_PASS",
    "VH183_NATIVE_GUEST_RAM_VALUES_PASS",
    "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS",
)
POSITIVE_RAM = (
    SNAPSHOT_SUCCESS,
    "VH185_NATIVE_RAM_PERSISTENCE_PASS boundaries=3 seed_once=1 guest_values_retained=1 guard_retained=1 real_vblanks=4 unai_samples=2380 original_retail=0",
    "VH183_NATIVE_GUEST_RAM_VALUES_PASS windows=4 guest_sw_lw_dependency=1 real_memory_readback=1 vblanks=4 samples=2380 original_retail=0",
    "VH176_GUEST_MIPS_NARROW_GPU_QUIET_PASS windows=4 narrow_reads=0 narrow_writes=0 vblanks=4 samples=2380 native_psxcounters=1 original_retail=0",
)

def refusal_phase(mode: int) -> int | None:
    if not 0 <= mode <= 9:
        raise ValueError("native log mode must be within 0..9")
    if mode == 0:
        return None
    if mode <= 3:
        return 1
    return 2 if mode <= 6 else 3

def corrupted_lane(mode: int) -> int:
    if not 1 <= mode <= 9:
        raise ValueError("corrupted mode must be within 1..9")
    return mode - 1 if mode <= 3 else (mode - 4) % 3

def expected_snapshot(phase: int, mode: int) -> tuple[int, int, int]:
    if phase not in (1, 2, 3):
        raise ValueError("invalid snapshot phase")
    data = list(VALUES)
    if refusal_phase(mode) == phase:
        data[corrupted_lane(mode)] ^= 1
    return tuple(data)

def audit_log(content: str, mode: int) -> int:
    """Return count of verified numeric RAM snapshots, raising on any mismatch."""
    failure = refusal_phase(mode)
    lines = content.splitlines()
    ordered: list[tuple[str, int]] = []
    snapshots = 0
    vblanks = 0
    refusals: list[tuple[int, tuple[int, int, int]]] = []
    for line in lines:
        if line.startswith("VH78_VBLANK_OBSERVED "):
            match = VBLANK.fullmatch(line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed native VBlank")
            phase, event, frame, loops = map(int, match.groups())
            if event != phase + 1 or frame != event or not (1 <= loops < 8000):
                raise ValueError(f"mode {mode}: forged or inconsistent native VBlank")
            ordered.append(("V", phase))
            vblanks += 1
        elif line.startswith("VH187_NATIVE_RAM_SNAPSHOT "):
            match = SNAPSHOT.fullmatch(line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed native numeric RAM snapshot")
            phase, count = map(int, match.groups()[:2])
            actual = tuple(int(word, 16) for word in match.groups()[2:])
            if count != phase or actual != expected_snapshot(phase, mode):
                raise ValueError(f"mode {mode}: incorrect native RAM readback phase={phase}")
            ordered.append(("S", phase))
            snapshots += 1
        elif line.startswith("VH185_NATIVE_RAM_PERSISTENCE_REFUSED "):
            match = REFUSAL.fullmatch(line)
            if match is None:
                raise ValueError(f"mode {mode}: malformed RAM refusal")
            phase = int(match.group(1))
            fields = tuple(int(x) for x in match.groups()[1:])
            refusals.append((phase, fields))
    # Strict temporal interleaving: phase-0 VBlank, phase-1 precheck, etc.
    expected_order: list[tuple[str, int]] = []
    for phase in range(4):
        if phase:
            expected_order.append(("S", phase))
        if phase == failure:
            break
        expected_order.append(("V", phase))
    if ordered != expected_order:
        raise ValueError(f"mode {mode}: duplicate, missing or reordered RAM/VBlank entries")
    if snapshots != (3 if failure is None else failure):
        raise ValueError(f"mode {mode}: wrong native snapshot count")
    if vblanks != (4 if failure is None else failure):
        raise ValueError(f"mode {mode}: wrong genuine emulator VBlank count")
    if failure is None:
        if refusals:
            raise ValueError("clean native log contains a RAM refusal")
        for marker in POSITIVE_RAM:
            if lines.count(marker) != 1:
                raise ValueError("clean native log missing or duplicating positive marker: " + marker)
    else:
        good = [1, 1, 1]
        good[corrupted_lane(mode)] = 0
        if refusals != [(failure, tuple(good))]:
            raise ValueError(f"mode {mode}: wrong RAM refusal field or timing")
        if any(line.startswith(marker) for marker in FORBIDDEN_IN_NEGATIVES for line in lines):
            raise ValueError(f"mode {mode}: false native RAM or GPU success")
    return snapshots

def audit_directory(directory: Path) -> tuple[int, int]:
    """Validate only private per-process log files, rejecting links and huge files."""
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("native proof directory must be a real directory")
    total_snapshots = 0
    for mode in range(10):
        path = directory / (f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log")
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
            raise ValueError(f"missing, linked or oversized mode-{mode} native log")
        total_snapshots += audit_log(path.read_text(encoding="utf-8"), mode)
    return 10, total_snapshots

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    args = parser.parse_args()
    runs, snapshots = audit_directory(args.verify_dir)
    if runs != 10 or snapshots != 21:
        raise ValueError("invalid native receipt matrix dimensions")
    print(
        f"VH188_NATIVE_RAM_RECEIPT_SEQUENCE_PASS modes={runs} snapshots={snapshots} "
        "ordered=1 one_bit_faults=9 real_vblank_records=1 original_retail=0"
    )

if __name__ == "__main__":
    main()
