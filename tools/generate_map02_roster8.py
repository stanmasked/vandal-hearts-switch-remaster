#!/usr/bin/env python3
"""Compile independent asset-free MAP02 capacity-smoke JSON to an opt-in C roster.

Not a retail Vandal Hearts MAP02 importer. Not included by the active Switch NRO.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/map02_roster8_4v4.json"
FIXTURE_ID = "map02_capacity_smoke_4v4"
SYMBOL = "VH_MAP02_ROSTER8_SMOKE"


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def exact_keys(obj, expected, label):
    if type(obj) is not dict or set(obj) != set(expected):
        raise ValueError(f"{label}: expected exactly {sorted(expected)}")
    return obj


def number(v, lo, hi, label):
    if type(v) is not int or v < lo or v > hi:
        raise ValueError(f"{label}: require integer {lo}..{hi}")
    return v


def point(v, label):
    if type(v) is not list or len(v) != 2:
        raise ValueError(f"{label}: require [x,y]")
    return (number(v[0], 0, 7, label + ".x"),
            number(v[1], 0, 5, label + ".y"))


def parse(data):
    d = exact_keys(data, {"schema_version", "id", "board", "allies",
                          "enemies", "cursor"}, "root")
    number(d["schema_version"], 2, 2, "schema_version")
    if type(d["id"]) is not str or d["id"] != FIXTURE_ID:
        raise ValueError("unsupported independent fixture ID")
    board = exact_keys(d["board"], {"width", "height", "blocked"}, "board")
    number(board["width"], 8, 8, "board.width")
    number(board["height"], 6, 6, "board.height")
    if type(board["blocked"]) is not list:
        raise ValueError("board.blocked must be a list")
    walls = [0] * 6
    for i, tile in enumerate(board["blocked"]):
        x, y = point(tile, f"board.blocked[{i}]")
        if walls[y] & (1 << x):
            raise ValueError("duplicate blocked tile")
        walls[y] |= 1 << x
    used = set()
    groups = []
    for side in ("allies", "enemies"):
        roster = d[side]
        if type(roster) is not list or not 1 <= len(roster) <= 4:
            raise ValueError(f"{side}: require 1..4 active units")
        actors = []
        for i, actor in enumerate(roster):
            actor = exact_keys(actor, {"x", "y", "hp"}, f"{side}[{i}]")
            x, y = point([actor["x"], actor["y"]], f"{side}[{i}]")
            hp = number(actor["hp"], 1, 20, f"{side}[{i}].hp")
            if (x, y) in used or walls[y] & (1 << x):
                raise ValueError("overlapping or blocked spawn")
            used.add((x, y))
            actors.append((x, y, hp, 0))
        actors.extend([(0, 0, 0, 0)] * (4 - len(roster)))
        groups.append(actors)
    cursor = point(d["cursor"], "cursor")
    if cursor != groups[0][0][:2]:
        raise ValueError("cursor must start on first ally")
    return walls, groups[0] + groups[1], len(d["allies"]), len(d["enemies"]), cursor


def render(data):
    walls, units, allies, enemies, cursor = parse(data)
    actor_lines = ", ".join("{{{}, {}, {}, {}}}".format(*u) for u in units)
    wall_line = ", ".join(f"0x{x:02X}" for x in walls)
    return (
        "/* GENERATED independent MAP02 capacity smoke; no retail assets. */\n"
        "#ifndef VH_MAP02_ROSTER8_SMOKE_H\n"
        "#define VH_MAP02_ROSTER8_SMOKE_H\n"
        f"static const VhRoster8 {SYMBOL} = {{\n"
        f"    {{{actor_lines}}},\n"
        f"    {{{wall_line}}},\n"
        f"    {allies}, {enemies},\n"
        f"    {cursor[0]}, {cursor[1]}\n"
        "};\n"
        "#endif /* VH_MAP02_ROSTER8_SMOKE_H */\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_pairs)
        result = render(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"MAP02 roster8 source error: {exc}", file=sys.stderr)
        return 1
    print("VH_MAP02_ROSTER8_GENERATOR_PASS max_per_side=4 independent_fixture=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
