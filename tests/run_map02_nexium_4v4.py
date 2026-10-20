#!/usr/bin/env python3
"""NeXium physical-input proof: unchanged 2v2 maps, optional independent 4v4.

Only xdotool controller keys and PNG captures are used; no in-memory state
injection. The L+R chord is accessible even when NeXium's ZR key is unknown.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageChops

WIDTH, HEIGHT = 1280, 720
GX, GY, CELL = 352, 100, 72
HERO, ENEMY, ACTED = (86, 190, 244), (235, 89, 98), (105, 126, 151)
BOARD = (GX, GY, GX + CELL * 8, GY + CELL * 6)
STATUS = (65, 83, 790, 107)


def cmd(*args: str, timeout: int = 12) -> str:
    return subprocess.check_output(args, text=True, timeout=timeout).strip()


class NeXiumPad:
    def __init__(self, window: str, folder: Path):
        self.window = window
        self.folder = folder
        self.cursor = (0, 0)

    def press(self, key: str):
        cmd("xdotool", "keydown", "--window", self.window, key)
        time.sleep(0.15)
        cmd("xdotool", "keyup", "--window", self.window, key)
        time.sleep(0.32)

    def toggle_eight(self):
        # Q -> Switch L; E -> Switch R. Hold Q while E is pressed.
        cmd("xdotool", "keydown", "--window", self.window, "q")
        time.sleep(0.35)
        cmd("xdotool", "keydown", "--window", self.window, "e")
        time.sleep(0.35)
        cmd("xdotool", "keyup", "--window", self.window, "e")
        time.sleep(0.1)
        cmd("xdotool", "keyup", "--window", self.window, "q")
        time.sleep(0.4)

    def goto(self, x: int, y: int):
        assert 0 <= x < 8 and 0 <= y < 6
        sx, sy = self.cursor
        for _ in range(abs(x - sx)):
            self.press("Right" if x > sx else "Left")
        for _ in range(abs(y - sy)):
            self.press("Down" if y > sy else "Up")
        self.cursor = (x, y)

    def snapshot(self, label: str):
        cmd("import", "-window", self.window,
            str(self.folder / (label + ".png")))

    def attack(self, y: int):
        self.goto(0, y)
        self.press("c")  # A selects exact ally slot
        self.goto(1, y)
        self.press("c")  # A confirms adjacent one-hit kill (2 dmg vs 2 HP)


def read(folder: Path, name: str) -> Image.Image:
    frame = Image.open(folder / (name + ".png")).convert("RGB")
    if frame.size != (WIDTH, HEIGHT):
        raise ValueError(f"{name}: unexpected NeXium screenshot {frame.size}")
    return frame


def count(frame: Image.Image, color: tuple[int, int, int],
          rect: tuple[int, int, int, int]) -> int:
    return sum(1 for px in frame.crop(rect).getdata()
               if max(abs(a-b) for a, b in zip(px, color)) <= 10)


def tile(frame: Image.Image, color: tuple[int, int, int], x: int, y: int) -> int:
    px, py = GX + CELL*x + 17, GY + CELL*y + 17
    return count(frame, color, (px, py, px + 38, py + 38))



def health_bar_pixels(frame: Image.Image, x: int, y: int,
                      sprite_color: tuple[int, int, int] = HERO) -> int:
    """Count health pixels relative to the *observed* sprite position.

    NeXium's 1280x720 window captures can scale/recenter the Switch viewport.
    Hard-coded framebuffer health-bar coordinates may land on the yellow
    cursor outline instead; first find the actual on-screen unit rectangle,
    then sample four rows five pixels underneath its lower edge.
    """
    px = GX + CELL * x + 17
    py = GY + CELL * y + 17
    bounds = (max(0, px - 12), max(0, py - 12),
              min(frame.width, px + 50), min(frame.height, py + 50))
    sprite = [
        (sx, sy)
        for sy in range(bounds[1], bounds[3])
        for sx in range(bounds[0], bounds[2])
        if max(abs(channel - expected)
               for channel, expected in
               zip(frame.getpixel((sx, sy)), sprite_color)) <= 10
    ]
    if len(sprite) < 500:
        return 0
    health_left = min(sx for sx, _ in sprite) - 1
    health_top = max(sy for _, sy in sprite) + 5
    if (health_left < 0 or health_top < 0 or
            health_left + 40 > frame.width or
            health_top + 4 > frame.height):
        return 0
    return count(frame, (255, 219, 102),
                 (health_left, health_top,
                  health_left + 40, health_top + 4))


def diff(a: Image.Image, b: Image.Image, rect) -> int:
    d = ImageChops.difference(a.crop(rect), b.crop(rect))
    return sum(1 for p in d.getdata() if max(p) > 30)


def verify(folder: Path):
    before, start, partial, victory, reset, enemy_t1, defeat, defeat_reset, after = (
        read(folder, k) for k in
        ("legacy", "four_start", "first_kill", "four_victory",
         "four_reset", "enemy_turn_1", "four_defeat",
         "defeat_reset", "legacy_return")
    )
    for y in range(4):
        if not (tile(start, HERO, 0, y) > 500 and
                tile(start, ENEMY, 1, y) > 500):
            raise ValueError(f"4v4 start lacks a live ally/enemy in row {y}")
        if not (tile(reset, HERO, 0, y) > 500 and
                tile(reset, ENEMY, 1, y) > 500):
            raise ValueError(f"Y reset did not restore 4v4 row {y}")
        if tile(victory, ACTED, 0, y) < 500:
            raise ValueError(f"ally {y} not marked acted after actual input")
    if not (tile(partial, ENEMY, 1, 0) < 100 and
            tile(partial, ENEMY, 1, 1) > 500 and
            tile(partial, ACTED, 0, 0) > 500):
        raise ValueError("first legal attack not visible or premature victory")
    if count(victory, ENEMY, BOARD) > 100:
        raise ValueError("some 4v4 opponents survived the four real attacks")
    if diff(partial, victory, STATUS) < 20:
        raise ValueError("visible victory status did not change")
    if diff(start, reset, BOARD) > 150:
        raise ValueError("Y failed to restore original four-by-four board")
    # Confirm a full opponent phase does not cause premature defeat.
    # All four enemy AI agents attack once: hero HP goes from 3 to 1.
    for y in range(4):
        if tile(enemy_t1, HERO, 0, y) < 500:
            raise ValueError(f"ally {y} died prematurely in first enemy phase")
        if tile(defeat, HERO, 0, y) > 100:
            raise ValueError(f"ally {y} survived the second enemy attack")
        if tile(defeat, ENEMY, 1, y) < 500:
            raise ValueError(f"enemy {y} missing after victorious AI phase")
    if diff(enemy_t1, defeat, STATUS) < 20:
        raise ValueError("enemy-caused 4v4 defeat was not visibly announced")
    if diff(start, defeat_reset, BOARD) > 150:
        raise ValueError("Y did not reset the AI-caused four-by-four loss")
    # The window viewport is scaled/offset by NeXium. Sample HP
    # relative to the *observed sprite*, not fixed framebuffer pixels.
    start_hp = health_bar_pixels(start, 0, 0)
    turn_hp = health_bar_pixels(enemy_t1, 0, 0)
    if not (start_hp >= 80 and 20 <= turn_hp <= start_hp - 40):
        raise ValueError(f"first AI phase did not reduce live ally HP "
                         f"(start={start_hp}, after={turn_hp})")
    if not (tile(before, ENEMY, 5, 2) > 500 and
            tile(after, ENEMY, 5, 2) > 500):
        raise ValueError("return from capacity demo did not restore MAP 1")
    if diff(before, after, BOARD) > 150:
        raise ValueError("legacy MAP 1 pixels changed following 4v4 demo")
    if diff(before, start, BOARD) < 5000:
        raise ValueError("L+R did not switch into separate 4v4 runtime")
    print("VH_MAP02_NEXIUM_4V4_PASS entered=1 allies=4 opponents=4 "
          "real_attacks=4 victory=1 enemy_phases=2 defeat=1 "
          "reset=1 legacy_restore=1 retail=0",
          flush=True)
    print(f"4v4 screenshots: victory_status_diff={diff(partial, victory, STATUS)} "
          f"reset_diff={diff(start, reset, BOARD)} "
          f"legacy_diff={diff(before, after, BOARD)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as log:
        proc = subprocess.Popen([os.environ["NEXIUM_BIN"],
                                 str(args.nro.resolve())],
                                stdout=log, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited early ({proc.returncode})")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium window is missing")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = NeXiumPad(window, args.evidence_dir)
            pad.press("n")  # legacy MAP 1
            pad.snapshot("legacy")
            pad.toggle_eight()  # enter separate eight-slot Switch battle
            pad.cursor = (0, 0)
            pad.snapshot("four_start")
            pad.attack(0)
            pad.snapshot("first_kill")
            for y in (1, 2, 3):
                pad.attack(y)
            pad.snapshot("four_victory")
            pad.press("z")  # Y reset after victory
            pad.snapshot("four_reset")
            pad.press("v")  # X: four enemies attack; all allies survive with 1HP
            pad.snapshot("enemy_turn_1")
            pad.press("v")  # X: four enemies attack again; all allies die
            pad.snapshot("four_defeat")
            pad.press("z")  # Y reset after AI-caused defeat
            pad.snapshot("defeat_reset")
            pad.toggle_eight()  # exit eight-slot battle
            pad.press("q")  # restore MAP 1, even if entering chord selected MAP 2
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
