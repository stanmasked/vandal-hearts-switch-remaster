#!/usr/bin/env python3
"""Independently reverify a downloaded seven-case CI digest index.

Regenerates the expected canonical index from PNGs, NROs and witness JSON.
A correct digest index is NOT a signature, audible audio proof or hardware
attestation. The external revision/run identity must be supplied separately.
"""
import argparse
import json
from pathlib import Path

from build_native_av_run_audit import build_report
from verify_native_av_guest_witness import (
    reject_nonfinite_json, unique_json_object, verify,
)

MAX_AUDIT_BYTES = 65536


def verify_audit(index_path, evidence_root, nro_root, revision, run_id, attempt,
                 *, verify_case=verify):
    path = Path(index_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing, non-regular or symlinked audit index")
    if path.stat().st_size > MAX_AUDIT_BYTES:
        raise ValueError("audit index exceeds size limit")
    with path.open("rb") as stream:
        contents = stream.read(MAX_AUDIT_BYTES + 1)
    if len(contents) > MAX_AUDIT_BYTES:
        raise ValueError("audit index exceeds size limit")
    try:
        decoded = contents.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("audit index is not UTF-8") from exc
    given = json.loads(decoded, object_pairs_hook=unique_json_object,
                       parse_constant=reject_nonfinite_json)
    if type(given) is not dict:
        raise ValueError("audit index must be a JSON object")
    # Validate the entire seven-case inventory, then independently inspect
    # each NRO and PNG/witness combination again. Hashes recorded in the
    # untrusted index must NEVER be used as input to this regeneration.
    regenerated = build_report(evidence_root, nro_root, revision, run_id,
                               attempt, verify_case=verify_case)
    canonical = (json.dumps(regenerated, sort_keys=True, indent=2,
                            ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    if contents != canonical:
        raise ValueError("audit index differs from independently regenerated evidence")
    return regenerated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_index", type=Path)
    parser.add_argument("published_evidence_root", type=Path)
    parser.add_argument("published_nro_root", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--github-run-id", type=int, required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    args = parser.parse_args()
    try:
        result = verify_audit(args.audit_index,
                              args.published_evidence_root, args.published_nro_root,
                              args.revision, args.github_run_id,
                              args.github_run_attempt)
    except (ValueError, OSError, UnicodeError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print("PASS: independently matched " + str(result["scenario_count"]) +
          " verified NeXium scenarios to the downloaded digest index; "
          "no hardware/audio attestation")


if __name__ == "__main__":
    main()
