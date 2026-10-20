#!/usr/bin/env python3
"""NeXium screenshot proof of visible guard-ready, armed and absorbed HUD.

This test drives a REAL Switch NRO with mapped controller input. It uses
stable second-arena HUD pixel regions, never game-memory manipulation.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import time
from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, BOARD, cmd, diff, read, tile, health_bar_pixels,
)

# Calibrated from the original full-resolution NeXium render: glyphs
# drawn at HUD y=582 appear in captured screenshots near y=566.
# Exclude the independent moving status bar around y=610.
GUARD_HUD = (965, 550, 1260, 588)


def verify(folder: Path):
    names = ("legacy", "primary", "before", "first_armed",
             "first_expired", "pre_attack", "second_armed",
             "blocked", "reset", "primary_return", "legacy_return")
    f = {n: read(folder, n) for n in names}
    original = f["before"]
    if not (tile(original, HERO, 1, 0) > 500 and
            tile(original, HERO, 1, 2) > 500):
        raise ValueError("second arena allies absent before defense")
    if diff(original, f["first_armed"], GUARD_HUD) < 60:
        raise ValueError("arming guard did not update visible HUD status")
    if diff(original, f["first_expired"], GUARD_HUD) > 20:
        raise ValueError("no-hit guard did not expire after opponent turn")
    if diff(f["pre_attack"], f["second_armed"], GUARD_HUD) < 60:
        raise ValueError("second guard command failed to visibly arm")
    if diff(f["pre_attack"], f["blocked"], GUARD_HUD) < 60:
        raise ValueError("actual absorbed hit not visible in status HUD")
    if diff(f["second_armed"], f["blocked"], GUARD_HUD) < 60:
        raise ValueError("armed status failed to change into blocked status")
    before_hp = health_bar_pixels(f["pre_attack"], 1, 0)
    after_hp = health_bar_pixels(f["blocked"], 1, 0)
    if not (before_hp >= 70 and 40 <= after_hp <= 78 and
            after_hp < before_hp):
        raise ValueError(f"real guard did not mitigate fourth enemy hit "
                         f"({before_hp} -> {after_hp})")
    if diff(original, f["reset"], BOARD) != 0:
        raise ValueError("Y reset changed the original second-arena board")
    if diff(original, f["reset"], GUARD_HUD) > 20:
        raise ValueError("Y reset did not restore GUARD READY status")
    if diff(f["primary"], f["primary_return"], BOARD) != 0:
        raise ValueError("original first arena was modified by guard HUD")
    if diff(f["legacy"], f["legacy_return"], BOARD) != 0:
        raise ValueError("original legacy MAP02 was modified by guard HUD")
    if diff(original, f["primary_return"], GUARD_HUD) < 60:
        raise ValueError("second-arena guard label leaked into first arena")
    print(
        "VH_MAP02_NEXIUM_GUARD_HUD_PASS ready=1 armed=1 "
        "no_hit_expired=1 actual_hit_blocked=1 reduced_damage=1 "
        "reset=1 first_arena_hidden=1 legacy_preserved=1 retail=0",
        flush=True,
    )
    print(f"guard HUD evidence: ready_to_armed="
          f"{diff(original, f['first_armed'], GUARD_HUD)} "
          f"armed_to_blocked="
          f"{diff(f['second_armed'], f['blocked'], GUARD_HUD)} "
          f"hp_before={before_hp} hp_after={after_hp} "
          f"reset_board_diff={diff(original, f['reset'], BOARD)} "
          f"legacy_diff={diff(f['legacy'], f['legacy_return'], BOARD)}",
          flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
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
            pad.press("q")
            pad.cursor = (1, 0)
            pad.snapshot("before")

            pad.goto(1, 2)
            pad.press("c")  # A third ally
            pad.press("x")  # B guards against next hit
            pad.snapshot("first_armed")
            pad.press("v")  # X: no enemy adjacent, expires harmlessly
            pad.snapshot("first_expired")
            pad.press("v")  # phase 2
            pad.press("v")  # phase 3
            pad.snapshot("pre_attack")
            pad.goto(1, 2)
            pad.press("c")
            pad.press("x")  # arm again for the real fourth-phase AI hit
            pad.snapshot("second_armed")
            pad.press("v")
            pad.snapshot("blocked")
            pad.press("z")
            pad.cursor = (1, 0)
            pad.snapshot("reset")
            pad.press("q")
            pad.cursor = (0, 0)
            pad.snapshot("primary_return")
            pad.toggle_eight()
            pad.press("q")
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
