#!/usr/bin/env python3
"""Select 4v4 -> 3v3 -> 1v4 -> 4v4 using real NeXium inputs.

Only authored asset-free fixtures. No emulator state injection is permitted.
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

ROSTER_LABEL = (975, 178, 1145, 209)


def verify(folder: Path):
    legacy, four, three, one, damaged, reset, four_again, back = (
        read(folder, name) for name in
        ("legacy", "four", "three", "one", "one_attack",
         "one_reset", "four_again", "legacy_return")
    )
    for y in range(4):
        if tile(four, HERO, 0, y) < 500 or tile(four, ENEMY, 1, y) < 500:
            raise ValueError(f"original capacity scene has missing row {y}")
        if tile(four_again, HERO, 0, y) < 500:
            raise ValueError("R did not cycle back to complete 4x4")
        if tile(one, ENEMY, 1, y) < 500:
            raise ValueError(f"1v4 scene enemy {y} missing")
    for y in range(3):
        if tile(three, HERO, 0, y) < 500 or tile(three, ENEMY, 1, y) < 500:
            raise ValueError("3v3 scene has missing active row")
    if tile(three, HERO, 0, 3) > 100 or tile(three, ENEMY, 1, 3) > 100:
        raise ValueError("3v3 still renders padded fourth slots")
    if tile(one, HERO, 0, 0) < 500 or any(
            tile(one, HERO, 0, y) > 100 for y in range(1, 4)):
        raise ValueError("1v4 still renders padded allied slots")
    if not (tile(damaged, ENEMY, 1, 0) < 100 and
            tile(damaged, ACTED, 0, 0) > 500 and
            tile(damaged, ENEMY, 1, 1) > 500):
        raise ValueError("1v4 combat selection did not work")
    if diff(one, reset, BOARD) != 0:
        raise ValueError("Y did not reset selected 1v4 composition")
    if diff(four, four_again, BOARD) != 0:
        raise ValueError("cycling to 4v4 did not restore original board")
    if diff(legacy, back, BOARD) != 0:
        raise ValueError("legacy MAP 1 not restored after varying rosters")
    if min(diff(four, three, ROSTER_LABEL),
           diff(three, one, ROSTER_LABEL),
           diff(one, four_again, ROSTER_LABEL)) < 10:
        raise ValueError("active-roster labels did not change with controls")
    print(
        "VH_MAP02_NEXIUM_VARIANTS_PASS default_4v4=1 three_by_three=1 "
        "one_by_four=1 legal_melee=1 reset_selected=1 "
        "roundtrip_4v4=1 legacy_restored=1 retail=0",
        flush=True,
    )
    print("NeXium variant evidence: roster_labels=3 "
          f"four_reset_diff={diff(four, four_again, BOARD)} "
          f"one_reset_diff={diff(one, reset, BOARD)} "
          f"legacy_diff={diff(legacy, back, BOARD)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    opts = parser.parse_args()
    opts.evidence_dir.mkdir(parents=True, exist_ok=True)
    with (opts.evidence_dir / "nexium.log").open("wb") as console:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(opts.nro.resolve())],
            stdout=console, stderr=subprocess.STDOUT,
        )
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"NeXium exited early: {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError("NeXium window not found")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            pad = NeXiumPad(window, opts.evidence_dir)
            pad.press("n")
            pad.snapshot("legacy")
            pad.toggle_eight()  # L+R enters old proven 4v4 by default
            pad.cursor = (0, 0)
            pad.snapshot("four")
            pad.press("e")      # R: switch to 3v3
            pad.snapshot("three")
            pad.press("e")      # R: switch to 1v4
            pad.snapshot("one")
            pad.press("c")      # select one remaining ally at (0,0)
            pad.goto(1, 0)
            pad.press("c")      # attack first enemy without premature victory
            pad.snapshot("one_attack")
            pad.press("z")      # reset stays on 1v4
            pad.snapshot("one_reset")
            pad.press("e")      # R wraps to original 4v4
            pad.snapshot("four_again")
            pad.toggle_eight()
            pad.press("q")      # previous L+R may have changed legacy map
            pad.snapshot("legacy_return")
            verify(opts.evidence_dir)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    main()
