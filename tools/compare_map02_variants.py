#!/usr/bin/env python3
"""Read-only comparison of decompressed M_MAP02.PRS and M_MAP02.DAT tile records.

Supply the decompressed PRS payload, NOT the compressed .PRS file.
No copyrighted game bytes are included or emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path

RECORD_SIZE = 304
RECORD_COUNT = 616
EXPECTED_LENGTH = RECORD_SIZE * RECORD_COUNT
FACE_GFX_OFFSET = 176
TARGET_RECORDS = (243, 319)
PRIOR_PRS_DECOMPRESSED_SHA256 = "dd98f466fbf4f1019cf04d9b19dd85861afa61e97d0470ce796a4cb83b989382"


def compare_map02(prs: bytes, dat: bytes) -> dict:
    if len(prs) != EXPECTED_LENGTH:
        raise ValueError(f"decompressed PRS must contain {EXPECTED_LENGTH} bytes; got {len(prs)}")
    if len(dat) < EXPECTED_LENGTH:
        raise ValueError(f"DAT must contain at least {EXPECTED_LENGTH} bytes; got {len(dat)}")
    changes = []
    for offset, (p, d) in enumerate(zip(prs, dat[:EXPECTED_LENGTH])):
        if p != d:
            record, within = divmod(offset, RECORD_SIZE)
            changes.append({
                "absolute_offset": offset, "record_index": record,
                "record_byte_offset": within, "prs": p, "dat": d,
            })
    target_faces = []
    for record in TARGET_RECORDS:
        offset = record * RECORD_SIZE + FACE_GFX_OFFSET
        p, d = prs[offset], dat[offset]
        target_faces.append({
            "record_index": record, "x": record % 28, "z": record // 28,
            "face": 0, "gfx0_offset": offset,
            "prs_local_gfx": p, "dat_local_gfx": d,
            "prs_runtime_gfx": p + 400 if p else 0,
            "dat_runtime_gfx": d + 400 if d else 0,
        })
    expected = {(243, FACE_GFX_OFFSET, 241, 98), (319, FACE_GFX_OFFSET, 243, 150)}
    actual = {(v["record_index"], v["record_byte_offset"], v["prs"], v["dat"]) for v in changes}
    return {
        "prs_decompressed_sha256": hashlib.sha256(prs).hexdigest(),
        "dat_sha256": hashlib.sha256(dat).hexdigest(),
        "compared_bytes": EXPECTED_LENGTH,
        "difference_count": len(changes),
        "differences": changes,
        "target_faces": target_faces,
        "matches_prior_disc_audit": actual == expected,
        "matches_prior_prs_digest": hashlib.sha256(prs).hexdigest() == PRIOR_PRS_DECOMPRESSED_SHA256,
        "matches_prior_disc_audit_with_provenance": (
            actual == expected and hashlib.sha256(prs).hexdigest() == PRIOR_PRS_DECOMPRESSED_SHA256
        ),
        "warning": "Byte-level reference comparison only; cannot establish runtime selection or visual correctness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decompressed_prs", type=Path)
    parser.add_argument("dat", type=Path)
    parser.add_argument("--require-prior-variant", action="store_true",
                        help="exit nonzero if observed differences do not match the documented two bytes")
    parser.add_argument("--require-prior-provenance", action="store_true",
                        help="require both documented two-byte changes and original decompressed PRS SHA-256")
    args = parser.parse_args()
    try:
        report = compare_map02(args.decompressed_prs.read_bytes(), args.dat.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return int((args.require_prior_variant and not report["matches_prior_disc_audit"]) or
               (args.require_prior_provenance and not report["matches_prior_disc_audit_with_provenance"]))


if __name__ == "__main__":
    raise SystemExit(main())
