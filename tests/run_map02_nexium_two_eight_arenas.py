#!/usr/bin/env python3
"""NeXium end-to-end proof of two independent 8-slot arenas and three sizes.

Controls and screenshots come from a real libnx NRO, not synthetic scenes
or game-memory injection. Both earlier two-unit MAP02 maps are untouched.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD, cmd, diff, read, tile,
)

ARENA_TAG = (980, 481, 1190, 523)


def verify(folder: Path):
    names = ("legacy", "a_four", "b_four", "b_three", "b_one",
             "b_moved", "b_enemy_turn", "b_reset",
             "a_one", "a_four_again", "legacy_return")
    frames = {name: read(folder, name) for name in names}
    a, b = frames["a_four"], frames["b_four"]
    three, one = frames["b_three"], frames["b_one"]
    moved, enemy, reset = (
        frames["b_moved"], frames["b_enemy_turn"], frames["b_reset"])
    for y in range(4):
        if tile(a, HERO, 0, y) < 500 or tile(a, ENEMY, 1, y) < 500:
            raise ValueError(f"first arena lost original 4v4 row {y}")
        if tile(b, HERO, 1, y) < 500 or tile(b, ENEMY, 5, y) < 500:
            raise ValueError(f"second arena failed to spawn 4v4 row {y}")
        if tile(one, ENEMY, 5, y) < 500:
            raise ValueError(f"second arena 1v4 missing foe {y}")
    for y in range(3):
        if tile(three, HERO, 1, y) < 500 or tile(three, ENEMY, 5, y) < 500:
            raise ValueError("second arena 3v3 contains missing active unit")
    if tile(three, HERO, 1, 3) > 100 or tile(three, ENEMY, 5, 3) > 100:
        raise ValueError("second arena 3v3 exposes padded slots")
    if tile(one, HERO, 1, 0) < 500 or any(
            tile(one, HERO, 1, y) > 100 for y in range(1, 4)):
        raise ValueError("second arena 1v4 has absent/forged allies")
    if not (tile(moved, ACTED, 2, 0) > 500 and
            tile(moved, HERO, 1, 0) < 100):
        raise ValueError("second arena legal ally step did not occur")
    if not (tile(enemy, HERO, 2, 0) > 500 and
            tile(enemy, ENEMY, 4, 0) > 500 and
            tile(enemy, ENEMY, 5, 0) < 100):
        raise ValueError("second arena opponent did not pursue across free path")
    if diff(one, reset, BOARD) != 0:
        raise ValueError("Y failed to restore second arena 1v4 roster")
    if tile(frames["a_one"], HERO, 0, 0) < 500 or any(
            tile(frames["a_one"], HERO, 0, y) > 100
            for y in range(1, 4)):
        raise ValueError("switch back to primary arena lost selected 1v4 size")
    if diff(a, frames["a_four_again"], BOARD) != 0:
        raise ValueError("original 4v4 arena was modified by map toggles")
    if diff(frames["legacy"], frames["legacy_return"], BOARD) != 0:
        raise ValueError("legacy MAP02 map changed after second arena")
    if diff(a, b, BOARD) < 5000:
        raise ValueError("second arena is not visibly different from first")
    if diff(a, b, ARENA_TAG) < 40:
        raise ValueError("second arena HUD identifier was not displayed")
    print("VH_MAP02_NEXIUM_TWO_ARENAS_PASS scenes=2 roster_sizes=3 "
          "second_4v4=1 second_3v3=1 second_1v4=1 move=1 ai_pursuit=1 "
          "reset=1 first_arena_preserved=1 legacy_preserved=1 retail=0",
          flush=True)
    print(f"two-arena evidence: second_reset_diff={diff(one, reset, BOARD)} "
          f"first_arena_diff={diff(a, frames['a_four_again'], BOARD)} "
          f"legacy_diff={diff(frames['legacy'], frames['legacy_return'], BOARD)}",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as out:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=out, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited prematurely: {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium window not found")
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
            pad.snapshot("a_four")
            pad.press("q")  # L: enter independently authored second arena
            pad.cursor = (1, 0)
            pad.snapshot("b_four")
            pad.press("e")  # R: second arena 3v3
            pad.snapshot("b_three")
            pad.press("e")  # R: second arena 1v4
            pad.snapshot("b_one")
            pad.press("c")  # A: select ally at (1,0)
            pad.goto(2, 0)
            pad.press("c")  # A: move one tile
            pad.snapshot("b_moved")
            pad.press("v")  # X: enemy approaches through free corridor
            pad.snapshot("b_enemy_turn")
            pad.press("z")  # Y: reset the same second arena 1v4
            pad.cursor = (1, 0)
            pad.snapshot("b_reset")
            pad.press("q")  # L: return to primary arena, retain 1v4 size
            pad.cursor = (0, 0)
            pad.snapshot("a_one")
            pad.press("e")  # R wraps 1v4 to original 4v4
            pad.snapshot("a_four_again")
            pad.toggle_eight()
            pad.press("q")  # original 2-map state, as prior NeXium proofs
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
