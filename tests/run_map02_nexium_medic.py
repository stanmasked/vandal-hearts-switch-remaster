#!/usr/bin/env python3
"""Real NeXium: scene-B medic heals actual AI damage, without game-state writes."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import time

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD, cmd, diff,
    health_bar_pixels, read, tile
)


def verify(root: Path, first_damage_turn: int):
    names = ("legacy", "primary", "second", "full_hp_b",
             "wounded", "healed", "reset", "primary_return", "legacy_return")
    f = {name: read(root, name) for name in names}
    if not 1 <= first_damage_turn <= 8:
        raise ValueError("no bounded real enemy attack timeline")
    for y in range(4):
        if tile(f["second"], HERO, 1, y) < 500 or (
                tile(f["second"], ENEMY, 5, y) < 500):
            raise ValueError(f"second arena has missing allied/enemy unit row {y}")
    if diff(f["second"], f["full_hp_b"], BOARD) != 0:
        raise ValueError("B on full-HP ally changed gameplay")
    start_hp = health_bar_pixels(f["second"], 1, 0)
    wounded_hp = health_bar_pixels(f["wounded"], 1, 0)
    healed_hp = health_bar_pixels(f["healed"], 1, 0)
    if not (start_hp >= 70 and 0 < wounded_hp < start_hp and
            healed_hp > wounded_hp and healed_hp <= start_hp):
        raise ValueError(
            "real NeXium healing did not restore wounded ally HP "
            f"(before={start_hp}, damaged={wounded_hp}, healed={healed_hp})")
    if tile(f["healed"], ACTED, 1, 1) < 500:
        raise ValueError("medic did not spend an actual support action")
    if tile(f["healed"], HERO, 1, 0) < 500:
        raise ValueError("patient is no longer a live active ally")
    if diff(f["second"], f["reset"], BOARD) != 0:
        raise ValueError("Y reset did not restore second arena")
    if diff(f["primary"], f["primary_return"], BOARD) != 0:
        raise ValueError("field medic damaged first 4v4 arena")
    if diff(f["legacy"], f["legacy_return"], BOARD) != 0:
        raise ValueError("field medic damaged original MAP02")
    print(
        "VH_MAP02_NEXIUM_MEDIC_PASS second_arena=1 healthy_no_heal=1 "
        "natural_ai_damage=1 healer_b_action=1 healed=1 action_spent=1 "
        "reset=1 primary_preserved=1 legacy_preserved=1 retail=0",
        flush=True,
    )
    print(f"medic evidence: first_damage_turn={first_damage_turn} "
          f"hp_before={start_hp} hp_wounded={wounded_hp} hp_healed={healed_hp} "
          f"reset_diff={diff(f['second'], f['reset'], BOARD)} "
          f"primary_diff={diff(f['primary'], f['primary_return'], BOARD)} "
          f"legacy_diff={diff(f['legacy'], f['legacy_return'], BOARD)}",
          flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nro", required=True, type=Path)
    ap.add_argument("--evidence-dir", required=True, type=Path)
    args = ap.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as logfile:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=logfile, stderr=subprocess.STDOUT)
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
            pad.press("q")  # L: independently authored second arena, 4v4
            pad.cursor = (1, 0)
            pad.snapshot("second")

            pad.goto(1, 1)
            pad.press("c")  # select living medic
            pad.goto(1, 0)
            pad.press("x")  # B: full-HP ally -> original cancel, no healing
            pad.snapshot("full_hp_b")

            initial = health_bar_pixels(read(args.evidence_dir, "second"), 1, 0)
            if initial < 70:
                raise RuntimeError("initial HP bar is not visible in real capture")
            damage_turn = -1
            for i in range(1, 9):
                pad.press("v")  # X: real enemy pursuit/attack
                label = f"enemy_phase_{i}"
                pad.snapshot(label)
                current = read(args.evidence_dir, label)
                current_hp = health_bar_pixels(current, 1, 0)
                if 0 < current_hp < initial:
                    shutil.copyfile(args.evidence_dir / (label + ".png"),
                                    args.evidence_dir / "wounded.png")
                    damage_turn = i
                    break
                if tile(current, HERO, 1, 0) < 500:
                    raise RuntimeError(f"patient died before healing at phase {i}")
            if damage_turn < 0:
                raise RuntimeError("no natural enemy HP damage within eight turns")

            pad.goto(1, 1)
            pad.press("c")  # select medic after enemy phase reset
            pad.goto(1, 0)
            pad.press("x")  # B: heal actual wounded teammate at (1,0)
            pad.snapshot("healed")
            pad.press("z")  # Y resets scene-B 4v4 to exact pristine pixels
            pad.cursor = (1, 0)
            pad.snapshot("reset")
            pad.press("q")  # L switches to existing first 4v4
            pad.cursor = (0, 0)
            pad.snapshot("primary_return")
            pad.toggle_eight()
            pad.press("q")  # ensure legacy MAP 1
            pad.snapshot("legacy_return")
            verify(args.evidence_dir, damage_turn)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    main()
