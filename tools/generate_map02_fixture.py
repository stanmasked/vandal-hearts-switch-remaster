#!/usr/bin/env python3
"""Validate an authored MAP02 fixture JSON and generate a portable C header.

No original Vandal Hearts PS1 content. This intentionally restricts the
prototype to the existing 8x6, two-allies/two-enemies native battle engine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/map02_fixture.json"
DEFAULT_OUTPUT = ROOT / "source/map02_encounter_data.h"
SCENARIO_HEADERS = {
    "map02_original_fixture_a": ("map02_fixture.json", "VH_MAP02_ENCOUNTER_DATA_H", "VH_MAP02_DEFAULT_SCENARIO"),
    "map02_original_fixture_b": ("map02_fixture_b.json", "VH_MAP02_ENCOUNTER_B_DATA_H", "VH_MAP02_SECOND_SCENARIO"),
}


def objects_unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def keys(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label}: expected exactly {sorted(expected)}")
    return value


def integer(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label}: expected integer in [{low},{high}]")
    return value


def location(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label}: expected [x,y]")
    return (
        integer(value[0], 0, 7, label + ".x"),
        integer(value[1], 0, 5, label + ".y"),
    )


def validated(data: object) -> dict[str, object]:
    d = keys(data, {"schema_version", "id", "board", "allies", "enemies",
                    "cursor", "rules", "events"}, "root")
    if integer(d["schema_version"], 1, 1, "schema_version") != 1:
        raise ValueError("unsupported schema")
    if type(d["id"]) is not str or d["id"] not in SCENARIO_HEADERS:
        raise ValueError("only approved, independently-authored fixture IDs are supported")
    board = keys(d["board"], {"width", "height", "blocked"}, "board")
    integer(board["width"], 8, 8, "board.width")
    integer(board["height"], 6, 6, "board.height")
    if not isinstance(board["blocked"], list):
        raise ValueError("board.blocked must be a list")
    walls = [0] * 6
    for ix, tile in enumerate(board["blocked"]):
        x, y = location(tile, f"board.blocked[{ix}]")
        if walls[y] & (1 << x):
            raise ValueError(f"duplicate blocked tile ({x},{y})")
        walls[y] |= 1 << x
    units: list[tuple[int, int, int]] = []
    occupied: set[tuple[int, int]] = set()
    counts: dict[str, int] = {}
    for faction in ("allies", "enemies"):
        roster = d[faction]
        if not isinstance(roster, list) or not 1 <= len(roster) <= 2:
            raise ValueError(f"{faction}: require one or two active units")
        counts[faction] = len(roster)
        for ix, actor in enumerate(roster):
            actor = keys(actor, {"x", "y", "hp"}, f"{faction}[{ix}]")
            x, y = location([actor["x"], actor["y"]], f"{faction}[{ix}]")
            hp = integer(actor["hp"], 1, 20, f"{faction}[{ix}].hp")
            if walls[y] & (1 << x) or (x, y) in occupied:
                raise ValueError("unit starts on blocked or occupied tile")
            units.append((x, y, hp))
            occupied.add((x, y))
        # Fixed four-slot C storage: absent combatants are strictly inert.
        for _ in range(2 - counts[faction]):
            units.append((0, 0, 0))
    cursor = location(d["cursor"], "cursor")
    if cursor != units[0][:2]:
        raise ValueError("default cursor must begin on the first allied unit")
    rules = keys(d["rules"], {"move_range", "attack_damage"}, "rules")
    move = integer(rules["move_range"], 1, 7, "rules.move_range")
    damage = integer(rules["attack_damage"], 1, 20, "rules.attack_damage")
    events = d["events"]
    if not isinstance(events, list) or len(events) != 2:
        raise ValueError("exactly two win/lose events are required")
    mapping = {
        ("all_enemies_defeated", "victory"): ("VH_BEVENT_ENEMIES_DOWN", "VH_BWIN"),
        ("all_allies_defeated", "defeat"): ("VH_BEVENT_ALLIES_DOWN", "VH_BLOSS"),
    }
    parsed_events: list[tuple[str, str]] = []
    used: set[tuple[str, str]] = set()
    for ix, event in enumerate(events):
        event = keys(event, {"when", "result"}, f"events[{ix}]")
        identity = (event["when"], event["result"])
        if identity not in mapping or identity in used:
            raise ValueError("invalid, duplicated or mismatched outcome event")
        parsed_events.append(mapping[identity])
        used.add(identity)
    if len(used) != 2:
        raise ValueError("both win and lose outcome events must be present")
    return {"id": d["id"], "walls": walls, "units": units, "cursor": cursor,
            "move": move, "damage": damage, "events": parsed_events,
            "ally_count": counts["allies"], "enemy_count": counts["enemies"]}


def render(data: object) -> str:
    scene = validated(data)
    walls = ", ".join(f"0x{x:02X}" for x in scene["walls"])
    actors = ", ".join(f"{{{x}, {y}, {hp}, 0}}" for x, y, hp in scene["units"])
    cursor_x, cursor_y = scene["cursor"]
    events = ", ".join(f"{{{trigger}, {outcome}}}"
                       for trigger, outcome in scene["events"])
    file_name, guard, identifier = SCENARIO_HEADERS[scene["id"]]
    return (
        f"/* GENERATED by tools/generate_map02_fixture.py from data/{file_name}. */\n"
        "/* Independent asset-free tactical fixture: NOT retail Vandal Hearts MAP02. */\n"
        f"#ifndef {guard}\n"
        f"#define {guard}\n"
        f"static const VhBattleScenario {identifier} = {{\n"
        f"    {{{walls}}},\n"
        f"    {{{actors}}},\n"
        f"    {cursor_x}, {cursor_y},\n"
        f"    {scene['move']}, {scene['damage']},\n"
        f"    {{{events}}},\n"
        "    2,\n"
        f"    {scene['ally_count']}, {scene['enemy_count']}\n"
        "};\n"
        f"#endif /* {guard} */\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--all", action="store_true",
                        help="generate or verify BOTH approved fixture headers")
    parser.add_argument("--check", action="store_true",
                        help="refuse a stale generated header; never modify it")
    opts = parser.parse_args()
    try:
        pairs = ((ROOT / "data" / fname, ROOT / "source" /
                  ("map02_encounter_data.h" if sid.endswith("_a") else "map02_encounter_b_data.h"))
                 for sid, (fname, _, _) in SCENARIO_HEADERS.items()) if opts.all else ((opts.input, opts.output),)
        for input_path, output_path in pairs:
            data = json.loads(input_path.read_text(encoding="utf-8"),
                              object_pairs_hook=objects_unique)
            rendered = render(data)
            if opts.all:
                expected_id = "map02_original_fixture_a" if input_path.name == "map02_fixture.json" else "map02_original_fixture_b"
                if data.get("id") != expected_id:
                    raise ValueError(f"fixture ID/file mismatch: {input_path.name}")
            if opts.check:
                if not output_path.is_file() or output_path.read_text(encoding="utf-8") != rendered:
                    raise ValueError(f"generated MAP02 header is stale: {output_path}")
            else:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(rendered, encoding="utf-8")
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"MAP02 encounter error: {exc}", file=sys.stderr)
        return 1
    print("VH_MAP02_SCENARIO_DATA_PASS board=8x6 units=4 events=2 authored_only=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
