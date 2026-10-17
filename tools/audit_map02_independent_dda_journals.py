"""Offline envelope audit for *independent* native MAP02 DDA journals.

A rejected-edge candidate is not an executed dda_span call. Both formats
are structurally validated, but neither authenticates the game or hardware.
This intentionally does NOT feed candidate rows into map02_dda_span_join.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_dda_native_spans import parse_native_spans
from tools.verify_map02_dda_rejected_edges import validate as validate_candidates

SPAN_FILE = "dda-native-spans.jsonl"
CANDIDATE_FILE = "dda-rejected-edge-candidates.jsonl"


def audit(directory: Path):
    """Read available native journals without inventing missing observations."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("journal directory is missing or is a symlink")
    inputs = {}
    for filename, parser in (
        (SPAN_FILE, parse_native_spans),
        (CANDIDATE_FILE, validate_candidates),
    ):
        path = directory / filename
        if path.is_symlink():
            raise ValueError("symlinked journal is not accepted")
        if not path.exists():
            inputs[filename] = {"present": False, "event_count": None, "sha256": None}
            continue
        if not path.is_file():
            raise ValueError("journal must be a regular file")
        raw = path.read_bytes()
        records = parser(raw)  # fail closed on malformed, saturated journals
        inputs[filename] = {
            "present": True,
            "event_count": len(records),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        if filename == SPAN_FILE:
            spans = records
        else:
            candidates = records
    if not any(entry["present"] for entry in inputs.values()):
        raise ValueError("no native DDA journals found")
    spans = spans if inputs[SPAN_FILE]["present"] else []
    candidates = candidates if inputs[CANDIDATE_FILE]["present"] else []
    span_keys = {(x.frame, x.primitive_ordinal, x.y) for x in spans}
    candidate_keys = {(x["frame"], x["primitive_ordinal"], x["y"])
                      for x in candidates}
    span_frames = {x.frame for x in spans}
    candidate_frames = {x["frame"] for x in candidates}
    return {
        "schema": "map02_independent_dda_journal_audit_v1",
        "files": inputs,
        "shared_frame_ids": sorted(span_frames & candidate_frames),
        "same_primitive_row_keys": len(span_keys & candidate_keys),
        "notes": [
            "Missing journals mean missing observations, not zero GPU events.",
            "Same row keys do not establish shared rasterizer provenance.",
            "Rejected edge candidates never represent executed dda_span calls.",
            "Native span records cannot recover vertically rejected rows.",
        ],
        "journal_origin_authenticated": False,
        "retail_map02_frame_verified": False,
        "rejected_triangle_pixel_coverage_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal_directory", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.journal_directory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
