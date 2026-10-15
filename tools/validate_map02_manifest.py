#!/usr/bin/env python3
"""Validate independently collected map-02 LAND_DT evidence (not game assets).

Input is a JSON object:
  {"map": 2, "records": [
    {"gfx": 241, "tile": 243, "face": 0, "land_dt": 641,
     "uv": [0, 0], "size": [0, 0], "palette": 0,
     "source_map": 2},
    {"gfx": 243, "tile": 319, "face": 0, "land_dt": 643,
     "uv": [0, 0], "size": [0, 0], "palette": 0,
     "source_map": 2}
  ]}

All values are expected observations, not reconstructed texture data.
A PASS verifies the manifest's internal consistency only, NOT its truth
against the original disc bytes.
"""
import argparse
import json
from pathlib import Path

EXPECTED = {241: (243, 0, 641), 243: (319, 0, 643)}


def validate(data):
    errors = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if type(data.get("map")) is not int or data["map"] != 2:
        errors.append("map must be integer 2")
    records = data.get("records")
    if not isinstance(records, list):
        return errors + ["records must be an array"]
    seen = set()
    for i, record in enumerate(records):
        prefix = f"records[{i}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        gfx = record.get("gfx")
        if type(gfx) is not int or gfx not in EXPECTED:
            errors.append(f"{prefix}: unexpected GFX index {gfx!r}")
            continue
        if gfx in seen:
            errors.append(f"{prefix}: duplicate GFX {gfx}")
        seen.add(gfx)
        tile, face, entry = EXPECTED[gfx]
        for key, expected in (("tile", tile), ("face", face),
                              ("land_dt", entry), ("palette", 0),
                              ("source_map", 2)):
            value = record.get(key)
            if type(value) is not int or value != expected:
                errors.append(f"{prefix}: {key} expected {expected}, got {value!r}")
        for key in ("uv", "size"):
            value = record.get(key)
            if (not isinstance(value, list) or len(value) != 2 or
                    any(type(x) is not int or x != 0 for x in value)):
                errors.append(f"{prefix}: {key} must be [0, 0]")
    for gfx in sorted(EXPECTED.keys() - seen):
        errors.append(f"missing GFX {gfx}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="read-only JSON evidence manifest")
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validate(data)
    for error in errors:
        print("FAIL:", error)
    if errors:
        return 1
    print("PASS: map-02 manifest internally consistent; source bytes NOT verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
