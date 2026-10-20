#!/usr/bin/env python3
"""Real NeXium X11 gameplay proof for the original asset-free Switch prototype.

Uses mapped controller keys and captured NeXium framebuffer PNGs. No guest RAM
injection, fabricated gameplay frames, proprietary ROM files or retail claims.
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
BOARD = (GX, GY, GX + 8 * CELL, GY + 6 * CELL)
HERO = (86, 190, 244)
ENEMY = (235, 89, 98)
CURSOR = (255, 219, 102)
TOLERANCE = 12


def cmd(*arguments: str, timeout: int = 12) -> str:
    return subprocess.check_output(arguments, timeout=timeout, text=True).strip()


def press(window: str, key: str) -> None:
    cmd("xdotool", "keydown", "--window", window, key)
    time.sleep(0.15)
    cmd("xdotool", "keyup", "--window", window, key)
    time.sleep(0.38)


def snapshot(window: str, folder: Path, name: str) -> None:
    cmd("import", "-window", window, str(folder / (name + ".png")))


def read(folder: Path, name: str) -> Image.Image:
    with Image.open(folder / (name + ".png")) as source:
        frame = source.convert("RGB")
    if frame.size != (WIDTH, HEIGHT):
        raise ValueError(f"{name}: screenshot dimensions {frame.size}, expected 1280x720")
    return frame


def matching(frame: Image.Image, rgb: tuple[int, int, int], rect) -> int:
    return sum(1 for px in frame.crop(rect).getdata()
               if max(abs(x - y) for x, y in zip(px, rgb)) <= TOLERANCE)


def sprite(frame: Image.Image, color: tuple[int, int, int], x: int, y: int) -> int:
    # Encompass the complete 36x36 unselected and 46x46 selected unit.
    px, py = GX + CELL * x, GY + CELL * y
    return matching(frame, color, (px + 6, py + 6, px + 66, py + 66))


def cursor(frame: Image.Image, x: int, y: int) -> int:
    px, py = GX + CELL * x, GY + CELL * y
    return matching(frame, CURSOR, (px, py, px + CELL, py + CELL))


def board_diff(a: Image.Image, b: Image.Image) -> int:
    delta = ImageChops.difference(a.crop(BOARD), b.crop(BOARD))
    return sum(1 for px in delta.getdata() if max(px) > 30)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(folder: Path) -> None:
    names = ("initial", "selected", "hover", "rejected", "moved",
             "reselected", "canceled", "returned")
    f = {name: read(folder, name) for name in names}
    require(sprite(f["initial"], HERO, 1, 2) > 1000,
            "initial real framebuffer lacks blue ally at 1,2")
    require(sprite(f["initial"], HERO, 2, 2) < 100,
            "ally already appears at destination before move")
    require(sprite(f["initial"], ENEMY, 6, 3) > 600,
            "initial real framebuffer lacks the enemy at 6,3")
    require(cursor(f["initial"], 1, 2) > 500,
            "initial cursor is not on the ally")
    require(sprite(f["selected"], HERO, 1, 2) >
            sprite(f["initial"], HERO, 1, 2) + 450,
            "A did not visibly select the hero")
    require(cursor(f["hover"], 2, 2) > 500 and
            cursor(f["hover"], 1, 2) < 120,
            "Right did not move the actual Switch cursor")
    require(sprite(f["hover"], HERO, 1, 2) > 1650,
            "hero moved before the second A confirmation")
    require(cursor(f["rejected"], 4, 2) > 500 and
            sprite(f["rejected"], HERO, 1, 2) > 1650 and
            sprite(f["rejected"], HERO, 4, 2) < 100,
            "out-of-range three-cell A incorrectly moved hero")
    require(sprite(f["moved"], HERO, 1, 2) < 100 and
            sprite(f["moved"], HERO, 2, 2) > 1000,
            "legal A destination did not move the real hero")
    require(sprite(f["reselected"], HERO, 2, 2) >
            sprite(f["moved"], HERO, 2, 2) + 450,
            "second A did not select hero at new position")
    require(sprite(f["canceled"], HERO, 2, 2) > 1000 and
            sprite(f["canceled"], HERO, 2, 2) + 450 <
            sprite(f["reselected"], HERO, 2, 2),
            "B cancellation did not visibly clear the selection")
    require(sprite(f["returned"], HERO, 1, 2) > 1000 and
            sprite(f["returned"], HERO, 2, 2) < 100,
            "second legal move did not return hero to 1,2")
    for name in names:
        require(sprite(f[name], ENEMY, 6, 3) > 600,
                f"{name}: original enemy disappeared unexpectedly")
    require(board_diff(f["initial"], f["returned"]) == 0,
            "the restored tactical board differs from the original pixels")
    print("VH_MAP02_NEXIUM_PROTOTYPE_MOVE_PASS boot=1 select=1 cursor=1 "
          "invalid_range=1 move=1 cancel=1 return=1 enemy_preserved=1 "
          "frame_replay=1 retail=0", flush=True)
    print(f"real screenshot measurements: initial_hero="
          f"{sprite(f['initial'], HERO, 1, 2)} selected_hero="
          f"{sprite(f['selected'], HERO, 1, 2)} destination_hero="
          f"{sprite(f['moved'], HERO, 2, 2)} "
          f"restored_board_diff={board_diff(f['initial'], f['returned'])}",
          flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.nro.is_file():
        parser.error("real built NRO artifact is required")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    executable = os.environ.get("NEXIUM_BIN")
    if not executable or not Path(executable).is_file():
        parser.error("NEXIUM_BIN must point to an existing emulator executable")
    with (args.evidence_dir / "nexium.log").open("wb") as emulator_log:
        process = subprocess.Popen([executable, str(args.nro.resolve())],
                                   stdout=emulator_log, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if process.poll() is not None:
                raise RuntimeError(f"NeXium exited before capture: {process.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible", "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("real NeXium window not found")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            snapshot(window, args.evidence_dir, "initial")
            press(window, "c")          # Switch A: select
            snapshot(window, args.evidence_dir, "selected")
            press(window, "Right")      # cursor to 2,2
            snapshot(window, args.evidence_dir, "hover")
            press(window, "Right")      # cursor to 3,2
            press(window, "Right")      # cursor to 4,2; beyond range 2
            press(window, "c")          # invalid A: should not move
            snapshot(window, args.evidence_dir, "rejected")
            press(window, "Left")       # 3,2
            press(window, "Left")       # 2,2
            press(window, "c")          # valid A: move hero
            snapshot(window, args.evidence_dir, "moved")
            press(window, "c")          # reselect hero
            snapshot(window, args.evidence_dir, "reselected")
            press(window, "x")          # Switch B: cancel
            snapshot(window, args.evidence_dir, "canceled")
            press(window, "c")          # reselect at 2,2
            press(window, "Left")       # 1,2
            press(window, "c")          # move back
            snapshot(window, args.evidence_dir, "returned")
            verify(args.evidence_dir)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
