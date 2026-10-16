#!/usr/bin/env python3
"""Fail-closed parser for ordered *emulator-observed* VBlank / GPU / VRAM JSONL.

This is an offline analyzer; no live PCSX capture is claimed.
"""
import argparse
import json
from collections import Counter

class TraceError(ValueError):
    pass

def analyze(lines):
    events = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except ValueError as exc:
            raise TraceError(f"invalid JSON at line {number}") from exc
        if not isinstance(e, dict) or e.get("kind") not in ("vblank", "gp0", "gp1", "vram_write", "snapshot"):
            raise TraceError(f"invalid event at line {number}")
        seq = e.get("seq")
        if type(seq) is not int or seq < 0 or (events and seq <= events[-1]["seq"]):
            raise TraceError("event sequence is not strictly increasing")
        if e["kind"] == "vblank":
            if any(type(e.get(k)) is not int or e[k] < 0 for k in ("frame", "cycle")):
                raise TraceError("invalid VBlank frame/cycle")
        if e["kind"] in ("gp0", "gp1"):
            if type(e.get("word")) is not int or not 0 <= e["word"] <= 0xffffffff:
                raise TraceError("invalid GPU word")
        if e["kind"] in ("vram_write", "snapshot"):
            for key, bound in (("x", 1023), ("y", 511), ("value", 65535)):
                if type(e.get(key)) is not int or not 0 <= e[key] <= bound:
                    raise TraceError("invalid VRAM coordinate/value")
        events.append(e)
    edges = [e for e in events if e["kind"] == "vblank"]
    if len(edges) < 2 or events[0]["kind"] != "vblank" or events[-1]["kind"] != "vblank":
        raise TraceError("missing start/end VBlank edges")
    for a, b in zip(edges, edges[1:]):
        if b["frame"] != a["frame"] + 1 or b["cycle"] <= a["cycle"]:
            raise TraceError("nonconsecutive VBlank frames or cycles")
    edge_seqs = {v["seq"] for v in edges}
    intervals = []
    for a, b in zip(edges, edges[1:]):
        bucket = [e for e in events if a["seq"] < e["seq"] < b["seq"]]
        intervals.append({"from_frame": a["frame"], "to_frame": b["frame"],
                          "gp0_words": [e["word"] for e in bucket if e["kind"] == "gp0"],
                          "gp1_words": [e["word"] for e in bucket if e["kind"] == "gp1"],
                          "observed_vram_writes": sum(e["kind"] == "vram_write" for e in bucket)})
    totals = Counter()
    for snap in (e for e in events if e["kind"] == "snapshot"):
        edge_seq = snap.get("edge_seq")
        if type(edge_seq) is not int or edge_seq not in edge_seqs or snap["seq"] <= edge_seq:
            raise TraceError("snapshot has invalid VBlank reference")
        if any(e["kind"] in ("gp0", "gp1", "vram_write") and edge_seq < e["seq"] < snap["seq"] for e in events):
            raise TraceError("snapshot readback occurred after post-edge activity")
        writes = [e for e in events if e["kind"] == "vram_write" and e["seq"] < edge_seq
                  and (e["x"], e["y"]) == (snap["x"], snap["y"])]
        category = ("unknown" if not writes else
                    "retained" if writes[-1]["value"] == snap["value"] else "mismatch")
        totals[category] += 1
    return {"scope": "emulator_observer_not_retail_MAP02",
            "physical_ps1_vblank_verified": False,
            "original_retail_MAP02_verified": False,
            "HD_replacement_approved": False, "vblank_edges": len(edges),
            "intervals": intervals, "snapshot_vs_explicit_last_write": dict(totals)}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace")
    args = p.parse_args()
    try:
        with open(args.trace, encoding="utf-8") as f:
            result = analyze(f)
    except (OSError, TraceError) as exc:
        p.exit(2, f"REFUSED: {exc}\n")
    print(json.dumps(result, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
