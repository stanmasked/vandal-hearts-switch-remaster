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
    draw_metadata = {}
    seen_draw_frames = set()
    draw_frame_mode = {}
    draw_count = {}
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
        if stage == "draw":
            framed = "frame" in entry
            if pos in draw_frame_mode and draw_frame_mode[pos] != framed:
                errors.append(f"mixed framed and unframed draw observations for {pos}")
                continue
            draw_frame_mode[pos] = framed
        if stage == "draw" and "frame" in entry:
            frame = entry["frame"]
            if type(frame) is not int or frame < 0:
                errors.append(f"entry {i}: frame must be a non-negative integer")
                continue
            key = (pos, frame)
            if key in seen_draw_frames:
                errors.append(f"duplicate draw observation for {pos} in frame {frame}")
                continue
            seen_draw_frames.add(key)
            draw_count[pos] = draw_count.get(pos, 0) + 1
            if (pos, stage) in found:
                if found[(pos, stage)] != entry["gfx"]:
                    errors.append(f"GFX changed across frames for {pos}")
                if entry["gfx"] not in TARGETS[pos]:
                    errors.append(f"unexpected GFX {entry['gfx']} for {pos} at {stage}")
                for field, limit in (("u", 255), ("v", 255), ("clut", 65535), ("tpage", 65535)):
                    if field in entry:
                        value = entry[field]
                        if type(value) is not int or not 0 <= value <= limit:
                            errors.append(f"entry {i}: {field} must be an integer from 0 to {limit}")
                        elif field in draw_metadata.get(pos, {}) and draw_metadata[pos][field] != value:
                            errors.append(f"{field} changed across frames for {pos}")
                continue
        elif (pos, stage) in found:
            errors.append(f"duplicate observation for {pos} at {stage}")
            continue
        elif stage == "draw":
            draw_count[pos] = draw_count.get(pos, 0) + 1
        found[(pos, stage)] = entry["gfx"]
        if stage == "draw":
            metadata = {}
            for field, limit in (("u", 255), ("v", 255), ("clut", 65535), ("tpage", 65535)):
                if field in entry:
                    value = entry[field]
                    if type(value) is not int or not 0 <= value <= limit:
                        errors.append(f"entry {i}: {field} must be an integer from 0 to {limit}")
                    else:
                        metadata[field] = value
            draw_metadata[pos] = metadata
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
            "draw_metadata": draw_metadata.get(pos, {}),
            "draw_observation_count": draw_count.get(pos, 0),
            "post_load_variant": "PRS" if after == prs else "DAT" if after == dat else None,
            "draw_variant": "PRS" if drawn == prs else "DAT" if drawn == dat else None,
        })
        if after is not None and drawn is not None and after != drawn:
            errors.append(f"GFX changed between loading and drawing for {pos}")
    return {"observations": rows, "errors": errors,
            "warning": "Observed draw metadata is not an independent validation of correct UV, CLUT, tpage, or visible pixels."}



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
    if isinstance(data, dict):
        data = [data]  # A single JSONL observation is also valid JSON.
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
