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
from verify_native_av_nro_manifest import verify_bundle

SCENARIOS = {
    "empty": ("synthetic", "initialized", "buffers_returned"),
    "full": ("user_files", "initialized", "buffers_returned"),
    "partial": ("invalid_or_partial", "unavailable_or_error", "inactive_or_error"),
    "zr": ("synthetic", "initialized", "buffers_returned"),
    "zl": ("synthetic", "unavailable_or_error", "inactive_or_error"),
    "resume": ("synthetic", "initialized", "buffers_returned"),
    "resume_retry": ("synthetic", "initialized", "buffers_returned"),
}

# Bind the emulator scenario to the exact NRO image published in this
# build, rather than accepting any valid NRO digest in its own witness.
NRO_BY_SCENARIO = {
    "empty": "libnx-ps1-music-av.nro",
    "full": "libnx-ps1-music-av.nro",
    "partial": "libnx-ps1-music-av.nro",
    "zr": "libnx-ps1-music-av-zr.nro",
    "zl": "libnx-ps1-music-av-zl.nro",
    "resume": "libnx-ps1-music-av-resume.nro",
    "resume_retry": "libnx-ps1-music-av-resume-retry.nro",
}

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
WITNESS_FIELDS = frozenset({
    "format", "source_revision", "github_run_id", "github_run_attempt",
    "nro_sha256", "first_frame_sha256", "second_frame_sha256",
    "required_checks", "observation", "audible_audio_verified",
    "physical_switch_verified",
})


def unique_json_object(pairs):
    """Reject ambiguous duplicate members at every nested JSON level."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON member: " + key)
        obj[key] = value
    return obj


def reject_nonfinite_json(value):
    raise ValueError("non-finite JSON number rejected: " + value)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def hash_file(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def verify(witness, first, second, nro, revision, scenario,
           github_run_id, github_run_attempt, *, published_nro_dir=None):
    """Return recomputed observations; never trust the stored verdict alone."""
    require(scenario in SCENARIOS, "unknown guest scenario")
    require(HEX40.fullmatch(revision) is not None, "invalid source commit")
    data = json.loads(
        witness.read_text(encoding="utf-8"),
        object_pairs_hook=unique_json_object,
        parse_constant=reject_nonfinite_json)
    require(type(data) is dict, "witness must be an object")
    require(data.keys() == WITNESS_FIELDS,
            "witness has missing or unexpected top-level fields")
    require(data.get("format") == "vh-native-av-guest-witness-v1",
            "unsupported witness format")
    require(data.get("source_revision") == revision, "source revision mismatch")
    require(type(github_run_id) is int and github_run_id > 0 and
            type(github_run_attempt) is int and github_run_attempt > 0,
            "invalid expected GitHub run identity")
    require(type(data.get("github_run_id")) is int and
            data["github_run_id"] == github_run_id,
            "GitHub run ID mismatch")
    require(type(data.get("github_run_attempt")) is int and
            data["github_run_attempt"] == github_run_attempt,
            "GitHub attempt mismatch")
    for label, path in (
        ("nro_sha256", nro),
        ("first_frame_sha256", first),
        ("second_frame_sha256", second),
    ):
        claim = data.get(label)
        require(type(claim) is str and HEX64.fullmatch(claim) is not None,
                "invalid " + label)
        require(hash_file(path) == claim, label + " mismatch")
    if published_nro_dir is not None:
        bundle = verify_bundle(published_nro_dir, revision, exact_inventory=True)
        expected_digest = bundle["nro_sha256"][NRO_BY_SCENARIO[scenario]]
        require(hash_file(nro) == expected_digest,
                "published NRO variant digest does not match guest scenario: " +
                scenario)
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
    parser.add_argument("--github-run-id", required=True, type=int)
    parser.add_argument("--github-run-attempt", required=True, type=int)
    parser.add_argument("--published-nro-dir", type=Path,
                        help="require the NRO to match this scenario's binary in a full published artifact bundle")
    args = parser.parse_args()
    try:
        result = verify(args.witness, args.before, args.after, args.nro,
                        args.revision, args.scenario,
                        args.github_run_id, args.github_run_attempt,
                        published_nro_dir=args.published_nro_dir)
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
