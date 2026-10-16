#!/usr/bin/env python3
"""V47 proof: join every tagged OT primitive to its EXACT PRS tile and face.

Supports identical GFX, UV and CLUT on different tiles and in the same frame,
because the game producer marks OT token at submission. No texture replacement,
no geometry export and no claim to a real retail map.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import struct
import sys

from .preflight_map02_prs_v45 import WIDTH, HEIGHT, STRIDE, inspect_file, read_prs, unpack_bounded, load_v24
from .verify_map02_v41 import parse_line, analyze

PATTERN = re.compile(r"\[v47-terrain-face-ot\]\s+(.*)$")
REQUIRED = {"f", "token", "z", "x", "face", "gfx", "route", "tpage", "clut", "u", "v"}
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_LOG_LINES = 150000
MAX_ERRORS = 50


class InvalidEvidence(ValueError):
    pass


def parse_face_log(line: str):
    m = PATTERN.search(line)
    if m is None:
        return None
    fields = {}
    for value in m.group(1).split():
        hit = re.fullmatch(r"([a-z]+)=(-?\d+)", value)
        if hit is None:
            raise InvalidEvidence("malformed v47 field: " + value[:80])
        k, v = hit.group(1), int(hit.group(2))
        if k in fields:
            raise InvalidEvidence("duplicate v47 field: " + k)
        fields[k] = v
    if set(fields) != REQUIRED:
        raise InvalidEvidence("v47 fields differ: missing="+str(sorted(REQUIRED-set(fields)))+
                              " extra="+str(sorted(set(fields)-REQUIRED)))
    if not (1 <= fields["f"] <= 0xffffffff and 1 <= fields["token"] < 65536
            and 0 <= fields["z"] < HEIGHT and 0 <= fields["x"] < WIDTH
            and 0 <= fields["face"] < 18 and 1 <= fields["gfx"] < 870
            and fields["route"] in (1,2,3)
            and 0 <= fields["tpage"] <= 65535 and 0 <= fields["clut"] <= 65535
            and 0 <= fields["u"] <= 255 and 0 <= fields["v"] <= 255):
        raise InvalidEvidence("out-of-range v47 face attribution")
    return fields


def verify(decoded, slots, lines, *, synthetic=False, source_sha=None):
    if len(decoded) != WIDTH*HEIGHT*STRIDE:
        raise InvalidEvidence("incorrect PRS decoded grid size")
    if len(lines) > MAX_LOG_LINES:
        raise InvalidEvidence("excessive number of log lines")
    summary = analyze(lines)
    if summary["status"] == "inconsistent":
        raise InvalidEvidence("original v41 native/hires trace inconsistency: "+
                              ";".join(summary["errors"][:3]))
    ot = {}
    face_log = {}
    types = Counter()
    for i,line in enumerate(lines,1):
        if len(line) > 16384:
            raise InvalidEvidence(f"line {i} exceeds limit")
        parsed = parse_line(line,i)
        if parsed is not None and parsed[0] == "v39-terrain-ot":
            fields = parsed[1]
            key = (fields["f"],fields["token"])
            if key in ot:
                raise InvalidEvidence(f"duplicate token {key}")
            ot[key] = fields
        face=parse_face_log(line)
        if face is not None:
            key=(face["f"],face["token"])
            if key in face_log:
                raise InvalidEvidence(f"duplicate face marker on token {key}")
            face_log[key]=face
            types[face["route"]]+=1
    if set(ot)!=set(face_log):
        raise InvalidEvidence("missing or extra face markers relative to v39 OT: missing="+
                              str(sorted(set(ot)-set(face_log))[:4])+
                              " extra="+str(sorted(set(face_log)-set(ot))[:4]))
    # The v41 analysis already validates token/gfx/route in every native and
    # deferred DDA event, but it may report only sparse pixels. Never claim
    # all submitted faces were *visually* observed based on a sparse trace.
    errors=[]
    rows=[]
    unpaired=set()
    samples=defaultdict(lambda: {"native":False,"hires":False})
    for i,line in enumerate(lines,1):
        parsed=parse_line(line,i)
        if parsed is None:
            continue
        tag,e=parsed
        if tag=="v39-terrain-dda":
            samples[(e["f"],e["token"])]["native"]=True
        if tag=="v40-terrain-hires":
            samples[(e["f"],e["token"])]["hires"]=True
    seen_coordinates=defaultdict(set)
    for key,face in sorted(face_log.items()):
        gpu=ot[key]
        if any(face[f]!=gpu[f] for f in ("gfx","route","tpage","clut")):
            errors.append(f"token={key} face metadata differs from real GPU FT4")
            continue
        z,x,fi=face["z"],face["x"],face["face"]
        base=(z*WIDTH+x)*STRIDE
        nfaces=decoded[base+302]
        if fi>=nfaces:
            errors.append(f"token={key} nonexistent PRS face at ({z},{x},{fi})")
            continue
        actual_gfx,=struct.unpack_from("<h",decoded,base+176+2*fi)
        if actual_gfx!=face["gfx"]:
            errors.append(f"token={key} PRS GFX {actual_gfx} != emitted {face['gfx']}")
            continue
        local=actual_gfx-400
        row=slots.get(local)
        if row is None:
            errors.append(f"token={key} no v24 row for local GFX {local}")
            continue
        if (row[8],row[9],row[2],row[3]) != (
                face["tpage"],face["clut"],face["u"],face["v"]):
            errors.append(f"token={key} original GPU tpage/CLUT/UV not in v24 slot {local}")
            continue
        # A face can be drawn again in the same frame via other render paths;
        # identity is (frame,token), not (frame,GFX) or (frame,tile).
        identity=(z,x,fi)
        seen_coordinates[key[0]].add(identity)
        both=samples[key]["native"] and samples[key]["hires"]
        if not both:
            unpaired.add(key)
        rows.append({"frame":key[0],"token":key[1],"z":z,"x":x,"face":fi,
                     "gfx":actual_gfx,"local_slot":local,"route":face["route"],
                     "native_and_hires_sampled":bool(both)})
    status=("refused" if errors else "matched_sampled_faces" if rows and not unpaired else
            "insufficient_sparse_evidence")
    return {
        "schema":"vh-map02-token-bound-face-v47",
        "status":status,
        "retail_map_authenticity_proven":False,
        "genuine_gameplay_proven":False,
        "full_map_coverage_proven":False,
        "HD_replacement_approved":False,
        "synthetic_input":bool(synthetic),
        "source_sha256":source_sha,
        "tagged_ot_count":len(ot),
        "face_marker_count":len(face_log),
        "matched_face_count":len(rows),
        "both_pass_sampled_count":sum(x["native_and_hires_sampled"] for x in rows),
        "sparsely_unobserved_count":len(unpaired),
        "distinct_face_coordinates_count":len({(x["z"],x["x"],x["face"]) for x in rows}),
        "duplicate_gfx_face_pairs":sum(
           1 for i,x in enumerate(rows) if any(y["frame"]==x["frame"] and y["gfx"]==x["gfx"]
                                                and y["token"]!=x["token"] for y in rows[i+1:])),
        "rows":rows[:64],
        "errors":errors[:MAX_ERRORS],
        "note":"Identity is authoritative only for submitted tagged FT4; not proof of full retail map or HD pixel fidelity."
    }


def _read_lines(path):
    if path.stat().st_size > MAX_LOG_BYTES:
        raise InvalidEvidence("GPU log size exceeds safe cap")
    with path.open(encoding="utf-8",errors="strict") as fp:
        rows=[]
        for line in fp:
            if len(rows) >= MAX_LOG_LINES:
                raise InvalidEvidence("too many GPU log records")
            rows.append(line)
        return rows


def inspect(prs, gpu_log, v24, synthetic=False):
    report=inspect_file(prs,v24,synthetic=synthetic)
    payload,_,_=read_prs(prs)
    return verify(unpack_bounded(payload),load_v24(v24),_read_lines(gpu_log),
                  synthetic=synthetic,source_sha=report["sha256_input"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("prs",type=Path)
    p.add_argument("gpu_log",type=Path,help="combined stderr from one instrumented session")
    p.add_argument("--v24",type=Path,default=Path(__file__).resolve().parents[1]/
                   "tests/fixtures/vh_map02_hd_lookup_v24.h")
    p.add_argument("--synthetic-fixture",action="store_true")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        result=inspect(a.prs,a.gpu_log,a.v24,a.synthetic_fixture)
        output=json.dumps(result,indent=2,sort_keys=True)+"\n"
        if a.output:
            with a.output.open("x",encoding="utf-8") as fp:
                fp.write(output)
        else:
            sys.stdout.write(output)
        return {"matched_sampled_faces":0,"refused":1,"insufficient_sparse_evidence":2}[result["status"]]
    except (OSError,UnicodeError,ValueError) as exc:
        print("[v47-face-evidence] REFUSED: "+str(exc),file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
