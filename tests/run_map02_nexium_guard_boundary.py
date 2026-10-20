#!/usr/bin/env python3
"""Real NeXium controller + screenshot proof: guard clears at scene/roster boundaries.

Uses only the existing mapped-controller X11 driver and captured PNG pixels.
The authored MAP02 demo is NOT the PlayStation original.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import time

from run_map02_nexium_4v4 import NeXiumPad, HERO, BOARD, cmd, diff, read, tile
from run_map02_nexium_guard_hud import GUARD_HUD

NAMES = (
    "legacy", "primary", "ready", "armed_before_scene", "primary_after_arm",
    "ready_after_scene", "armed_before_roster", "three_allies",
    "one_ally", "four_allies", "armed_before_exit", "legacy_after_exit",
    "primary_reenter", "ready_reenter", "enemy_phase_reenter",
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def verify(folder: Path) -> None:
    frames = {name: read(folder, name) for name in NAMES}
    ready = frames["ready"]
    require(tile(ready, HERO, 1, 0) > 500 and
            tile(ready, HERO, 1, 2) > 500,
            "second arena 4v4 baseline allies not present")
    require(tile(frames["three_allies"], HERO, 1, 2) > 500,
            "3v3 roster lost third ally unexpectedly")
    require(tile(frames["one_ally"], HERO, 1, 2) < 100 and
            tile(frames["one_ally"], HERO, 1, 0) > 500,
            "1v4 roster failed to remove third ally")
    require(tile(frames["four_allies"], HERO, 1, 2) > 500,
            "return to 4v4 failed to restore third ally")

    # A visually armed defense must be cleared by each independent switch.
    for armed in ("armed_before_scene", "armed_before_roster",
                  "armed_before_exit"):
        require(diff(ready, frames[armed], GUARD_HUD) >= 60,
                f"{armed}: real B guard did not visibly arm")
    for cleared in ("ready_after_scene", "three_allies", "four_allies",
                    "ready_reenter", "enemy_phase_reenter"):
        require(diff(ready, frames[cleared], GUARD_HUD) <= 20,
                f"{cleared}: a previous guard state leaked across transition")
    require(diff(ready, frames["one_ally"], GUARD_HUD) >= 60,
            "1v4 did not display unavailable guard state")

    # Scene 0 and legacy demo must never expose second-arena guard status.
    for scene0 in ("primary", "primary_after_arm", "primary_reenter"):
        require(diff(ready, frames[scene0], GUARD_HUD) >= 60,
                f"{scene0}: guard UI leaked into the first arena")
    require(diff(frames["primary"], frames["primary_after_arm"], BOARD) == 0 and
            diff(frames["primary"], frames["primary_reenter"], BOARD) == 0,
            "scene 0 board changed following guarded scene transition")
    require(diff(frames["legacy"], frames["legacy_after_exit"], BOARD) == 0,
            "legacy MAP02 board changed following guarded exit")
    for reset in ("ready_after_scene", "four_allies", "ready_reenter"):
        require(diff(ready, frames[reset], BOARD) == 0,
                f"{reset}: second arena did not restore original 4v4 board")
    require(diff(frames["enemy_phase_reenter"], ready, BOARD) > 100,
            "real X enemy phase had no observable tactical board effect")

    print(
        "VH_MAP02_NEXIUM_GUARD_BOUNDARY_PASS arming=1 scene_reset=1 "
        "roster_3v3=1 roster_1v4_unavailable=1 roster_4v4_reset=1 "
        "legacy_exit=1 reentry=1 enemy_phase_no_leak=1 "
        "first_arena_preserved=1 retail=0",
        flush=True,
    )
    print(
        "actual NeXium PNG comparison: ready_armed="
        f"{diff(ready, frames['armed_before_scene'], GUARD_HUD)} "
        f"ready_three={diff(ready, frames['three_allies'], GUARD_HUD)} "
        f"ready_unavailable={diff(ready, frames['one_ally'], GUARD_HUD)} "
        f"reset_board_diff={diff(ready, frames['ready_reenter'], BOARD)} "
        f"legacy_diff={diff(frames['legacy'], frames['legacy_after_exit'], BOARD)}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.nro.is_file():
        parser.error("a real built NRO is required")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    executable = os.environ.get("NEXIUM_BIN", "")
    if not executable or not Path(executable).is_file():
        parser.error("NEXIUM_BIN must be the downloaded, SHA-pinned NeXium")
    with (args.evidence_dir / "nexium.log").open("wb") as log:
        process = subprocess.Popen(
            [executable, str(args.nro.resolve())],
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if process.poll() is not None:
                raise RuntimeError(f"NeXium exited early: {process.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium X11 window is missing")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

            pad = NeXiumPad(window, args.evidence_dir)
            pad.press("n")  # MINUS opens legacy authored 2v2 battle
            pad.snapshot("legacy")
            pad.toggle_eight()
            pad.cursor = (0, 0)
            pad.snapshot("primary")
            pad.press("q")  # L enters independent secondary 4v4 arena
            pad.cursor = (1, 0)
            pad.snapshot("ready")

            pad.goto(1, 2)
            pad.press("c")  # A selects third ally
            pad.press("x")  # B arms guard
            pad.snapshot("armed_before_scene")
            pad.press("q")  # L returns to primary arena, dropping guard
            pad.cursor = (0, 0)
            pad.snapshot("primary_after_arm")
            pad.press("q")  # L returns to fresh second arena 4v4
            pad.cursor = (1, 0)
            pad.snapshot("ready_after_scene")

            pad.goto(1, 2)
            pad.press("c")
            pad.press("x")
            pad.snapshot("armed_before_roster")
            pad.press("e")  # R selects second-arena 3v3 roster, reset guard
            pad.cursor = (1, 0)
            pad.snapshot("three_allies")
            pad.press("e")  # 1v4, no third ally: GUARD UNAVAILABLE
            pad.cursor = (1, 0)
            pad.snapshot("one_ally")
            pad.press("e")  # 4v4 restored; fresh READY state
            pad.cursor = (1, 0)
            pad.snapshot("four_allies")

            pad.goto(1, 2)
            pad.press("c")
            pad.press("x")
            pad.snapshot("armed_before_exit")
            pad.toggle_eight()  # Back to original authored 2v2 mode
            # L+R's initial L keydown can change original scenario while
            # the chord is being formed, as in proven 4v4 NeXium routes.
            pad.press("q")  # Explicitly restore original MAP 1
            pad.cursor = (0, 0)
            pad.snapshot("legacy_after_exit")
            pad.toggle_eight()  # Reenter expanded first arena
            pad.cursor = (0, 0)
            pad.snapshot("primary_reenter")
            pad.press("q")
            pad.cursor = (1, 0)
            pad.snapshot("ready_reenter")
            pad.press("v")  # Real X enemy phase with *no* inherited guard
            pad.snapshot("enemy_phase_reenter")
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
