#!/usr/bin/env python3
"""NeXium proof: third ally's B squad guard prevents 1 HP of a real AI hit.

Two independent routes are played from the same original scene-B map:
A) four X enemy phases without any guard; B) reset, three X phases,
   A-select third ally + B guard + X fourth phase, followed by medic B heal.
Images are genuine NeXium screenshot captures and not injected state.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import time
from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD,
    cmd, count, diff, health_bar_pixels, read, tile,
)


def verify(folder: Path):
    names = ("legacy", "primary", "second", "after_three",
             "unguarded", "reset_baseline", "guard_ready",
             "guard_armed", "guarded", "healed", "final_reset",
             "primary_return", "legacy_return")
    f = {n: read(folder, n) for n in names}
    for y in range(4):
        if tile(f["second"], HERO, 1, y) < 500 or (
                tile(f["second"], ENEMY, 5, y) < 500):
            raise ValueError(f"second arena initial team missing row {y}")
    hp0 = health_bar_pixels(f["second"], 1, 0)
    hp_before = health_bar_pixels(f["after_three"], 1, 0)
    hp_regular = health_bar_pixels(f["unguarded"], 1, 0)
    hp_guard = health_bar_pixels(f["guarded"], 1, 0)
    hp_healed = health_bar_pixels(f["healed"], 1, 0)
    if not (hp0 >= 70 and hp_before == hp0):
        raise ValueError(f"enemy attacked too early or initial HP unreadable "
                         f"(initial={hp0}, before={hp_before})")
    if not (0 < hp_regular < hp_guard < hp0):
        raise ValueError(f"real squad guard failed to prevent part of enemy "
                         f"damage (unguarded={hp_regular}, guarded={hp_guard}, "
                         f"original={hp0})")
    if hp_healed != hp0:
        raise ValueError(f"actual medic follow-up failed to restore HP "
                         f"({hp_guard}->{hp_healed}; original={hp0})")
    if diff(f["after_three"], f["guard_ready"], BOARD) != 0:
        raise ValueError("reset-and-three-enemy-phases are nondeterministic")
    if tile(f["guard_armed"], ACTED, 1, 2) < 500:
        raise ValueError("third ally did not spend their guard action")
    if tile(f["guarded"], HERO, 1, 2) < 500:
        raise ValueError("third ally did not reset action after enemy phase")
    if tile(f["healed"], ACTED, 1, 1) < 500:
        raise ValueError("medic did not spend action after real guarded damage")
    if diff(f["second"], f["reset_baseline"], BOARD) != 0:
        raise ValueError("first Y reset did not restore second 4v4 map")
    if diff(f["second"], f["final_reset"], BOARD) != 0:
        raise ValueError("final Y reset did not restore second 4v4 map")
    if diff(f["primary"], f["primary_return"], BOARD) != 0:
        raise ValueError("guard affected first original expanded arena")
    if diff(f["legacy"], f["legacy_return"], BOARD) != 0:
        raise ValueError("guard affected approved original legacy MAP02")
    print("VH_MAP02_NEXIUM_GUARD_PASS third_ally=1 "
          "real_ai_comparison=1 damage_reduced=1 medic_followup=1 "
          "action_spent=1 deterministic_replay=1 reset=1 "
          "primary_preserved=1 legacy_preserved=1 retail=0", flush=True)
    print(f"guard evidence: initial_hp={hp0} before_hit={hp_before} "
          f"unguarded_hp={hp_regular} guarded_hp={hp_guard} "
          f"medic_healed_hp={hp_healed} "
          f"deterministic_diff={diff(f['after_three'], f['guard_ready'], BOARD)} "
          f"reset_diff={diff(f['second'], f['final_reset'], BOARD)} "
          f"primary_diff={diff(f['primary'], f['primary_return'], BOARD)} "
          f"legacy_diff={diff(f['legacy'], f['legacy_return'], BOARD)}",
          flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nro", required=True, type=Path)
    ap.add_argument("--evidence-dir", required=True, type=Path)
    args = ap.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (args.evidence_dir / "nexium.log").open("wb") as output:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(args.nro.resolve())],
            stdout=output, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited early ({proc.returncode})")
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
            pad.snapshot("primary")
            pad.press("q")        # L switches into expanded arena B
            pad.cursor = (1, 0)
            pad.snapshot("second")

            for _ in range(3):
                pad.press("v")    # real X: enemy pursuit phases 1..3
            pad.snapshot("after_three")
            pad.press("v")        # phase 4, no guard: 2HP enemy strike
            pad.snapshot("unguarded")
            pad.press("z")        # Y resets exact second-arena scene
            pad.cursor = (1, 0)
            pad.snapshot("reset_baseline")

            for _ in range(3):
                pad.press("v")
            pad.snapshot("guard_ready")
            pad.goto(1, 2)
            pad.press("c")        # A selects third ally
            pad.press("x")        # B arms one-hit squad shield
            pad.snapshot("guard_armed")
            pad.press("v")        # X: same fourth AI attack, now -1 damage
            pad.snapshot("guarded")

            pad.goto(1, 1)
            pad.press("c")        # A selects the existing medic
            pad.goto(1, 0)
            pad.press("x")        # B heals archer after shield mitigated hit
            pad.snapshot("healed")
            pad.press("z")        # Y restores current second 4v4 map
            pad.cursor = (1, 0)
            pad.snapshot("final_reset")
            pad.press("q")
            pad.cursor = (0, 0)
            pad.snapshot("primary_return")
            pad.toggle_eight()
            pad.press("q")        # previous approved legacy Map 1
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
