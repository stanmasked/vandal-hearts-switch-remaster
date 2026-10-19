#!/usr/bin/env python3
"""MAP02 v189: adversarially replay actual native PCSX RAM/VBlank logs.

Validate each real synthetic-guest process log, then mutate an in-memory copy
in 15/16 independent ways. Every mutation MUST fail the stricter chronology
oracle, including moving a REFUSED line ahead of its bad RAM readback or
reordering positive markers (gaps in v188's string-presence validation).
Original private logs are read-only and never printed or committed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re

from .check_map02_v188_native_ram_receipts import (
    POSITIVE_RAM, audit_directory, audit_log, corrupted_lane,
    expected_snapshot, refusal_phase,
)

PASS_MARKER = (
    "VH189_NATIVE_LOG_REPLAY_PASS modes=10 snapshots=21 mutations=159 "
    "chronology=1 rejected=159 original_retail=0"
)

def significant(line: str):
    if line.startswith("VH78_VBLANK_OBSERVED "):
        return ("V", int(line.split("phase=", 1)[1].split(" ", 1)[0]))
    if line.startswith("VH187_NATIVE_RAM_SNAPSHOT "):
        return ("S", int(line.split("phase=", 1)[1].split(" ", 1)[0]))
    if line.startswith("VH185_NATIVE_RAM_PERSISTENCE_REFUSED "):
        return ("R", int(line.split("phase=", 1)[1].split(" ", 1)[0]))
    if line in POSITIVE_RAM:
        return ("P", POSITIVE_RAM.index(line))
    return None

def audit_strict(text: str, mode: int) -> int:
    """Require actual interleaving of native VBlank, RAM, refusal and success."""
    snapshots = audit_log(text, mode)
    failure = refusal_phase(mode)
    timeline = [key for line in text.splitlines() if (key := significant(line)) is not None]
    expected: list[tuple[str, int]] = []
    for phase in range(4):
        if phase:
            expected.append(("S", phase))
        if phase == failure:
            expected.append(("R", phase))
            break
        expected.append(("V", phase))
    if failure is None:
        expected.extend(("P", i) for i in range(len(POSITIVE_RAM)))
    if timeline != expected:
        raise ValueError(f"mode {mode}: out-of-order native receipt/refusal/pass timeline")
    return snapshots

def replay_mutations(text: str, mode: int):
    """Yield labelled transcript mutations without ever changing the original."""
    lines = text.splitlines()
    vi = next(i for i, x in enumerate(lines)
              if x.startswith("VH78_VBLANK_OBSERVED "))
    si = next(i for i, x in enumerate(lines)
              if x.startswith("VH187_NATIVE_RAM_SNAPSHOT "))
    v = lines[vi]
    s = lines[si]

    def changed(label, action):
        data = lines.copy()
        action(data)
        return (label, "\n".join(data) + "\n")

    def remove(at):
        return lambda a: a.pop(at)

    def duplicate(at):
        return lambda a: a.insert(at, a[at])

    def replace(at, value):
        return lambda a: a.__setitem__(at, value)

    def swap(i, j):
        return lambda a: (a.__setitem__(i, lines[j]),
                          a.__setitem__(j, lines[i]))

    yield changed("drop-first-vblank", remove(vi))
    yield changed("duplicate-first-vblank", duplicate(vi))
    yield changed("incorrect-vblank-event", replace(vi, v.replace("event=1", "event=2")))
    yield changed("incorrect-vblank-frame", replace(vi, v.replace("frame=1", "frame=2")))
    yield changed("zero-vblank-wait", replace(vi, re.sub(r"loops=[0-9]+", "loops=0", v)))
    yield changed("drop-first-ram", remove(si))
    yield changed("duplicate-first-ram", duplicate(si))
    word = re.search(r"first=([0-9a-f]{8})", s)
    if word is None:
        raise ValueError("first numeric RAM word missing")
    mutated_word = f"first={int(word.group(1),16)^2:08x}"
    yield changed("incorrect-ram-value", replace(si, s.replace(word.group(0), mutated_word)))
    yield changed("wrong-ram-vblank-ordinal", replace(si, s.replace("vblanks=1", "vblanks=2")))
    yield changed("snapshot-before-vblank", swap(vi, si))
    yield changed("malformed-vblank", replace(vi, "VH78_VBLANK_OBSERVED malformed"))
    yield changed("malformed-ram", replace(si, "VH187_NATIVE_RAM_SNAPSHOT malformed"))
    if mode == 0:
        p0 = lines.index(POSITIVE_RAM[0])
        p1 = lines.index(POSITIVE_RAM[1])
        yield changed("drop-pass", remove(p0))
        yield changed("duplicate-pass", duplicate(p0))
        yield changed("reorder-passes", swap(p0, p1))
    else:
        ri = next(i for i, x in enumerate(lines)
                  if x.startswith("VH185_NATIVE_RAM_PERSISTENCE_REFUSED "))
        r = lines[ri]
        last_si = max(i for i, x in enumerate(lines)
                      if x.startswith("VH187_NATIVE_RAM_SNAPSHOT "))
        flag = re.search(r"first_ok=([01])", r)
        if flag is None:
            raise ValueError("refusal identity missing")
        swapped = f"first_ok={1-int(flag.group(1))}"
        yield changed("drop-refusal", remove(ri))
        yield changed("wrong-refusal-field", replace(ri, r.replace(flag.group(0), swapped)))
        yield changed("false-positive-pass", lambda a: a.append(POSITIVE_RAM[0]))
        yield changed("refusal-before-bad-readback", swap(ri, last_si))

def audit_replay(directory: Path) -> tuple[int, int, int]:
    """Read only originals; mutate RAM/VBlank log text strictly in memory."""
    runs, snapshots = audit_directory(directory)
    if runs != 10 or snapshots != 21:
        raise ValueError("v189 requires complete native v188 proof first")
    total_mutations = 0
    for mode in range(10):
        path = directory / (f"v185-{mode}.log" if mode <= 3 else f"v186-{mode}.log")
        raw = path.read_text(encoding="utf-8")
        audit_strict(raw, mode)
        unique: set[str] = set()
        distinct_transcripts: set[str] = set()
        for label, tampered in replay_mutations(raw, mode):
            if label in unique or tampered == raw or tampered in distinct_transcripts:
                raise ValueError(
                    f"v189 invalid, duplicate or overlapping tamper recipe mode={mode}: {label}"
                )
            unique.add(label)
            distinct_transcripts.add(tampered)
            try:
                audit_strict(tampered, mode)
            except ValueError:
                total_mutations += 1
            else:
                raise ValueError(f"v189 verifier accepted hostile replay mode={mode} recipe={label}")
    if total_mutations != 159:
        raise ValueError(f"expected precisely 159 rejected native-log mutations; got {total_mutations}")
    return runs, snapshots, total_mutations

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-dir", type=Path, required=True)
    args = parser.parse_args()
    n, shots, mutations = audit_replay(args.verify_dir)
    assert (n, shots, mutations) == (10, 21, 159)
    print(PASS_MARKER)

if __name__ == "__main__":
    main()
