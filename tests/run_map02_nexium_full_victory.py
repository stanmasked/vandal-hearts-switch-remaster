#!/usr/bin/env python3
"""Play and prove the full asset-free MAP02 battle through real NeXium input.

This runs the exact five-turn victory route exercised by the host-only
test_map02_full_battle_replay.c, but NEVER directly manipulates C game state.
Only NeXium's actual default controller keyboard keys are sent.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time
from PIL import Image, ImageChops

GRID_X, GRID_Y, CELL = 352, 100, 72
HERO = (86, 190, 244)
ENEMY = (235, 89, 98)
ACTED = (105, 126, 151)


def shell(*argv: str, timeout: int = 12) -> str:
    return subprocess.check_output(argv, text=True, timeout=timeout).strip()


class Controller:
    def __init__(self, window: str, evidence: Path):
        self.window = window
        self.cursor = (1, 2)
        self.evidence = evidence

    def press(self, key: str):
        shell("xdotool", "keydown", "--window", self.window, key)
        time.sleep(0.15)
        shell("xdotool", "keyup", "--window", self.window, key)
        time.sleep(0.32)

    def goto(self, x: int, y: int):
        assert 0 <= x < 8 and 0 <= y < 6
        oldx, oldy = self.cursor
        key_x = "Right" if x > oldx else "Left"
        key_y = "Down" if y > oldy else "Up"
        for _ in range(abs(x-oldx)):
            self.press(key_x)
        for _ in range(abs(y-oldy)):
            self.press(key_y)
        self.cursor = (x, y)

    def move(self, from_x: int, from_y: int, to_x: int, to_y: int):
        self.goto(from_x, from_y)
        self.press("c")  # A selects allied unit
        self.goto(to_x, to_y)
        self.press("c")  # A confirms a legal movement

    def attack(self, from_x: int, from_y: int, enemy_x: int, enemy_y: int):
        self.goto(from_x, from_y)
        self.press("c")
        self.goto(enemy_x, enemy_y)
        self.press("c")

    def end(self):
        self.press("v")  # X runs one enemy phase

    def snap(self, name: str):
        shell("import", "-window", self.window,
              str(self.evidence / (name + ".png")))


def count_color(image: Image.Image, color: tuple[int, int, int],
                area: tuple[int, int, int, int]) -> int:
    return sum(
        1 for pix in image.crop(area).getdata()
        if max(abs(p - q) for p, q in zip(pix, color)) <= 10
    )


def tile_color(image: Image.Image, x: int, y: int,
               rgb: tuple[int, int, int]) -> int:
    px, py = GRID_X + CELL*x + 17, GRID_Y + CELL*y + 17
    return count_color(image, rgb, (px, py, px+38, py+38))


def check_screens(evidence: Path):
    names = ("battle", "t1", "t2", "t3", "t4", "victory", "reset")
    frames = {name: Image.open(evidence / (name+".png")).convert("RGB")
              for name in names}
    if any(img.size != (1280,720) for img in frames.values()):
        raise ValueError("real NeXium screenshot size differs from 1280x720")
    b, t1, t2, t3, t4, win, reset = (frames[name] for name in names)
    expected = [
        ("initial ally", tile_color(b,1,2,HERO)>500),
        ("initial enemy", tile_color(b,5,2,ENEMY)>500),
        ("turn1 ally0", tile_color(t1,1,0,HERO)>500),
        ("turn1 ally1", tile_color(t1,3,4,HERO)>500),
        ("turn2 ally0", tile_color(t2,3,0,HERO)>500),
        ("turn2 ally1", tile_color(t2,4,5,HERO)>500),
        ("turn3 enemy3", tile_color(t3,5,5,ENEMY)>500),
        ("turn4 enemy3 defeated", tile_color(t4,5,5,ENEMY)<100),
        ("turn4 last enemy", tile_color(t4,4,0,ENEMY)>500),
        # Ally 0 delivers the final blow and is marked acted (muted grey),
        # not active cyan. Require its actual on-screen acted palette here.
        ("victory ally0 survived and acted", tile_color(win,3,0,ACTED)>500),
        ("victory ally1 survived", tile_color(win,4,5,HERO)>500),
        ("reset ally0", tile_color(reset,1,2,HERO)>500),
        ("reset enemy2", tile_color(reset,5,2,ENEMY)>500),
    ]
    board = (GRID_X, GRID_Y, GRID_X+8*CELL, GRID_Y+6*CELL)
    remaining_enemy_red = count_color(win, ENEMY, board)
    if remaining_enemy_red > 100:
        raise ValueError(f"victory screen still contains enemy: red_pixels={remaining_enemy_red}")
    msg_box = (65, 83, 790, 107)
    diff = ImageChops.difference(t4.crop(msg_box), win.crop(msg_box))
    status_delta = sum(1 for px in diff.getdata() if max(px)>30)
    if status_delta < 150:
        raise ValueError(f"no visible victory status transition: delta={status_delta}")
    reset_board = ImageChops.difference(b.crop(board), reset.crop(board))
    reset_changed = sum(1 for px in reset_board.getdata() if max(px)>30)
    if reset_changed > 700:
        raise ValueError(f"Y did not restore initial battle scene: diff={reset_changed}")
    failures = [name for name, passed in expected if not passed]
    if failures:
        raise ValueError("NeXium tactical victory pixel assertions failed: "+
                         ", ".join(failures))
    print(
        "VH_MAP02_NEXIUM_FULL_VICTORY_PASS turns=5 ally_moves=4 melee=4 "
        "enemy_phases=4 victory=1 reset=1 original_retail=0",
        flush=True,
    )
    print(f"Full-battle visual evidence: defeated_enemy_red={remaining_enemy_red} "
          f"victory_status_delta={status_delta} reset_board_diff={reset_changed}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    opts = parser.parse_args()
    opts.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (opts.evidence_dir / "nexium.log").open("wb") as console:
        process = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(opts.nro.resolve())],
            stdout=console, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if process.poll() is not None:
                raise RuntimeError(f"NeXium exited before input: rc={process.returncode}")
            window = shell("xdotool", "search", "--onlyvisible", "--name", "NeXium").splitlines()[-1]
            try:
                shell("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = Controller(window, opts.evidence_dir)
            pad.press("n")  # Minus: default demo -> real tactical battle mode
            pad.snap("battle")
            # Turn 1
            pad.move(1,2,1,0)
            pad.move(1,4,3,4)
            pad.end(); pad.snap("t1")
            # Turn 2
            pad.move(1,0,3,0)
            pad.move(3,4,4,5)
            pad.end(); pad.snap("t2")
            # Turn 3 (ally 0 deliberately waits)
            pad.attack(4,5,5,5)
            pad.end(); pad.snap("t3")
            # Turn 4
            pad.attack(3,0,4,0)
            pad.attack(4,5,5,5)
            pad.end(); pad.snap("t4")
            # Turn 5: both foes now defeated by actual controller input
            pad.attack(3,0,4,0)
            pad.snap("victory")
            pad.press("z")  # Y reset
            pad.snap("reset")
            check_screens(opts.evidence_dir)
        finally:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=4)


if __name__ == "__main__":
    main()
