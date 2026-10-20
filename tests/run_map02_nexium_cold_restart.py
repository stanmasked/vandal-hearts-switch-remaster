#!/usr/bin/env python3
"""Cold-restart consistency of the original asset-free MAP02 tactical prototype.

Starts two genuinely distinct NeXium OS processes and replays guard -> AI hit
-> medic -> Y reset -> bow -> Y reset -> legacy return in each. No state
injection, no synthetic evidence, no retail PlayStation assets.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import ImageChops

from run_map02_nexium_4v4 import (
    NeXiumPad, HERO, ENEMY, ACTED, BOARD,
    cmd, diff, health_bar_pixels, read, tile,
)
from run_map02_nexium_guard_hud import GUARD_HUD

STAGES = (
    "legacy", "primary", "second", "pre_hit", "guard_armed", "guard_hit",
    "medic_healed", "reset", "bow_ready", "bow_hit", "bow_reset",
    "legacy_return",
)


def identical_pixels(a, b, rect) -> bool:
    """Require exact RGB equality; the semantic diff() permits channel noise <=30."""
    return ImageChops.difference(a.crop(rect), b.crop(rect)).getbbox() is None


def verify(folder: Path) -> None:
    record_path = folder / "processes.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict)
            or record.get("emulator_processes") != 2
            or type(record.get("process_ids")) is not list
            or len(record["process_ids"]) != 2
            or any(type(pid) is not int or pid <= 0 for pid in record["process_ids"])
            or record["process_ids"][0] == record["process_ids"][1]
            or record.get("first_process_exited_before_second") is not True):
        raise ValueError("two separately terminated real emulator processes not proven")

    frames = {
        boot: {stage: read(folder, f"boot{boot}_{stage}") for stage in STAGES}
        for boot in (1, 2)
    }
    results = []
    for boot in (1, 2):
        f = frames[boot]
        base = f["second"]
        for y in range(4):
            if tile(base, HERO, 1, y) < 500 or tile(base, ENEMY, 5, y) < 500:
                raise ValueError(f"boot {boot}: original second arena spawn missing {y}")
        initial_hp = health_bar_pixels(base, 1, 0)
        pre_hp = health_bar_pixels(f["pre_hit"], 1, 0)
        guarded_hp = health_bar_pixels(f["guard_hit"], 1, 0)
        healed_hp = health_bar_pixels(f["medic_healed"], 1, 0)
        if not (initial_hp >= 70 and pre_hp == initial_hp
                and 40 <= guarded_hp <= 78 and guarded_hp < pre_hp
                and healed_hp == initial_hp):
            raise ValueError(
                f"boot {boot}: real guard/medic damage mismatch "
                f"{initial_hp}->{pre_hp}->{guarded_hp}->{healed_hp}")
        if (tile(f["guard_armed"], ACTED, 1, 2) < 500
                or diff(f["pre_hit"], f["guard_armed"], GUARD_HUD) < 60
                or diff(f["guard_armed"], f["guard_hit"], GUARD_HUD) < 60):
            raise ValueError(f"boot {boot}: guard READY/ARMED/BLOCKED failed")
        if tile(f["medic_healed"], ACTED, 1, 1) < 500:
            raise ValueError(f"boot {boot}: medic did not spend action")
        if diff(base, f["reset"], BOARD) != 0:
            raise ValueError(f"boot {boot}: first Y reset left stale combat state")
        ready, shot = f["bow_ready"], f["bow_hit"]
        if not (tile(ready, HERO, 2, 0) > 500
                and tile(ready, ENEMY, 4, 0) > 500
                and tile(shot, ACTED, 2, 0) > 500
                and tile(shot, ENEMY, 4, 0) < 100
                and diff(ready, shot, BOARD) > 500):
            raise ValueError(f"boot {boot}: fresh bow action did not defeat target")
        if diff(base, f["bow_reset"], BOARD) != 0:
            raise ValueError(f"boot {boot}: second Y reset failed")
        if diff(f["legacy"], f["legacy_return"], BOARD) != 0:
            raise ValueError(f"boot {boot}: old authored MAP02 changed")
        results.append((initial_hp, guarded_hp, healed_hp))

    # Stronger than two green replays: require identical visible game states
    # at EVERY shared checkpoint, not just expected hit/heal classifications.
    for stage in STAGES:
        if not identical_pixels(frames[1][stage], frames[2][stage], BOARD):
            raise ValueError(f"cold boot image non-deterministic on BOARD: {stage}")
    for stage in ("second", "pre_hit", "guard_armed", "guard_hit",
                  "medic_healed", "reset", "bow_ready", "bow_hit", "bow_reset"):
        if not identical_pixels(frames[1][stage], frames[2][stage], GUARD_HUD):
            raise ValueError(f"cold boot image non-deterministic on guard HUD: {stage}")

    print(
        "VH_MAP02_NEXIUM_COLD_RESTART_PASS emulator_processes=2 "
        "different_pids=1 first_exited_before_second=1 guard_both=1 "
        "medic_both=1 bow_both=1 two_resets_each=1 "
        "board_determinism=1 hud_determinism=1 legacy_preserved=1 retail=0",
        flush=True)
    print(
        "cold-restart evidence: "
        f"boot1_hp={results[0][0]}->{results[0][1]}->{results[0][2]} "
        f"boot2_hp={results[1][0]}->{results[1][1]}->{results[1][2]} "
        f"checkpoints={len(STAGES)} board_diff=0 guard_hud_diff=0 "
        f"boot1_pid={record['process_ids'][0]} boot2_pid={record['process_ids'][1]}",
        flush=True)


def replay(pad: NeXiumPad, label: str) -> None:
    def shot(name: str):
        pad.snapshot(label + "_" + name)

    pad.press("n")                # MINUS: approved legacy MAP02
    shot("legacy")
    pad.toggle_eight()             # L+R: independent expanded battle
    pad.cursor = (0, 0)
    shot("primary")
    pad.press("q")                # L: arena B
    pad.cursor = (1, 0)
    shot("second")

    for _ in range(3):
        pad.press("v")            # X: real enemy pursuit
    shot("pre_hit")
    pad.goto(1, 2)
    pad.press("c")                # A: third allied character
    pad.press("x")                # B: activate guard
    shot("guard_armed")
    pad.press("v")                # fourth AI turn deals mitigated damage
    shot("guard_hit")

    pad.goto(1, 1)
    pad.press("c")                # select medic
    pad.goto(1, 0)
    pad.press("x")                # heal same actually wounded ally
    shot("medic_healed")
    pad.press("z")                # Y: first exact battle reset
    pad.cursor = (1, 0)
    shot("reset")

    pad.press("c")                # A: fresh archer
    pad.goto(2, 0)
    pad.press("c")                # A: legal move
    pad.press("v")                # X: natural enemy approach
    shot("bow_ready")
    pad.press("c")                # A: select archer
    pad.goto(4, 0)
    pad.press("x")                # B: successful two-tile ranged shot
    shot("bow_hit")
    pad.press("z")                # Y: exact second reset
    pad.cursor = (1, 0)
    shot("bow_reset")
    pad.toggle_eight()             # L+R exit expanded
    pad.press("q")                # approved legacy Map 1
    shot("legacy_return")


def run_once(executable: Path, folder: Path, boot: int) -> int:
    with (folder / f"boot{boot}_nexium.log").open("wb") as logfile:
        proc = subprocess.Popen(
            [os.environ["NEXIUM_BIN"], str(executable.resolve())],
            stdout=logfile, stderr=subprocess.STDOUT)
        try:
            time.sleep(30)
            if proc.poll() is not None:
                raise RuntimeError(f"boot {boot}: NeXium exited early {proc.returncode}")
            windows = cmd("xdotool", "search", "--onlyvisible",
                          "--name", "NeXium").splitlines()
            if not windows:
                raise RuntimeError(f"boot {boot}: no NeXium window")
            window = windows[-1]
            try:
                cmd("xdotool", "windowfocus", "--sync", window, timeout=3)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            replay(NeXiumPad(window, folder), f"boot{boot}")
            return proc.pid
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    first = run_once(args.nro, args.evidence_dir, 1)
    # Avoid accidentally reusing a remaining NeXium window from boot 1.
    try:
        old_windows = cmd("xdotool", "search", "--onlyvisible", "--name",
                          "NeXium", timeout=3).splitlines()
    except subprocess.CalledProcessError:
        old_windows = []
    if old_windows:
        raise RuntimeError("first emulator window survived process termination")
    second = run_once(args.nro, args.evidence_dir, 2)
    (args.evidence_dir / "processes.json").write_text(
        json.dumps({
            "emulator_processes": 2,
            "process_ids": [first, second],
            "first_process_exited_before_second": True,
        }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    verify(args.evidence_dir)


if __name__ == "__main__":
    main()
