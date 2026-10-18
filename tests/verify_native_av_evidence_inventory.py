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
# These four guest-only controls have isolated EMPTY SD fixtures, even
# though they exercise distinct synthetic audout fault paths.
SD_MODE_BY_SCENARIO = {
    "empty": "empty",
    "full": "full",
    "partial": "partial",
    "zr": "empty",
    "zl": "empty",
    "resume": "empty",
    "resume_retry": "empty",
}


def unique_json_object(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate SD fixture JSON member: " + key)
        data[key] = value
    return data


def reject_nonfinite(number):
    raise ValueError("non-finite SD fixture JSON number: " + number)


def expected_manifest(mode):
    files = {"empty": [], "partial": ["music.seq"],
             "full": ["music.seq", "music.vh", "music.vb"]}[mode]
    return {
        "fixture_mode": mode,
        "synthetic_only": True,
        "files_created": files,
        "expected_audio_source": {
            "empty": "synthetic", "full": "user_files",
            "partial": "invalid_or_partial",
        }[mode],
        "expected_audout_status": (
            "unavailable_or_error" if mode == "partial" else "initialized"
        ),
        "original_audio_verified": False,
        "audible_audio_verified": False,
    }


def verify_fixture_manifest(path, scenario):
    # Bound the JSON size even if someone publishes arbitrary bytes at
    # the expected name. The generator outputs a small seven-field object.
    if path.stat().st_size > 16384:
        raise ValueError("SD fixture manifest exceeds 16 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=unique_json_object,
                          parse_constant=reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("SD fixture manifest is not valid UTF-8 JSON") from exc
    expected = expected_manifest(SD_MODE_BY_SCENARIO[scenario])
    # Canonical serialization distinguishes JSON booleans from numbers.
    if (type(data) is not dict or
            json.dumps(data, sort_keys=True, allow_nan=False) !=
            json.dumps(expected, sort_keys=True, allow_nan=False)):
        raise ValueError("SD fixture manifest does not match scenario: " + scenario)


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
        scenario = folder.name[len(PREFIX):-len(SUFFIX)]
        verify_fixture_manifest(folder / "sd-fixture-manifest.json", scenario)
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
