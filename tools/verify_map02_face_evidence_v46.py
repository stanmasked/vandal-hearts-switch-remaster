#!/usr/bin/env python3
"""V46: fail-closed face-level PRS -> game draw -> OT/native/hires evidence join.

No vertex data exported, no pixels changed, no texture replacement. Runtime
logs must be from the SAME single process/session as the PRS input and its
active texture table. Frame identity is cross-subsystem only if the emitted
graphics frame counter and GPU DrawOTag frame agree; mismatch is refused.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
import sys

from .preflight_map02_prs_v45 import (
    WIDTH, HEIGHT, STRIDE, InvalidPrs, inspect_file, read_prs,
    unpack_bounded, load_v24,
)
from .verify_map02_v41 import analyze, parse_line

MAX_LOG = 16 * 1024 * 1024
MAX_EVENTS = 200000
ROUTES = {"normal": 1, "edge": 2, "overhead": 3}
EXPECTED_DRAW_KEYS = {"z", "x", "face", "stage", "gfx", "frame",
                      "u", "v", "clut", "tpage", "path"}
MAX_ERRORS = 30


class V46Invalid(ValueError):
    pass


def _read_log(path: Path) -> list[str]:
    if path.stat().st_size > MAX_LOG:
        raise V46Invalid(f"log too large: {path}")
    with path.open("r", encoding="utf-8", errors="strict") as stream:
        lines = []
        for i, line in enumerate(stream):
            if i >= MAX_EVENTS:
                raise V46Invalid("too many log lines")
            if len(line) > 16384:
                raise V46Invalid(f"excessive log line at {i+1}")
            lines.append(line)
        return lines


def _draw_events(lines):
    records = []
    seen = set()
    for line_no, line in enumerate(lines, 1):
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise V46Invalid(f"graphics line {line_no} is not JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise V46Invalid(f"graphics line {line_no} is not a record")
        if value.get("stage") != "draw":
            continue
        if set(value) != EXPECTED_DRAW_KEYS:
            raise V46Invalid(f"graphics line {line_no} unexpected or missing draw keys")
        for k in ("z", "x", "face", "gfx", "frame", "u", "v", "clut", "tpage"):
            if type(value[k]) is not int:
                raise V46Invalid(f"graphics line {line_no} {k} not an integer")
        z,x,face,gfx,frame = (value[k] for k in ("z","x","face","gfx","frame"))
        if not (0 <= z < HEIGHT and 0 <= x < WIDTH and 0 <= face < 18 and
                0 <= gfx < 870 and 1 <= frame <= 0xffffffff and
                0 <= value["u"] <= 255 and 0 <= value["v"] <= 255 and
                0 <= value["tpage"] <= 65535 and 0 <= value["clut"] <= 65535 and
                value["path"] in ROUTES):
            raise V46Invalid(f"graphics line {line_no} invalid draw geometry")
        key = (frame,z,x,face)
        if key in seen:
            raise V46Invalid(f"repeated face draw in same frame: {key}")
        seen.add(key)
        records.append(value)
    return records


def _gpu_events(lines):
    ots, paired, all_events = {}, set(), []
    analyzed = analyze(lines)
    if analyzed["status"] == "inconsistent":
        raise V46Invalid("GPU DDA provenance inconsistent: " + "; ".join(analyzed["errors"][:3]))
    for line_no, line in enumerate(lines,1):
        try:
            evt = parse_line(line,line_no)
        except ValueError as exc:
            raise V46Invalid(str(exc)) from exc
        if evt is None:
            continue
        tag, data = evt
        key = (data["f"],data["token"])
        if tag == "v39-terrain-ot":
            if key in ots:
                raise V46Invalid(f"duplicate OT token {key}")
            ots[key] = data
        else:
            all_events.append((key,tag,data))
    sample_counts = defaultdict(lambda: {"v39-terrain-dda":0,"v40-terrain-hires":0})
    for key,tag,data in all_events:
        if key not in ots:
            raise V46Invalid(f"orphan GPU sample {key}")
        owner = ots[key]
        if owner["gfx"] != data["gfx"] or owner["route"] != data["route"]:
            raise V46Invalid(f"mismatched OT/sample provenance {key}")
        sample_counts[key][tag] += 1
    for key,cnts in sample_counts.items():
        if all(cnts.values()):
            paired.add(key)
    return ots, paired, analyzed


def compare(decoded: bytes, graphics_lines: list[str],
            gpu_lines: list[str], slots: dict, input_meta: dict) -> dict:
    errors = []
    draws = _draw_events(graphics_lines)
    ot, paired, gpu_summary = _gpu_events(gpu_lines)
    by_frame_gfx_route = defaultdict(list)
    for key,datum in ot.items():
        by_frame_gfx_route[(key[0],datum["gfx"],datum["route"])].append((key,datum))
    matches = []
    seen_ot = set()
    for draw in draws:
        frame,z,x,face,gfx = (draw[k] for k in ("frame","z","x","face","gfx"))
        base = (z*WIDTH+x)*STRIDE
        nfaces = decoded[base+302]
        if face >= nfaces:
            errors.append(f"f={frame} {z},{x}/{face}: face absent from PRS")
            continue
        original_gfx, = struct.unpack_from("<h",decoded,base+176+2*face)
        if gfx != original_gfx:
            errors.append(f"f={frame} {z},{x}/{face}: runtime GFX {gfx} != PRS GFX {original_gfx}")
            continue
        local = gfx-400
        row = slots.get(local)
        if row is None:
            errors.append(f"f={frame} {z},{x}/{face}: GFX {gfx} not supported by v24")
            continue
        expected = {"u":row[2],"v":row[3],"tpage":row[8],"clut":row[9]}
        if any(draw[name] != expected[name] for name in expected):
            errors.append(f"f={frame} {z},{x}/{face}: live UV/tpage/CLUT != v24 local slot {local}")
            continue
        route = ROUTES[draw["path"]]
        candidates = by_frame_gfx_route[(frame,gfx,route)]
        if len(candidates) != 1:
            errors.append(f"f={frame} {z},{x}/{face}: ambiguous or absent GPU OT match ({len(candidates)})")
            continue
        key, owner = candidates[0]
        if key in seen_ot:
            errors.append(f"f={frame} {z},{x}/{face}: duplicate claim on GPU OT token")
            continue
        seen_ot.add(key)
        if owner["tpage"] != row[8] or owner["clut"] != row[9]:
            errors.append(f"f={frame} {z},{x}/{face}: OT tpage/CLUT differs from v24")
            continue
        if key not in paired:
            # Sparse sampling does not prove a polygon was *not* rendered.
            # But it also cannot pass a join claiming both paths observed.
            errors.append(f"f={frame} {z},{x}/{face}: no same-token native/hires DDA evidence")
            continue
        matches.append({"frame":frame,"z":z,"x":x,"face":face,
                        "gfx":gfx,"local_slot":local,"route":draw["path"],
                        "ot_token":key[1]})
    # Untagged sprites do not appear in v39 OT events; a genuine unaccounted
    # marked FT4 is a provenance gap and must never silently pass.
    if len(seen_ot) != len(ot):
        errors.append(f"unclaimed tagged terrain OT primitives: {len(ot)-len(seen_ot)}")
    state = ("refused" if errors else
             "synthetic_joint_evidence_only" if matches else "insufficient_evidence")
    return {
        "schema":"vh-map02-per-face-evidence-v46",
        "status":state,
        "input_sha256":input_meta["sha256_input"],
        "source_provenance":input_meta["input_provenance"],
        "retail_map_authenticity_proven":False,
        "genuine_gameplay_proven":False,
        "full_map_texture_coverage_proven":False,
        "HD_replacement_approved":False,
        "decompressed_bytes":len(decoded),
        "graphics_face_draw_count":len(draws),
        "gpu_ot_tagged_count":len(ot),
        "paired_gpu_primitives":len(paired),
        "joined_face_count":len(matches),
        "joined_faces":matches[:24],
        "errors":errors[:MAX_ERRORS],
        "warning":"Requires matching PRS/graphics/GPU from ONE session. Synthetic verification never enables HD substitution.",
    }


def inspect(prs: Path, graphics: Path, gpu: Path, v24: Path, synthetic=False):
    preflight = inspect_file(prs,v24,synthetic=synthetic)
    payload,_,_ = read_prs(prs)
    decoded = unpack_bounded(payload)
    slots = load_v24(v24)
    return compare(decoded, _read_log(graphics), _read_log(gpu), slots, preflight)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("prs",type=Path)
    p.add_argument("graphics_log",type=Path, help="stdout JSONL of the same run")
    p.add_argument("gpu_log",type=Path,help="stderr native/hires OT+DDA of the same run")
    p.add_argument("--v24",type=Path,default=Path(__file__).resolve().parents[1]/
                   "tests/fixtures/vh_map02_hd_lookup_v24.h")
    p.add_argument("--synthetic-fixture",action="store_true")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        result=inspect(a.prs,a.graphics_log,a.gpu_log,a.v24,a.synthetic_fixture)
        payload=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as out:
                out.write(payload)
        else:
            sys.stdout.write(payload)
        return {"synthetic_joint_evidence_only":0,"refused":1,"insufficient_evidence":2}[result["status"]]
    except (OSError,UnicodeError,ValueError,InvalidPrs) as exc:
        print("[v46-evidence] REFUSED: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
