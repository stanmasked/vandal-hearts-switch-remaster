#!/usr/bin/env python3
"""NeXium controller proof for selecting MAP 2 and winning its authored battle.

Actual keyboard controls map to Switch L=Q, R=E, A=C, Y=Z, Minus=N.
This never alters in-process game state. No retail PS1 content is involved.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageChops

WIDTH, HEIGHT = 1280, 720
GRID_X, GRID_Y, CELL = 352, 100, 72
ENEMY = (235, 89, 98)
HERO = (86, 190, 244)
ACTED_HERO = (105, 126, 151)
BOARD = (GRID_X, GRID_Y, GRID_X + 8 * CELL, GRID_Y + 6 * CELL)


def cmd(*argv: str, timeout: int = 12) -> str:
    return subprocess.check_output(argv, text=True, timeout=timeout).strip()


def press(window: str, key: str):
    cmd("xdotool", "keydown", "--window", window, key)
    time.sleep(0.15)
    cmd("xdotool", "keyup", "--window", window, key)
    time.sleep(0.34)


def snap(window: str, evidence: Path, label: str):
    cmd("import", "-window", window, str(evidence / f"{label}.png"))


def load(root: Path, label: str) -> Image.Image:
    img = Image.open(root / f"{label}.png").convert("RGB")
    if img.size != (WIDTH, HEIGHT):
        raise ValueError(f"{label}: unexpected emulator resolution {img.size}")
    return img


def count(image: Image.Image, color: tuple[int, int, int],
          rect: tuple[int, int, int, int]) -> int:
    return sum(
        1 for pixel in image.crop(rect).getdata()
        if max(abs(v - expected) for v, expected in zip(pixel, color)) <= 10
    )


def tile(image: Image.Image, color: tuple[int, int, int], x: int, y: int) -> int:
    left = GRID_X + CELL*x + 17
    top = GRID_Y + CELL*y + 17
    return count(image, color, (left, top, left+38, top+38))


def delta(left: Image.Image, right: Image.Image, rect) -> int:
    diffs = ImageChops.difference(left.crop(rect), right.crop(rect))
    return sum(1 for rgb in diffs.getdata() if max(rgb) > 30)


def verify_evidence(root: Path):
    first, second, one, won, reset, back = (
        load(root, name)
        for name in ("first", "second", "first_attack", "won", "reset", "back")
    )
    # Map 1 has enemy at (5,2); Map 2 has an enemy at (2,2) instead.
    if not (tile(first, ENEMY, 5, 2) > 500
            and tile(second, ENEMY, 2, 2) > 500
            and tile(second, ENEMY, 2, 4) > 500
            and tile(second, ENEMY, 5, 2) < 100):
        raise ValueError("R did not switch NeXium from map 1 to map 2")
    scene_label = (978, 174, 1150, 215)
    if delta(first, second, scene_label) < 70:
        raise ValueError("selected MAP label did not change")
    # First A melee attack consumes action, killing only the first foe.
    if not (tile(one, ENEMY, 2, 2) < 100
            and tile(one, ENEMY, 2, 4) > 500
            and tile(one, ACTED_HERO, 1, 2) > 500):
        raise ValueError("first MAP 2 melee attack or action consumption missing")
    # Second A melee attack wins; neither foe remains, heroes stay on board.
    if not (count(won, ENEMY, BOARD) < 100
            and tile(won, ACTED_HERO, 1, 2) > 500
            and tile(won, ACTED_HERO, 1, 4) > 500):
        raise ValueError("second MAP 2 attack did not achieve visible victory")
    status = (65, 83, 790, 107)
    status_delta = delta(one, won, status)
    if status_delta < 150:
        raise ValueError("victory status did not visibly replace battle prompt")
    # Y must reset the *selected* MAP 2; L must return to initial MAP 1.
    reset_difference = delta(second, reset, BOARD)
    first_difference = delta(first, back, BOARD)
    if reset_difference != 0 or first_difference != 0:
        raise ValueError(f"scenario reset/switch did not restore original board "
                         f"(map2={reset_difference}, map1={first_difference})")
    print("VH_MAP02_NEXIUM_SCENE_SELECTION_PASS scene_switch=1 "
          "second_battle_victory=1 attacks=2 reset_selected=1 "
          "switch_back=1 original_retail=0", flush=True)
    print(f"NeXium scene evidence: victory_status_delta={status_delta} "
          f"reset_map2_diff={reset_difference} restore_map1_diff={first_difference}",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as logfile:
        process = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=logfile, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if process.poll() is not None:
                raise RuntimeError(f"NeXium exited before input: {process.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible", "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium window was not detected")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            press(window, "n")  # Minus enters unchanged scene 1
            snap(window, args.evidence_dir, "first")
            press(window, "e")  # R selects independently-authored scene 2
            snap(window, args.evidence_dir, "second")
            press(window, "c")  # Select ally 0 at (1,2)
            press(window, "Right")
            press(window, "c")  # Attack foe 2 at (2,2)
            snap(window, args.evidence_dir, "first_attack")
            press(window, "Left")
            press(window, "Down")
            press(window, "Down")
            press(window, "c")  # Select ally 1 at (1,4)
            press(window, "Right")
            press(window, "c")  # Attack foe 3 at (2,4), victory
            snap(window, args.evidence_dir, "won")
            press(window, "z")  # Y resets the *selected* second scene
            snap(window, args.evidence_dir, "reset")
            press(window, "q")  # L returns to the first authored map
            snap(window, args.evidence_dir, "back")
            verify_evidence(args.evidence_dir)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
