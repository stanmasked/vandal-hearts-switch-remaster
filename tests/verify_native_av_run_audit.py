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


def _read_index(index_path):
    """Read the entire untrusted audit with canonicality checks deferred."""
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
    return contents, given


def verify_audit(index_path, evidence_root, nro_root, revision, run_id, attempt,
                 *, verify_case=verify):
    contents, given = _read_index(index_path)
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


def verify_audit_with_producer_attempt(
        index_path, evidence_root, nro_root, revision, run_id,
        verifier_attempt, *, verify_case=verify):
    """Permit retrying ONLY the consumer job after a producer succeeded.

    GitHub increments GITHUB_RUN_ATTEMPT for a rerun of failed jobs,
    even when the seven guest producers and their artifact were not rerun.
    Recover the original producer attempt from the index, constrain it to
    this run's history, and independently re-check EVERY guest witness
    against that same attempt and the externally supplied SHA/run ID.
    The index by itself is NEVER evidence of an authentic attempt.
    """
    if type(verifier_attempt) is not int or verifier_attempt < 1:
        raise ValueError("verifier attempt must be a positive integer")
    _, claimed = _read_index(index_path)
    producer_attempt = claimed.get("github_run_attempt")
    if (type(producer_attempt) is not int or producer_attempt < 1 or
            producer_attempt > verifier_attempt):
        raise ValueError("published producer attempt outside verifier history")
    return verify_audit(index_path, evidence_root, nro_root, revision,
                        run_id, producer_attempt, verify_case=verify_case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_index", type=Path)
    parser.add_argument("published_evidence_root", type=Path)
    parser.add_argument("published_nro_root", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--github-run-id", type=int, required=True)
    parser.add_argument("--github-run-attempt", type=int, required=True)
    parser.add_argument("--accept-prior-published-attempt", action="store_true",
                        help="Reverify original evidence after a consumer-only CI rerun")
    args = parser.parse_args()
    try:
        verifier = (verify_audit_with_producer_attempt
                    if args.accept_prior_published_attempt else verify_audit)
        result = verifier(args.audit_index,
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
