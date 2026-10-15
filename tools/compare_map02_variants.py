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



def classify_runtime_faces(report: dict, captured: list[dict]) -> dict:
    """Compare post-LoadMap GFX observations without assuming PRS or DAT wins.

    Captures contain record_index, face, local_gfx and runtime_gfx.
    A complete, unique observation for each target is required.
    """
    if not isinstance(captured, list):
        raise ValueError("runtime capture must be a list")
    by_key = {}
    for item in captured:
        if not isinstance(item, dict):
            raise ValueError("runtime capture entries must be objects")
        for field in ("record_index", "face", "local_gfx", "runtime_gfx"):
            if type(item.get(field)) is not int:
                raise ValueError(f"runtime capture {field} must be an integer")
        key = (item["record_index"], item["face"])
        if key in by_key:
            raise ValueError(f"duplicate runtime capture for {key}")
        if item["local_gfx"] < 0 or item["local_gfx"] > 255:
            raise ValueError("runtime local_gfx outside byte range")
        by_key[key] = item
    expected_keys = {(face["record_index"], face["face"]) for face in report["target_faces"]}
    if set(by_key) != expected_keys:
        raise ValueError("runtime captures must contain exactly both target record/face pairs")
    classifications = []
    for face in report["target_faces"]:
        key = (face["record_index"], face["face"])
        item = by_key[key]
        local = item["local_gfx"]
        runtime = item["runtime_gfx"]
        translated = local + 400 if local else 0
        consistent = runtime == translated
        prs = consistent and local == face["prs_local_gfx"]
        dat = consistent and local == face["dat_local_gfx"]
        classifications.append({
            "record_index": key[0], "face": key[1],
            "observed_local_gfx": local, "observed_runtime_gfx": runtime,
            "translation_consistent": consistent,
            "matches_prs": prs, "matches_dat": dat,
            "classification": (
                "invalid_translation" if not consistent else
                "both" if prs and dat else "prs" if prs else "dat" if dat else "neither"
            ),
        })
    return {
        "faces": classifications,
        "all_match_prs": all(v["classification"] == "prs" for v in classifications),
        "all_match_dat": all(v["classification"] == "dat" for v in classifications),
        "warning": "Post-LoadMap GFX observations only; no draw-call or visual correctness proof.",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decompressed_prs", type=Path)
    parser.add_argument("dat", type=Path)
    parser.add_argument("--require-prior-variant", action="store_true",
                        help="exit nonzero if observed differences do not match the documented two bytes")
    parser.add_argument("--require-prior-provenance", action="store_true",
                        help="require both documented two-byte changes and original decompressed PRS SHA-256")
    parser.add_argument("--runtime-capture", type=Path,
                        help="JSON list of two post-LoadMap face observations to classify")
    args = parser.parse_args()
    try:
        report = compare_map02(args.decompressed_prs.read_bytes(), args.dat.read_bytes())
        if args.runtime_capture is not None:
            report["runtime_capture_comparison"] = classify_runtime_faces(
                report, json.loads(args.runtime_capture.read_text(encoding="utf-8"))
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return int((args.require_prior_variant and not report["matches_prior_disc_audit"]) or
               (args.require_prior_provenance and not report["matches_prior_disc_audit_with_provenance"]))


if __name__ == "__main__":
    raise SystemExit(main())
