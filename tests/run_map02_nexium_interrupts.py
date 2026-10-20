#!/usr/bin/env python3
"""One real NeXium process: interrupt active guard with scene, roster, Y,
mode exit and MINUS; require exact original restoration and no stale state.

This test only sends mapped Switch-controller inputs and reads captured PNGs.
It never modifies game memory, NRO bytes or embedded commercial assets.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD,
    cmd, diff, read, tile, health_bar_pixels,
)
from run_map02_nexium_guard_hud import GUARD_HUD

NAMES = (
    "legacy", "primary", "second", "armed_before_scene",
    "primary_after_scene", "second_after_scene",
    "armed_before_roster", "roster_three", "roster_one",
    "second_after_roster", "armed_before_y", "after_y",
    "pre_hit", "armed_before_hit", "blocked", "legacy_after_block",
    "primary_reentry", "second_reentry", "demo_off", "legacy_after_minus",
    "primary_after_minus", "second_after_minus", "final_legacy",
)


def verify(folder: Path):
    f = {name: read(folder, name) for name in NAMES}
    base, primary, old = f["second"], f["primary"], f["legacy"]
    for row in range(4):
        if tile(base, HERO, 1, row) < 500 or tile(base, ENEMY, 5, row) < 500:
            raise ValueError(f"baseline scene B incomplete row {row}")
        if tile(primary, HERO, 0, row) < 500 or tile(primary, ENEMY, 1, row) < 500:
            raise ValueError(f"baseline expanded scene A incomplete row {row}")

    # Arm guard without ending the turn, then abandon that battle by L.
    for label in ("armed_before_scene", "armed_before_roster", "armed_before_y"):
        if tile(f[label], ACTED, 1, 2) < 500 or diff(base, f[label], GUARD_HUD) < 60:
            raise ValueError(f"real B guard was not armed before {label}")
    for label in ("primary_after_scene", "primary_reentry", "primary_after_minus"):
        if diff(primary, f[label], BOARD) != 0:
            raise ValueError(f"scene A inherited battle state at {label}")
    for label in ("second_after_scene", "second_after_roster",
                  "after_y", "second_reentry", "second_after_minus"):
        if diff(base, f[label], BOARD) != 0:
            raise ValueError(f"scene B was not pristine after {label}")
        if diff(base, f[label], GUARD_HUD) > 20:
            raise ValueError(f"stale guard HUD leaked after {label}")
        if tile(f[label], HERO, 1, 2) < 500:
            raise ValueError(f"guard action flag persisted after {label}")

    # Changing roster cancels guard and removes disabled slots.
    for row in range(3):
        if tile(f["roster_three"], HERO, 1, row) < 500:
            raise ValueError(f"3v3 roster missing ally {row}")
    if tile(f["roster_three"], HERO, 1, 3) > 100:
        raise ValueError("3v3 roster kept phantom fourth ally")
    if tile(f["roster_one"], HERO, 1, 0) < 500:
        raise ValueError("1v4 roster lost active ally")
    for row in range(1, 4):
        if tile(f["roster_one"], HERO, 1, row) > 100:
            raise ValueError(f"1v4 roster retained inactive ally {row}")
    if diff(base, f["roster_one"], GUARD_HUD) < 60:
        raise ValueError("1v4 did not display unavailable guard status")

    # An actual guarded enemy hit happened before exit. Exiting must reset
    # both the HP and the previous "BLOCKED" status on reentry.
    start_hp = health_bar_pixels(base, 1, 0)
    hit_before = health_bar_pixels(f["pre_hit"], 1, 0)
    hit_after = health_bar_pixels(f["blocked"], 1, 0)
    if not (start_hp >= 70 and hit_before == start_hp and
            40 <= hit_after <= 78 and hit_after < hit_before):
        raise ValueError(
            f"no actual guarded AI attack: {start_hp}->{hit_before}->{hit_after}")
    if diff(f["armed_before_hit"], f["blocked"], GUARD_HUD) < 60:
        raise ValueError("GUARD ARMED never changed to BLOCKED")

    if diff(old, f["demo_off"], BOARD) < 2000:
        raise ValueError("MINUS did not actually disable battle demo")

    for label in ("legacy_after_block", "legacy_after_minus", "final_legacy"):
        if diff(old, f[label], BOARD) != 0:
            raise ValueError(f"approved legacy MAP02 changed after {label}")
    if diff(f["second_reentry"], f["second_after_minus"], BOARD) != 0:
        raise ValueError("MINUS reentry changed pristine arena layout")

    print(
        "VH_MAP02_NEXIUM_INTERRUPTS_PASS emulator_processes=1 "
        "guard_scene_cancel=1 guard_roster_cancel=1 guard_y_cancel=1 "
        "guard_blocked_exit=1 old_map_preserved=1 minus_reentry=1 "
        "scene_a_preserved=1 roster_3v3=1 roster_1v4=1 "
        "all_resets_exact=1 retail=0", flush=True)
    print(
        f"interrupt evidence: guard_hp={hit_before}->{hit_after} "
        f"scene_return_diff={diff(base, f['second_after_scene'], BOARD)} "
        f"roster_return_diff={diff(base, f['second_after_roster'], BOARD)} "
        f"y_reset_diff={diff(base, f['after_y'], BOARD)} "
        f"reentry_diff={diff(base, f['second_reentry'], BOARD)} "
        f"minus_return_diff={diff(base, f['second_after_minus'], BOARD)} "
        f"legacy_diff={diff(old, f['final_legacy'], BOARD)}",
        flush=True)


def arm(pad: NeXiumPad):
    pad.goto(1, 2)
    pad.press("c")        # A selects third ally
    pad.press("x")        # B arms squad shield


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nro", required=True, type=Path)
    ap.add_argument("--evidence-dir", required=True, type=Path)
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
                raise RuntimeError("NeXium window missing")
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
            pad.press("q")          # L -> second 4v4
            pad.cursor = (1, 0)
            pad.snapshot("second")

            arm(pad)
            pad.snapshot("armed_before_scene")
            pad.press("q")          # L -> original expanded arena
            pad.cursor = (0, 0)
            pad.snapshot("primary_after_scene")
            pad.press("q")          # L -> second arena again
            pad.cursor = (1, 0)
            pad.snapshot("second_after_scene")

            arm(pad)
            pad.snapshot("armed_before_roster")
            for label in ("roster_three", "roster_one", "second_after_roster"):
                pad.press("e")      # R: 4v4 -> 3v3 -> 1v4 -> 4v4
                pad.cursor = (1, 0)
                pad.snapshot(label)

            arm(pad)
            pad.snapshot("armed_before_y")
            pad.press("z")          # Y resets current arena with armed shield
            pad.cursor = (1, 0)
            pad.snapshot("after_y")

            for _ in range(3):
                pad.press("v")      # X: real enemy pursuit 3 phases
            pad.snapshot("pre_hit")
            arm(pad)
            pad.snapshot("armed_before_hit")
            pad.press("v")          # X fourth phase absorbs 1 enemy damage
            pad.snapshot("blocked")

            pad.toggle_eight()     # leave expanded battle after real hit
            pad.press("q")          # restore first approved old map
            pad.snapshot("legacy_after_block")
            pad.toggle_eight()     # reenter first expanded arena
            pad.cursor = (0, 0)
            pad.snapshot("primary_reentry")
            pad.press("q")          # second arena
            pad.cursor = (1, 0)
            pad.snapshot("second_reentry")

            pad.press("n")          # MINUS disables battle demo entirely
            pad.snapshot("demo_off")
            pad.press("n")          # MINUS reopens old MAP02 at scenario_id=0
            # Do not press L here: MINUS explicitly initializes Map 1, while
            # an extra L would accidentally cycle into the other legacy map.
            pad.snapshot("legacy_after_minus")
            pad.toggle_eight()
            pad.cursor = (0, 0)
            pad.snapshot("primary_after_minus")
            pad.press("q")
            pad.cursor = (1, 0)
            pad.snapshot("second_after_minus")
            pad.toggle_eight()
            pad.press("q")
            pad.snapshot("final_legacy")

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
