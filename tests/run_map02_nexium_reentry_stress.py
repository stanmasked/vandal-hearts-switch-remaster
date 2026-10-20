#!/usr/bin/env python3
"""Six repeated MAP02 entry/exit cycles inside ONE real NeXium process.

Pure controller input, original authored placeholder battles, PNG evidence.
Each cycle arms an actual guard then exercises a different interruption,
returns to original legacy MAP02 and reenters both expanded arenas. No
memory injection, fabricated runtime frames, emulator relaunch, or retail ROM.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD, cmd, diff, read, tile,
    health_bar_pixels,
)
from run_map02_nexium_guard_hud import GUARD_HUD

ROUTES = ("y_reset", "roster_cycle", "scene_change",
          "chord_exit", "actual_guard_hit", "minus_exit")


def names():
    n = ["legacy", "primary", "second"]
    for i, route in enumerate(ROUTES):
        n.extend((f"cycle{i}_armed", f"cycle{i}_second",
                  f"cycle{i}_legacy", f"cycle{i}_primary"))
    n.extend(("cycle1_three", "cycle1_one", "cycle2_scene_a",
              "cycle4_pre_hit", "cycle4_blocked", "cycle5_free_roam"))
    return n


def verify(folder: Path):
    f = {name: read(folder, name) for name in names()}
    old, first, second = f["legacy"], f["primary"], f["second"]
    for y in range(4):
        if (tile(first, HERO, 0, y) < 500 or
            tile(first, ENEMY, 1, y) < 500 or
            tile(second, HERO, 1, y) < 500 or
            tile(second, ENEMY, 5, y) < 500):
            raise ValueError(f"initial 4v4 fixture corrupted in row {y}")
    for i, route in enumerate(ROUTES):
        armed = f[f"cycle{i}_armed"]
        if (tile(armed, ACTED, 1, 2) < 500 or
            diff(second, armed, GUARD_HUD) < 60):
            raise ValueError(f"{route}: shield was not armed by real A/B")
        restored = f[f"cycle{i}_second"]
        if diff(second, restored, BOARD) != 0:
            raise ValueError(f"{route}: resumed second arena retained battle state")
        if diff(second, restored, GUARD_HUD) > 20:
            raise ValueError(f"{route}: stale GUARD ARMED/BLOCKED HUD persisted")
        if tile(restored, HERO, 1, 2) < 500:
            raise ValueError(f"{route}: guard action flag was not cleared")
        if diff(old, f[f"cycle{i}_legacy"], BOARD) != 0:
            raise ValueError(f"{route}: approved original MAP02 changed")
        if diff(first, f[f"cycle{i}_primary"], BOARD) != 0:
            raise ValueError(f"{route}: original expanded arena changed")

    for y in range(3):
        if tile(f["cycle1_three"], HERO, 1, y) < 500:
            raise ValueError(f"roster cycle removed 3v3 ally {y}")
    if tile(f["cycle1_three"], HERO, 1, 3) > 100:
        raise ValueError("roster cycle left phantom 4th ally")
    if tile(f["cycle1_one"], HERO, 1, 0) < 500:
        raise ValueError("1v4 roster missing live first ally")
    for y in range(1, 4):
        if tile(f["cycle1_one"], HERO, 1, y) > 100:
            raise ValueError(f"1v4 retained absent ally {y}")
    if diff(second, f["cycle1_one"], GUARD_HUD) < 60:
        raise ValueError("1v4 did not show unavailable guard")
    if diff(first, f["cycle2_scene_a"], BOARD) != 0:
        raise ValueError("L scene change preserved abandoned guard across arena")
    if diff(old, f["cycle5_free_roam"], BOARD) < 2000:
        raise ValueError("MINUS did not actually leave the battle demo")

    hit_before = health_bar_pixels(f["cycle4_pre_hit"], 1, 0)
    hit_after = health_bar_pixels(f["cycle4_blocked"], 1, 0)
    if not (hit_before >= 70 and 40 <= hit_after <= 78 and
            hit_after < hit_before):
        raise ValueError(
            f"real fourth-phase protected enemy hit not detected: {hit_before}->{hit_after}")
    if diff(f["cycle4_armed"], f["cycle4_blocked"], GUARD_HUD) < 60:
        raise ValueError("active GUARD ARMED never became GUARD BLOCKED")

    print(
        "VH_MAP02_NEXIUM_REENTRY_STRESS_PASS emulator_processes=1 "
        "cycles=6 guard_armed=6 y_reset=1 roster_cycle=1 scene_change=1 "
        "chord_exit=1 guarded_damage=1 minus_exit=1 "
        "six_original_map_restores=1 six_arena_restores=1 "
        "zero_state_leaks=1 retail=0", flush=True)
    print(
        f"reentry stress evidence: guarded_hp={hit_before}->{hit_after} "
        f"second_diffs={','.join(str(diff(second, f[f'cycle{i}_second'], BOARD)) for i in range(6))} "
        f"legacy_diffs={','.join(str(diff(old, f[f'cycle{i}_legacy'], BOARD)) for i in range(6))} "
        f"primary_diffs={','.join(str(diff(first, f[f'cycle{i}_primary'], BOARD)) for i in range(6))}",
        flush=True)


def arm(pad: NeXiumPad):
    pad.goto(1, 2)
    pad.press("c")
    pad.press("x")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nro", type=Path, required=True)
    ap.add_argument("--evidence-dir", type=Path, required=True)
    args = ap.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as log:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=log, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited early: {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("real NeXium window not found")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = NeXiumPad(window, args.evidence_dir)
            pad.press("n")
            pad.snapshot("legacy")
            pad.toggle_eight()
            pad.cursor = (0, 0)
            pad.snapshot("primary")
            pad.press("q")
            pad.cursor = (1, 0)
            pad.snapshot("second")

            for i, route in enumerate(ROUTES):
                if route == "actual_guard_hit":
                    # Pursuit phases happen *before* the guard is armed;
                    # otherwise the shield would expire without a hit.
                    for _ in range(3):
                        pad.press("v")
                    pad.snapshot("cycle4_pre_hit")
                arm(pad)
                pad.snapshot(f"cycle{i}_armed")

                if route == "y_reset":
                    pad.press("z")
                    pad.cursor = (1, 0)
                elif route == "roster_cycle":
                    for label in ("cycle1_three", "cycle1_one", None):
                        pad.press("e")
                        pad.cursor = (1, 0)
                        if label:
                            pad.snapshot(label)
                elif route == "scene_change":
                    pad.press("q")   # Second -> first expanded arena
                    pad.cursor = (0, 0)
                    pad.snapshot("cycle2_scene_a")
                    pad.press("q")   # First -> pristine second arena
                    pad.cursor = (1, 0)
                elif route == "chord_exit":
                    pad.toggle_eight()
                    pad.press("q")   # restore original Map 1 after chord
                    pad.toggle_eight()
                    pad.cursor = (0, 0)
                    pad.press("q")
                    pad.cursor = (1, 0)
                elif route == "actual_guard_hit":
                    pad.press("v")   # Fourth enemy AI phase absorbs first hit
                    pad.snapshot("cycle4_blocked")
                    pad.toggle_eight()
                    pad.press("q")
                    pad.toggle_eight()
                    pad.cursor = (0, 0)
                    pad.press("q")
                    pad.cursor = (1, 0)
                elif route == "minus_exit":
                    pad.press("n")
                    pad.snapshot("cycle5_free_roam")
                    pad.press("n")   # Minus reopens the original Map 1
                    pad.toggle_eight()
                    pad.cursor = (0, 0)
                    pad.press("q")
                    pad.cursor = (1, 0)

                pad.snapshot(f"cycle{i}_second")
                pad.toggle_eight()
                pad.press("q")       # Original Map 1 after L+R toggle
                pad.snapshot(f"cycle{i}_legacy")
                pad.toggle_eight()
                pad.cursor = (0, 0)
                pad.snapshot(f"cycle{i}_primary")
                pad.press("q")
                pad.cursor = (1, 0)

            verify(args.evidence_dir)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    main()
