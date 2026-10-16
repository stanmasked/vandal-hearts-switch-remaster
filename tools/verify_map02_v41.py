#!/usr/bin/env python3
"""Conservative frame-aware correlation of actual map02 OT, native and hires traces.

Exit 0 = at least one terrain primitive has matching native AND hires DDA
samples in the same frame, with zero consistency errors.
Exit 1 = contradicting/invalid trace or unsafe payload.
Exit 2 = insufficient evidence (including only old, unframed v39/v40 logs).

Sparse samples prove origin consistency only, not image/per-pixel equivalence,
visibility of unsampled primitives, or a complete playable renderer.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

TAGS = {
    "v39-terrain-ot": ("f", "token", "gfx", "route", "tpage", "clut"),
    "v39-terrain-dda": ("f", "token", "gfx", "route", "x", "y", "u", "v",
                        "raw", "draw", "semi", "abr"),
    "v40-terrain-hires": ("f", "token", "gfx", "route", "x", "y", "u", "v",
                          "raw", "draw", "semi", "abr", "scale"),
}
MARKER = re.compile(r"\[(v39-terrain-ot|v39-terrain-dda|v40-terrain-hires)\]")
FIELD = re.compile(r"([a-z]+)=(-?\d+)")
EVENT_LIMIT = 1000000
ERROR_LIMIT = 100


def parse_line(line: str, line_number: int):
    m = MARKER.search(line)
    if not m:
        return None
    tag = m.group(1)
    fields = {}
    tail = line[m.end():].strip()
    for token in tail.split():
        hit = FIELD.fullmatch(token)
        if not hit:
            raise ValueError(f"line {line_number}: malformed {tag} field {token[:80]!r}")
        k, v = hit.group(1), int(hit.group(2))
        if k in fields:
            raise ValueError(f"line {line_number}: duplicate field {k}")
        fields[k] = v
    required = set(TAGS[tag])
    if set(fields) != required:
        raise ValueError(
            f"line {line_number}: wrong fields for {tag}; "
            f"missing={sorted(required-set(fields))}, unexpected={sorted(set(fields)-required)}"
        )
    if not 1 <= fields["f"] <= 0xffffffff:
        raise ValueError(f"line {line_number}: invalid frame")
    if not 1 <= fields["token"] < 65536:
        raise ValueError(f"line {line_number}: invalid OT token")
    if not 1 <= fields["gfx"] <= 65535:
        raise ValueError(f"line {line_number}: invalid gfx")
    if fields["route"] not in (1, 2, 3):
        raise ValueError(f"line {line_number}: invalid terrain route")
    if tag.endswith("-ot"):
        if not 0 <= fields["tpage"] <= 65535 or not 0 <= fields["clut"] <= 65535:
            raise ValueError(f"line {line_number}: invalid tpage/clut")
    else:
        if not 0 <= fields["u"] <= 255 or not 0 <= fields["v"] <= 255:
            raise ValueError(f"line {line_number}: invalid PS1 UV")
        if fields["draw"] not in (0, 1) or fields["semi"] not in (0, 1):
            raise ValueError(f"line {line_number}: invalid draw/semi flag")
        if fields["abr"] not in (0, 1, 2, 3):
            raise ValueError(f"line {line_number}: invalid blend mode")
        if not 0 <= fields["raw"] <= 65535:
            raise ValueError(f"line {line_number}: invalid BGR555 texel")
        if fields["draw"] != int(fields["raw"] != 0):
            raise ValueError(f"line {line_number}: transparency contradicts raw texel")
        if tag == "v40-terrain-hires" and not 1 <= fields["scale"] <= 4:
            raise ValueError(f"line {line_number}: unsupported native/hires scale")
    return tag, fields


def analyze(lines):
    ot = {}
    samples = defaultdict(lambda: {"native": 0, "hires": 0})
    sample_records = []
    errors = []
    counts = Counter()
    frames = set()
    def error(message):
        if len(errors) < ERROR_LIMIT:
            errors.append(message)
    for line_no, line in enumerate(lines, 1):
        if len(line) > 16384:
            error(f"line {line_no}: record too long")
            break
        try:
            found = parse_line(line, line_no)
        except ValueError as exc:
            error(str(exc))
            continue
        if found is None:
            continue
        tag, fields = found
        counts[tag] += 1
        if sum(counts.values()) > EVENT_LIMIT:
            error("event count limit exceeded")
            break
        frames.add(fields["f"])
        key = (fields["f"], fields["token"])
        if tag == "v39-terrain-ot":
            if key in ot:
                error(f"line {line_no}: duplicate OT event for f={key[0]} token={key[1]}")
            else:
                ot[key] = fields
        else:
            name = "native" if tag == "v39-terrain-dda" else "hires"
            sample_records.append((line_no, key, fields, name))

    for line_no, key, item, name in sample_records:
        owner = ot.get(key)
        if owner is None:
            error(f"line {line_no}: orphan {name} sample for f={key[0]} token={key[1]}")
            continue
        if (owner["gfx"], owner["route"]) != (item["gfx"], item["route"]):
            error(
                f"line {line_no}: mismatched {name} origin for f={key[0]} "
                f"token={key[1]} (expected gfx={owner['gfx']} route={owner['route']})"
            )
            continue
        samples[key][name] += 1

    paired = sorted(key for key, d in samples.items()
                    if d["native"] > 0 and d["hires"] > 0)
    native_prims = sum(d["native"] > 0 for d in samples.values())
    hires_prims = sum(d["hires"] > 0 for d in samples.values())
    unsampled = sum(key not in samples for key in ot)
    status = ("inconsistent" if errors else
              "provenance_correlated" if paired else "insufficient_evidence")
    return {
        "schema": "vh-map02-frame-provenance-v41",
        "status": status,
        "pixel_equivalence_proven": False,
        "gameplay_execution_proven": False,
        "frames_with_events": len(frames),
        "ot_primitive_count": len(ot),
        "native_sample_count": counts["v39-terrain-dda"],
        "hires_sample_count": counts["v40-terrain-hires"],
        "native_primitive_count": native_prims,
        "hires_primitive_count": hires_prims,
        "paired_primitive_count": len(paired),
        "unsampled_ot_primitive_count": unsampled,
        "examples_of_paired_frame_tokens": [
            {"frame": key[0], "token": key[1],
             "gfx": ot[key]["gfx"], "route": ot[key]["route"]}
            for key in paired[:8]
        ],
        "errors": errors
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="combined stderr from a real map 11 gameplay session")
    parser.add_argument("--output", type=Path, help="write JSON report; stdout by default")
    args = parser.parse_args()
    try:
        with args.log.open(encoding="utf-8", errors="strict") as stream:
            report = analyze(stream)
        report_text = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(report_text)
        else:
            sys.stdout.write(report_text)
    except (OSError, UnicodeError) as exc:
        print(f"trace reader failed: {exc}", file=sys.stderr)
        return 1
    return {"provenance_correlated": 0, "inconsistent": 1,
            "insufficient_evidence": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
