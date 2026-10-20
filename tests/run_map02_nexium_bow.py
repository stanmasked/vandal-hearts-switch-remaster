#!/usr/bin/env python3
"""Real NeXium proof of scene B's optional straight-line bow ability.

Actual mapped controller presses only: A selects/moves; B cancels on an
empty/friendly cell, and B shoots when selected first ally aims at an
active enemy across 2..3 clear squares. No state injection or retail assets.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import time
from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD, GX, GY, CELL,
    cmd, diff, read, tile, count,
)

WHITE = (255, 255, 255)
STATUS = (65, 83, 790, 107)


def selection_white(frame, x, y):
    px, py = GX + CELL*x, GY + CELL*y
    return count(frame, WHITE, (px + 9, py + 9, px + 63, py + 63))


def verify(folder: Path):
    keys = ("legacy", "primary", "second", "invalid_bow",
            "enemy_approach", "shot", "reset", "primary_again",
            "legacy_again")
    im = {k: read(folder, k) for k in keys}
    initial = im["second"]
    invalid = im["invalid_bow"]
    ready, after, reset = im["enemy_approach"], im["shot"], im["reset"]
    for y in range(4):
        if tile(initial, HERO, 1, y) < 500 or tile(initial, ENEMY, 5, y) < 500:
            raise ValueError(f"second arena spawn missing row {y}")
    if tile(invalid, ENEMY, 5, 0) < 500:
        raise ValueError("out-of-range B fire was incorrectly accepted")
    if tile(invalid, HERO, 1, 0) < 500:
        raise ValueError("invalid bow changed active archer health/position")
    if selection_white(invalid, 1, 0) < 40:
        raise ValueError("invalid bow canceled selected archer")
    if not (tile(ready, HERO, 2, 0) > 500 and
            tile(ready, ENEMY, 4, 0) > 500 and
            tile(ready, ENEMY, 5, 0) < 100):
        raise ValueError("enemy never approached bow range after actual move")
    if not (tile(after, ACTED, 2, 0) > 500 and
            tile(after, ENEMY, 4, 0) < 100):
        raise ValueError("ranged B fire did not consume action and kill foe")
    if count(after, ENEMY, BOARD) < 1500:
        raise ValueError("one arrow improperly defeated the entire enemy team")
    if diff(after, ready, BOARD) < 500:
        raise ValueError("bow shot did not materially change visible game state")
    if diff(initial, reset, BOARD) != 0:
        raise ValueError("Y reset did not restore original second 4v4 arena")
    if diff(im["primary"], im["primary_again"], BOARD) != 0:
        raise ValueError("bow action damaged original primary 4v4 arena")
    if diff(im["legacy"], im["legacy_again"], BOARD) != 0:
        raise ValueError("bow action damaged approved legacy MAP02")
    print(
        "VH_MAP02_NEXIUM_BOW_PASS second_arena=1 invalid_range=1 "
        "selection_preserved=1 line_of_sight=1 actual_b_fire=1 "
        "enemy_defeated=1 other_enemies_alive=1 reset=1 "
        "primary_preserved=1 legacy_preserved=1 retail=0",
        flush=True,
    )
    print("Bow evidence: "
          f"invalid_selection_white={selection_white(invalid, 1, 0)} "
          f"shot_board_change={diff(after, ready, BOARD)} "
          f"reset_diff={diff(initial, reset, BOARD)} "
          f"primary_diff={diff(im['primary'], im['primary_again'], BOARD)} "
          f"legacy_diff={diff(im['legacy'], im['legacy_again'], BOARD)}",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
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
            pad.press("q")   # L: enter second original, asset-free arena
            pad.cursor = (1, 0)
            pad.snapshot("second")
            pad.press("c")   # A selects first archer on (1,0)
            pad.goto(5, 0)
            pad.press("x")   # B: invalid because enemy is 4 squares away
            pad.snapshot("invalid_bow")
            pad.goto(1, 0)
            pad.press("x")   # B on friendly square: ordinary cancel
            pad.press("c")   # A select again after valid cancel
            pad.goto(2, 0)
            pad.press("c")   # A move one tile
            pad.press("v")   # X enemy phase, first enemy pursues to (4,0)
            pad.snapshot("enemy_approach")
            pad.press("c")   # A selects archer at (2,0)
            pad.goto(4, 0)
            pad.press("x")   # B: bow fires across clear (3,0), 2 squares
            pad.snapshot("shot")
            pad.press("z")   # Y restore second scene
            pad.cursor = (1, 0)
            pad.snapshot("reset")
            pad.press("q")   # L restore untouched primary 4v4
            pad.cursor = (0, 0)
            pad.snapshot("primary_again")
            pad.toggle_eight()
            pad.press("q")   # restore original legacy Map 1
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
