#!/usr/bin/env python3
"""Check metadata-only RU MAP02 source reconciliation.

This checks *reported* SHA-256 values, not the disc itself. It does not
attest the reporter, authenticate gameplay or prove GPU pixel output.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED_HASHES = {
    "prs_logical": "c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387",
    "prs_file": "c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387",
    "prs_unpacked": "dd98f466fbf4f1019cf04d9b19dd85861afa61e97d0470ce796a4cb83b989382",
    "dat_file": "07666bd80b87de763ef7312ecaeaa0bf747ebfe49db032fa68c9af675d151c31",
}
EXPECTED_DIFFERENCES = (
    (74048, 243, 176, 241, 98),
    (97152, 319, 176, 243, 150),
)
EXPECTED_FACES = (
    (243, 19, 8, 241, 98),
    (319, 11, 11, 243, 150),
)


def require(value, expected, label):
    if type(value) is not type(expected) or value != expected:
        raise ValueError("invalid or changed " + label)


def check_receipt(report):
    if type(report) is not dict:
        raise ValueError("MAP02 receipt must be a JSON object")
    for field, expected in (
        ("schema", 1), ("kind", "LOCAL_MAP02_RU_SOURCE_RECONCILIATION"),
        ("source_project", "Vandal Hearts PS1 RU v1.6"),
        ("verified_source_sha256", True), ("volume_id", "SLUS_00447"),
        ("original_payload_exported", False),
        ("interpretation", "MATCHES_PRIOR_SOURCE_BYTES"),
    ):
        require(report.get(field), expected, field)
    for field in ("existing_decoder_source_sha256", "existing_comparison_source_sha256"):
        digest = report.get(field)
        if type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise ValueError("missing source-code fingerprint " + field)
    hashes = report.get("hashes")
    if type(hashes) is not dict:
        raise ValueError("missing resource fingerprints")
    for field, expected in EXPECTED_HASHES.items():
        require(hashes.get(field), expected, "hashes." + field)
    prs, dat = report.get("prs"), report.get("dat")
    if type(prs) is not dict or type(dat) is not dict:
        raise ValueError("missing PRS/DAT metadata")
    for field, expected in (
        ("lba", 7116), ("size_bytes", 22783),
        ("declared_compressed_bytes", 22779), ("unpacked_bytes", 187264)
    ):
        require(prs.get(field), expected, "prs." + field)
    for field, expected in (("lba", 6999), ("size_bytes", 238336)):
        require(dat.get(field), expected, "dat." + field)
    comparison = report.get("comparison")
    if type(comparison) is not dict:
        raise ValueError("missing comparison")
    for field, expected in (
        ("compared_bytes", 187264), ("difference_count", 2),
        ("matches_prior_two_differences", True)
    ):
        require(comparison.get(field), expected, "comparison." + field)
    differences = comparison.get("first_differences")
    if type(differences) is not list or len(differences) != 2:
        raise ValueError("expected exactly two differences")
    fields = ("offset", "record", "within_record", "prs_value", "dat_value")
    for idx, (row, expected) in enumerate(zip(differences, EXPECTED_DIFFERENCES)):
        if type(row) is not dict or set(row) != set(fields):
            raise ValueError("invalid difference record")
        for field, value in zip(fields, expected):
            require(row.get(field), value, "difference %d %s" % (idx, field))
    faces = comparison.get("target_faces")
    if type(faces) is not list or len(faces) != 2:
        raise ValueError("expected exactly two target faces")
    fields = ("record", "x", "z", "prs_local_gfx", "dat_local_gfx")
    for idx, (row, expected) in enumerate(zip(faces, EXPECTED_FACES)):
        if type(row) is not dict or set(row) != set(fields):
            raise ValueError("invalid target face")
        for field, value in zip(fields, expected):
            require(row.get(field), value, "target %d %s" % (idx, field))
    prior = report.get("prior_source_comparison")
    if type(prior) is not dict:
        raise ValueError("missing prior source comparison")
    for field in ("prs_logical_matches", "prs_unpacked_matches", "dat_matches", "all_match"):
        require(prior.get(field), True, "prior_source_comparison." + field)
    return {
        "kind": "MAP02_RU_RECEIPT_CONSISTENCY_GATE",
        "source_receipt_consistent": True,
        "map02_prs_dat_equivalent_to_prior_source": True,
        "reported_prs_decoded_bytes": 187264,
        "reported_prs_dat_differences": 2,
        "disc_independently_rehashed_by_this_gate": False,
        "runtime_capture_supplied": False,
        "runtime_gfx_selection_verified": False,
        "original_gameplay_authenticated": False,
        "warning": "A receipt can be fabricated. It does not prove a game was run or a pixel drawn.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path, help="private metadata-only MAP02 RU JSON")
    args = parser.parse_args()
    try:
        path = args.receipt
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
            raise ValueError("receipt must be a regular, bounded, non-symlink file")
        raw = path.read_bytes()
        result = check_receipt(json.loads(raw.decode("utf-8")))
        result["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
