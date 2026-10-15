#!/usr/bin/env python3
"""Validate captured map-11 (resource M_MAP02) runtime face GFX observations.

Input: JSON array or JSON Lines of objects with integer z,x,face,gfx and string stage.
Stage is 'post_load' or 'draw'. gfx is the *global* index (after +400).
This is an observational consistency checker, not a proof of visual correctness.
"""
import argparse
import json
from pathlib import Path

TARGETS = {(8, 19, 0): (641, 498), (11, 11, 0): (643, 550)}
STAGES = {"post_load", "draw"}


def evaluate_trace(entries):
    if not isinstance(entries, list):
        raise ValueError("trace must be a JSON list")
    found = {}
    errors = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {i}: expected object")
            continue
        if any(type(entry.get(k)) is not int for k in ("z", "x", "face", "gfx")):
            errors.append(f"entry {i}: z,x,face,gfx must be integers")
            continue
        pos = (entry["z"], entry["x"], entry["face"])
        if pos not in TARGETS:
            continue
        stage = entry.get("stage")
        if stage not in STAGES:
            errors.append(f"entry {i}: invalid stage")
            continue
        if (pos, stage) in found:
            errors.append(f"duplicate observation for {pos} at {stage}")
            continue
        found[(pos, stage)] = entry["gfx"]
        if entry["gfx"] not in TARGETS[pos]:
            errors.append(f"unexpected GFX {entry['gfx']} for {pos} at {stage}")
    rows = []
    for pos, (prs, dat) in TARGETS.items():
        after = found.get((pos, "post_load"))
        drawn = found.get((pos, "draw"))
        if after is None:
            errors.append(f"missing post_load observation for {pos}")
        if drawn is None:
            errors.append(f"missing draw observation for {pos}")
        rows.append({
            "z": pos[0], "x": pos[1], "face": pos[2],
            "prs_gfx": prs, "dat_gfx": dat,
            "post_load_gfx": after, "draw_gfx": drawn,
            "post_load_variant": "PRS" if after == prs else "DAT" if after == dat else None,
            "draw_variant": "PRS" if drawn == prs else "DAT" if drawn == dat else None,
        })
        if after is not None and drawn is not None and after != drawn:
            errors.append(f"GFX changed between loading and drawing for {pos}")
    return {"observations": rows, "errors": errors,
            "warning": "GFX identity alone cannot prove visually correct texture or tpage/CLUT state."}



def parse_trace_text(text):
    """Accept a JSON array or a JSON Lines stream of observation objects."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        entries = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON Lines entry at line {line_number}: {exc.msg}") from exc
        if not entries:
            raise ValueError("trace contains no observations")
        data = entries
    if not isinstance(data, list):
        raise ValueError("trace must be a JSON array or JSON Lines objects")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSON array of captured runtime observations")
    args = parser.parse_args()
    try:
        result = evaluate_trace(parse_trace_text(args.trace.read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
