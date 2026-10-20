#!/usr/bin/env python3
"""Real NeXium 4v4 pathfinding, illegal move and enemy pursuit evidence.

This is an independent sequence from the adjacent-attack win/loss smoke.
Uses real emulator keyboard-to-controller inputs; no in-process state writes.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, BOARD, HERO, ENEMY, ACTED, GX, GY, CELL, cmd,
    count, diff, read, tile,
)

HP_COLOR = (255, 219, 102)


def verify(evidence: Path):
    legacy, initial, invalid, moved, enemy, reset, back = (
        read(evidence, label) for label in
        ("legacy", "start", "invalid_move", "moved", "enemy_turn",
         "reset", "legacy_return")
    )
    for y in range(4):
        if tile(initial, HERO, 0, y) < 500:
            raise ValueError(f"initial ally {y} missing")
        if tile(initial, ENEMY, 1, y) < 500:
            raise ValueError(f"initial opponent {y} missing")

    # A selected hero must not move to authored blocked terrain (3,2).
    # Selection remains armed so that the next valid A actually moves it.
    if not (tile(invalid, HERO, 0, 3) > 500 and
            tile(invalid, HERO, 3, 2) < 100 and
            tile(invalid, ENEMY, 1, 3) > 500):
        raise ValueError("blocked terrain incorrectly accepted as a move")

    # A then chooses a genuinely reachable empty tile one step below.
    if not (tile(moved, ACTED, 0, 4) > 500 and
            tile(moved, HERO, 0, 3) < 100 and
            tile(moved, ENEMY, 1, 3) > 500):
        raise ValueError("legal movement or acted state not visible")

    # X triggers all four independent opponent slots. The first three
    # adjacent enemies damage their corresponding allies; the fourth
    # reaches the newly empty (0,3) square without overlapping another.
    if not (tile(enemy, HERO, 0, 4) > 500 and
            tile(enemy, ENEMY, 0, 3) > 500 and
            tile(enemy, ENEMY, 1, 3) < 100 and
            tile(enemy, HERO, 0, 0) > 500):
        raise ValueError("enemy movement/ally action reset not visible")
    for y in range(3):
        if tile(enemy, HERO, 0, y) < 500:
            raise ValueError(f"ally {y} died before second enemy turn")
    bar = (GX + 16, GY + 59, GX + 56, GY + 63)
    hp_initial = count(initial, HP_COLOR, bar)
    hp_after = count(enemy, HP_COLOR, bar)
    if not (hp_initial >= 80 and 20 <= hp_after <= hp_initial - 40):
        raise ValueError(f"enemy attacks did not visibly lower HP "
                         f"({hp_initial} -> {hp_after})")
    if diff(initial, reset, BOARD) > 150:
        raise ValueError("Y did not reset movement and opponent positions")
    if not (tile(legacy, ENEMY, 5, 2) > 500 and
            tile(back, ENEMY, 5, 2) > 500 and
            diff(legacy, back, BOARD) <= 150):
        raise ValueError("return from 4v4 movement failed to restore MAP 1")
    print(
        "VH_MAP02_NEXIUM_4V4_PATH_PASS illegal_wall=1 moved_ally=1 "
        "acted_state=1 opponent_pursuit=1 hp_damage=1 reset=1 "
        "legacy_map_restored=1 retail=0",
        flush=True,
    )
    print(f"4v4 move-path evidence: initial_hp_pixels={hp_initial} "
          f"enemy_turn_hp_pixels={hp_after} "
          f"reset_board_delta={diff(initial, reset, BOARD)}",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as logfile:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=logfile, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited before gameplay: {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium window was not detected")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = NeXiumPad(window, args.evidence_dir)
            pad.press("n")     # unchanged legacy MAP 1
            pad.snapshot("legacy")
            pad.toggle_eight()  # L+R selects optional original 4v4 scene
            pad.cursor = (0, 0)
            pad.snapshot("start")
            pad.goto(0, 3)
            pad.press("c")     # A selects fourth allied unit
            pad.goto(3, 2)
            pad.press("c")     # illegal blocked terrain; must not move
            pad.snapshot("invalid_move")
            pad.goto(0, 4)
            pad.press("c")     # legal one-square move with same selected ally
            pad.snapshot("moved")
            pad.press("v")     # one enemy phase; fourth enemy pursues gap
            pad.snapshot("enemy_turn")
            pad.press("z")     # Y resets current 4v4 scenario
            pad.snapshot("reset")
            pad.toggle_eight() # back to 2-map legacy mode
            pad.press("q")     # select original MAP 1 deterministically
            pad.snapshot("legacy_return")
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
