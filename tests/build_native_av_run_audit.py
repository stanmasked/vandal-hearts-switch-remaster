#!/usr/bin/env python3
"""Reverify all NeXium cases and emit a deterministic SHA-256 digest index.

This is NOT a signature, a physical-Switch attestation, or proof of audible audio.
"""
import argparse
import json
from pathlib import Path

from verify_native_av_evidence_inventory import (
    FILES, PREFIX, SCENARIOS, SUFFIX, SD_MODE_BY_SCENARIO, validate_inventory,
)
from verify_native_av_guest_witness import NRO_BY_SCENARIO, hash_file, verify
from verify_native_av_nro_manifest import COMMIT_FILE, MANIFEST, NRO_NAMES, verify_bundle


def snapshot_file_digests(folder, filenames):
    """Fingerprint regular files at a particular verification checkpoint."""
    result = {}
    for filename in filenames:
        path = folder / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing, non-regular or symlinked audit input: " +
                             str(path))
        result[filename] = hash_file(path)
    return result


def build_report(evidence_root, nro_root, revision, run_id, attempt, *,
                 verify_case=verify):
    evidence_root, nro_root = Path(evidence_root), Path(nro_root)
    if (type(run_id) is not int or run_id <= 0 or
            type(attempt) is not int or attempt <= 0):
        raise ValueError("GitHub run identity requires positive integers")
    inventory = validate_inventory(evidence_root)
    bundle = verify_bundle(nro_root, revision, exact_inventory=True)
    all_bundle_files = (*NRO_NAMES, MANIFEST, COMMIT_FILE)
    nro_start = snapshot_file_digests(nro_root, all_bundle_files)
    cases = []
    for scenario in SCENARIOS:
        folder = evidence_root / (PREFIX + scenario + SUFFIX)
        name = NRO_BY_SCENARIO[scenario]
        # The digest published for this case must describe the very
        # same bytes that its independent witness checker inspected.
        evidence_start = snapshot_file_digests(folder, sorted(FILES))
        observed = verify_case(
            folder / "native-av-guest-witness.json",
            folder / "av-before.png", folder / "av-after.png",
            nro_root / name, revision, scenario, run_id, attempt,
            published_nro_dir=nro_root)
        heartbeat = observed["heartbeat_changed_pixels"]
        if type(heartbeat) is not int or heartbeat < 16:
            raise ValueError("invalid verified framebuffer heartbeat: " + scenario)
        evidence_end = snapshot_file_digests(folder, sorted(FILES))
        if evidence_end != evidence_start:
            raise ValueError("NeXium evidence changed during verification: " +
                             scenario)
        cases.append({
            "scenario": scenario,
            "synthetic_sd_mode": SD_MODE_BY_SCENARIO[scenario],
            "nro_filename": name,
            "nro_sha256": bundle["nro_sha256"][name],
            "evidence_sha256": evidence_end,
            "heartbeat_changed_pixels": heartbeat,
        })
    # A later guest check must not be able to modify an earlier case
    # AFTER that earlier case's own two digest snapshots were made.
    for case in cases:
        scenario = case["scenario"]
        folder = evidence_root / (PREFIX + scenario + SUFFIX)
        final_digests = snapshot_file_digests(folder, sorted(FILES))
        if final_digests != case["evidence_sha256"]:
            raise ValueError("previously verified NeXium evidence changed: " +
                             scenario)
    # Check that even unused NRO variants and provenance metadata
    # are unchanged across the entire seven-scenario verification.
    nro_end = snapshot_file_digests(nro_root, all_bundle_files)
    if nro_start != nro_end:
        raise ValueError("NRO artifact changed during seven-case verification")
    return {
        "format": "vh-native-av-seven-case-digest-index-v2",
        "published_nro_file_sha256": nro_end,
        "source_revision": bundle["source_commit"],
        "github_run_id": run_id, "github_run_attempt": attempt,
        "scenario_count": inventory["scenario_count"],
        "cases": cases,
        "physical_hardware_verified": False,
        "audible_audio_verified": False,
        "original_game_assets_included": False,
    }


def write_report(output, report):
    payload = json.dumps(report, sort_keys=True, indent=2,
                         ensure_ascii=True, allow_nan=False) + "\n"
    # Fail closed: never silently overwrite an earlier run's digest index.
    with Path(output).open("x", encoding="ascii") as stream:
        stream.write(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("published_evidence_root", type=Path)
    parser.add_argument("published_nro_root", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--github-run-id", required=True, type=int)
    parser.add_argument("--github-run-attempt", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build_report(
            args.published_evidence_root, args.published_nro_root,
            args.revision, args.github_run_id, args.github_run_attempt)
        write_report(args.output, report)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print("PASS: independently reverified seven cases and wrote digest index; "
          "no hardware/audio attestation")


if __name__ == "__main__":
    main()
