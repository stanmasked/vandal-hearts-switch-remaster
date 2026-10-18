#!/usr/bin/env python3
"""Check the exact downloaded NeXium evidence inventory (not audio proof).

This protects against missing, extra, swapped-path, symlinked or
unexpectedly empty published files before pixel/witness verification.
"""
import argparse
import json
from pathlib import Path

SCENARIOS = ("empty", "full", "partial", "zr", "zl", "resume", "resume_retry")
PREFIX = "native-ps1-music-av-nexium-"
SUFFIX = "-evidence"
FILES = frozenset((
    "av-before.png",
    "av-after.png",
    "nexium.log",
    "sd-fixture-manifest.json",
    "native-av-guest-witness.json",
))
REQUIRED_NONEMPTY = FILES - {"nexium.log"}


def validate_inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("published evidence root must be a non-symlink directory")
    expected_dirs = {PREFIX + scenario + SUFFIX for scenario in SCENARIOS}
    entries = list(root.iterdir())
    names = {entry.name for entry in entries}
    if names != expected_dirs:
        raise ValueError("published evidence case directory inventory mismatch: " +
                         "missing=" + repr(sorted(expected_dirs - names)) +
                         " extra=" + repr(sorted(names - expected_dirs)))
    for folder in entries:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("invalid published scenario directory: " + folder.name)
        contents = list(folder.iterdir())
        actual = {entry.name for entry in contents}
        if actual != FILES:
            raise ValueError("published evidence file inventory mismatch in " +
                             folder.name + ": missing=" + repr(sorted(FILES - actual)) +
                             " extra=" + repr(sorted(actual - FILES)))
        for entry in contents:
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("non-regular or symlinked evidence file: " + str(entry))
            if entry.name in REQUIRED_NONEMPTY and entry.stat().st_size == 0:
                raise ValueError("empty required evidence file: " + str(entry))
    return {"scenario_count": len(SCENARIOS),
            "files_per_scenario": len(FILES),
            "physical_hardware_verified": False,
            "audible_audio_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("published_evidence_root", type=Path)
    args = parser.parse_args()
    try:
        report = validate_inventory(args.published_evidence_root)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"verification": "exact_published_evidence_inventory",
                      **report}, sort_keys=True))


if __name__ == "__main__":
    main()
