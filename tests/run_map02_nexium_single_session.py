#!/usr/bin/env python3
"""One genuine NeXium process: bow -> reset -> guard+medic -> roster cycle.

Only physical-controller-mapped xdotool keys are used. Each transition is
proved from PNGs of the same running libnx NRO; no synthetic game state,
memory injection, proprietary map resources, or emulator relaunch.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD, cmd, count,
    diff, health_bar_pixels, read, tile,
)
from run_map02_nexium_bow import selection_white
from run_map02_nexium_guard_hud import GUARD_HUD


STEPS = (
    "legacy", "primary", "second", "bow_rejected", "bow_ready",
    "bow_hit", "bow_reset", "pre_guard", "guard_armed", "guard_hit",
    "medic_healed", "combo_reset", "roster_three", "roster_one",
    "roster_four_again", "primary_again", "legacy_again",
)


def verify(folder: Path) -> None:
    frames = {name: read(folder, name) for name in STEPS}
    original = frames["second"]
    for y in range(4):
        if tile(original, HERO, 1, y) < 500 or tile(original, ENEMY, 5, y) < 500:
            raise ValueError(f"second 4v4 spawn missing row {y}")

    # A rejected out-of-range shot must retain both target and selection.
    rejected = frames["bow_rejected"]
    if tile(rejected, ENEMY, 5, 0) < 500:
        raise ValueError("illegal B shot killed a distant foe")
    if selection_white(rejected, 1, 0) < 40:
        raise ValueError("illegal B shot silently cancelled archer selection")

    ready, shot = frames["bow_ready"], frames["bow_hit"]
    if not (tile(ready, HERO, 2, 0) > 500 and
            tile(ready, ENEMY, 4, 0) > 500):
        raise ValueError("real archer advance and enemy pursuit did not occur")
    if not (tile(shot, ACTED, 2, 0) > 500 and
            tile(shot, ENEMY, 4, 0) < 100 and
            count(shot, ENEMY, BOARD) > 1500):
        raise ValueError("B arrow did not defeat exactly one foe")
    if diff(ready, shot, BOARD) < 500:
        raise ValueError("bow hit produced no real board change")
    if diff(original, frames["bow_reset"], BOARD) != 0:
        raise ValueError("reset after bow did not restore the original arena")

    pre, armed, defended, healed = (
        frames[name] for name in
        ("pre_guard", "guard_armed", "guard_hit", "medic_healed")
    )
    hp_initial = health_bar_pixels(original, 1, 0)
    hp_pre = health_bar_pixels(pre, 1, 0)
    hp_defended = health_bar_pixels(defended, 1, 0)
    hp_healed = health_bar_pixels(healed, 1, 0)
    if not (hp_initial >= 70 and hp_pre == hp_initial and
            40 <= hp_defended <= 78 and hp_defended < hp_pre and
            hp_healed == hp_initial):
        raise ValueError("guard and medic failed to cooperate on real AI injury "
                         f"({hp_initial}->{hp_pre}->{hp_defended}->{hp_healed})")
    if diff(pre, armed, GUARD_HUD) < 60 or diff(armed, defended, GUARD_HUD) < 60:
        raise ValueError("guard READY/ARMED/BLOCKED visible states did not change")
    if tile(armed, ACTED, 1, 2) < 500:
        raise ValueError("guard was not spent in same encounter")
    if tile(defended, HERO, 1, 2) < 500:
        raise ValueError("guard action did not clear after opponent turn")
    if tile(healed, ACTED, 1, 1) < 500:
        raise ValueError("medic did not spend their actual action")
    if diff(original, frames["combo_reset"], BOARD) != 0:
        raise ValueError("guard and medic leaked state through Y reset")

    # Exercises roster cycling in the same process, after both abilities.
    three = frames["roster_three"]
    for y in range(3):
        if tile(three, HERO, 1, y) < 500 or tile(three, ENEMY, 5, y) < 500:
            raise ValueError("3v3 roster missing a live slot")
    if tile(three, HERO, 1, 3) > 100 or tile(three, ENEMY, 5, 3) > 100:
        raise ValueError("3v3 roster leaked padded fourth slot")
    one = frames["roster_one"]
    if tile(one, HERO, 1, 0) < 500:
        raise ValueError("1v4 roster removed the only active ally")
    for y in range(1, 4):
        if tile(one, HERO, 1, y) > 100:
            raise ValueError(f"1v4 roster retained absent ally {y}")
        if tile(one, ENEMY, 5, y) < 500:
            raise ValueError(f"1v4 roster removed enemy {y}")
    if diff(original, frames["roster_four_again"], BOARD) != 0:
        raise ValueError("4v4 roster did not return to pristine second arena")
    if diff(frames["primary"], frames["primary_again"], BOARD) != 0:
        raise ValueError("initial expanded arena changed after combined encounter")
    if diff(frames["legacy"], frames["legacy_again"], BOARD) != 0:
        raise ValueError("approved original MAP02 changed after combined encounter")

    print(
        "VH_MAP02_NEXIUM_SINGLE_SESSION_PASS emulator_processes=1 "
        "invalid_bow=1 legal_bow=1 foe_removed=1 guard_block=1 "
        "medic_followup=1 roster_4v4=1 roster_3v3=1 roster_1v4=1 "
        "reset=1 first_arena_preserved=1 legacy_preserved=1 retail=0",
        flush=True,
    )
    print(
        f"single-session evidence: hp_initial={hp_initial} "
        f"hp_guarded={hp_defended} hp_healed={hp_healed} "
        f"bow_changes={diff(ready, shot, BOARD)} "
        f"guard_ui_armed={diff(pre, armed, GUARD_HUD)} "
        f"guard_ui_blocked={diff(armed, defended, GUARD_HUD)} "
        f"reset_diff={diff(original, frames['combo_reset'], BOARD)} "
        f"roster_return_diff={diff(original, frames['roster_four_again'], BOARD)} "
        f"legacy_diff={diff(frames['legacy'], frames['legacy_again'], BOARD)}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    with (args.evidence_dir / "nexium.log").open("wb") as log:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited before game start: {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("real NeXium game window is missing")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = NeXiumPad(window, args.evidence_dir)
            pad.press("n")           # Minus: legacy Map 1
            pad.snapshot("legacy")
            pad.toggle_eight()       # L+R: optional independent battle
            pad.cursor = (0, 0)
            pad.snapshot("primary")
            pad.press("q")           # L: second arena (4v4)
            pad.cursor = (1, 0)
            pad.snapshot("second")

            # Archer action, followed by an actual reset in this process.
            pad.press("c")           # A select archer
            pad.goto(5, 0)
            pad.press("x")           # B illegal distance 4
            pad.snapshot("bow_rejected")
            pad.goto(1, 0)
            pad.press("x")           # B same tile cancels
            pad.press("c")           # A reselect
            pad.goto(2, 0)
            pad.press("c")           # A legal move
            pad.press("v")           # X: real enemy AI moves into range
            pad.snapshot("bow_ready")
            pad.press("c")           # A reselect archer
            pad.goto(4, 0)
            pad.press("x")           # B range-2 kill
            pad.snapshot("bow_hit")
            pad.press("z")           # Y reset current scene
            pad.cursor = (1, 0)
            pad.snapshot("bow_reset")

            # Guard and medic cooperate on actual fourth enemy phase.
            for _ in range(3):
                pad.press("v")
            pad.snapshot("pre_guard")
            pad.goto(1, 2)
            pad.press("c")
            pad.press("x")           # B arms squad shield
            pad.snapshot("guard_armed")
            pad.press("v")           # X fourth AI turn, first hit reduced
            pad.snapshot("guard_hit")
            pad.goto(1, 1)
            pad.press("c")
            pad.goto(1, 0)
            pad.press("x")           # B medic heals same wounded ally
            pad.snapshot("medic_healed")
            pad.press("z")
            pad.cursor = (1, 0)
            pad.snapshot("combo_reset")

            # Exhaustively cycle all available roster capacities in Arena B.
            for label in ("roster_three", "roster_one", "roster_four_again"):
                pad.press("e")       # R cycles 4x4→3x3→1x4→4x4
                pad.cursor = (1, 0)
                pad.snapshot(label)
            pad.press("q")           # L returns to first expanded arena
            pad.cursor = (0, 0)
            pad.snapshot("primary_again")
            pad.toggle_eight()       # L+R leaves expanded mode
            pad.press("q")           # Restore legacy MAP 1
            pad.snapshot("legacy_again")
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
