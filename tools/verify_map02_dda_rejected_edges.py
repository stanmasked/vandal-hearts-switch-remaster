"""Strict validation for *candidate* DDA edges of vertically rejected scanlines.

Candidate bounds are not executed spans and never certify GPU pixel coverage.
"""
import argparse
import json
from pathlib import Path

FIELDS = frozenset({"stage", "step", "frame", "primitive_ordinal",
                    "reason", "y", "x_start", "x_bound", "clip_t", "clip_b"})
MAX_BYTES = 64 * 512


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def validate(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise ValueError("empty, oversized or non-byte journal")
    if not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw:
        raise ValueError("noncanonical line endings")
    lines = raw.split(b"\n")[:-1]
    if len(lines) > 63:
        raise ValueError("64 events may hide capture truncation")
    out = []
    for index, line in enumerate(lines):
        if not line or len(line) > 512:
            raise ValueError("empty or oversized event")
        try:
            row = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda value: (_ for _ in ()).throw(
                                 ValueError("nonfinite JSON number")))
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f"invalid JSON at event {index}") from exc
        if not isinstance(row, dict) or row.keys() != FIELDS:
            raise ValueError("unexpected candidate record schema")
        if row["stage"] != "rejected_edge_candidate":
            raise ValueError("incorrect event stage")
        for key in FIELDS - {"stage"}:
            if type(row[key]) is not int:
                raise ValueError(f"{key} must be an integer")
        if (row["step"] != index or not 1 <= row["frame"] <= 0xffffffff or
                not 0 <= row["primitive_ordinal"] <= 0xffffffff):
            raise ValueError("invalid identity or event order")
        if any(not -(1 << 31) <= row[key] < (1 << 31)
               for key in ("y", "x_start", "x_bound", "clip_t", "clip_b")):
            raise ValueError("coordinates exceed native signed-int range")
        if row["clip_t"] > row["clip_b"]:
            raise ValueError("invalid vertical clipping window")
        if row["reason"] in (4, 7):
            valid = row["y"] < row["clip_t"]
        elif row["reason"] in (5, 6):
            valid = row["y"] > row["clip_b"]
        else:
            valid = False
        if not valid:
            raise ValueError("reason inconsistent with vertical clipping")
        out.append(row)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    args = parser.parse_args()
    try:
        rows = validate(args.journal.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"validated {len(rows)} candidate edge events (NOT executed spans)")


if __name__ == "__main__":
    main()
