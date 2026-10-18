#!/usr/bin/env python3
"""Independently verify a NeXium AV guest witness against exact PNG/NRO bytes.

This is a CI-only consistency check, not a signed hardware attestation.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image

from check_native_av_screenshot import (
    inspect_images, inspect_zl_marker, inspect_zr_marker,
    inspect_resume_marker, inspect_resume_retry_marker,
)

SCENARIOS = {
    "empty": ("synthetic", "initialized", "buffers_returned"),
    "full": ("user_files", "initialized", "buffers_returned"),
    "partial": ("invalid_or_partial", "unavailable_or_error", "inactive_or_error"),
    "zr": ("synthetic", "initialized", "buffers_returned"),
    "zl": ("synthetic", "unavailable_or_error", "inactive_or_error"),
    "resume": ("synthetic", "initialized", "buffers_returned"),
    "resume_retry": ("synthetic", "initialized", "buffers_returned"),
}

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hash_file(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify(witness, first, second, nro, revision, scenario):
    """Return recomputed observations; never trust the stored verdict alone."""
    require(scenario in SCENARIOS, "unknown guest scenario")
    require(HEX40.fullmatch(revision) is not None, "invalid source commit")
    data = json.loads(witness.read_text(encoding="utf-8"))
    require(type(data) is dict, "witness must be an object")
    require(data.get("format") == "vh-native-av-guest-witness-v1",
            "unsupported witness format")
    require(data.get("source_revision") == revision, "source revision mismatch")
    for label, path in (
        ("nro_sha256", nro),
        ("first_frame_sha256", first),
        ("second_frame_sha256", second),
    ):
        claim = data.get(label)
        require(type(claim) is str and HEX64.fullmatch(claim) is not None,
                "invalid " + label)
        require(hash_file(path) == claim, label + " mismatch")
    require(data.get("physical_switch_verified") is False,
            "hardware evidence incorrectly claimed")
    require(data.get("audible_audio_verified") is False,
            "audible output incorrectly claimed")

    source, audout, pipeline = SCENARIOS[scenario]
    flags = {
        "audio_source": source,
        "audout_status": audout,
        "audio_pipeline": pipeline,
        "synthetic_scene_switches": source == "synthetic" and scenario != "zl",
        "no_synthetic_scene_switches": source == "user_files",
        "zr_recovery": scenario == "zr",
        "zl_no_replay": scenario == "zl",
        "resume_continuation": scenario in ("resume", "resume_retry"),
        "resume_retry": scenario == "resume_retry",
    }
    checks = data.get("required_checks")
    require(type(checks) is dict and checks.keys() == flags.keys(),
            "missing or extra required checks")
    for key, expected in flags.items():
        actual = checks[key]
        require(type(actual) is type(expected) and actual == expected,
                "required check mismatch: " + key)

    with Image.open(first) as a, Image.open(second) as b:
        observed = inspect_images(a, b)
        last_markers = {
            "zr": inspect_zr_marker(b),
            "zl": inspect_zl_marker(b),
            "resume": inspect_resume_marker(b),
            "resume_retry": inspect_resume_retry_marker(b),
        }

    require(data.get("observation") == observed, "stale or forged observation")
    require(observed["video_framebuffer"] == "observed" and
            observed["grid_hero_marker"] == "observed" and
            type(observed["heartbeat_changed_pixels"]) is int and
            observed["heartbeat_changed_pixels"] >= 16,
            "framebuffer evidence invalid")
    require(observed["audio_source"] == source and
            observed["audout_status"] == audout and
            observed["audio_pipeline_progress"] == pipeline,
            "wrong audio evidence for scenario")
    if flags["synthetic_scene_switches"]:
        require(observed["synthetic_scene_switches"] == "confirmed",
                "missing synthetic scene switching")
    if flags["no_synthetic_scene_switches"]:
        require(observed["synthetic_scene_switches"] == "not_applicable",
                "unexpected user-bank scene switching")
    if scenario == "zr":
        require(observed["guest_zr_recovery"] == "confirmed" and
                last_markers["zr"] == "confirmed",
                "ZR recovery not present on both frames")
    if scenario == "zl":
        require(observed["guest_zl_invalid_clock_no_replay"] == "confirmed" and
                last_markers["zl"] == "confirmed",
                "ZL no-replay not present on both frames")
    if scenario in ("resume", "resume_retry"):
        require(observed["guest_resume_x_y_pcm_continuation"] == "confirmed" and
                last_markers["resume"] == "confirmed",
                "resume continuation not present on both frames")
    if scenario == "resume_retry":
        require(observed["guest_resume_retry_after_fake_open_failure"] ==
                "confirmed" and last_markers["resume_retry"] == "confirmed",
                "synthetic first-open failure not present on both frames")
    for disclaimer in (
        "audible_audio_verified", "actual_gameplay_verified",
        "user_music_identity_verified",
    ):
        require(observed[disclaimer] is False,
                "unexpected proof claim: " + disclaimer)
    require(observed["guest_resume_is_not_home_event"] is True,
            "missing HOME scope disclaimer")
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--witness", required=True, type=Path)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    args = parser.parse_args()
    try:
        result = verify(args.witness, args.before, args.after, args.nro,
                        args.revision, args.scenario)
    except (ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "verification": "passed",
        "scenario": args.scenario,
        "frames_changed": result["heartbeat_changed_pixels"],
        "hardware_attested": False,
        "audible_audio_attested": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
