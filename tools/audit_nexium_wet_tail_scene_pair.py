#!/usr/bin/env python3
"""Compare independently buffered legacy and opt-in NeXium scene observations.

This is an evidence consistency gate, NOT sample-aligned A/B audio,
proof of a specific STUDIO_C effect, or physical Switch playback.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import analyze_nexium_scene_audio as scene

SCHEMA = "vh-nexium-optin-vs-legacy-scene-evidence/v1"
SCENE_NAMES = ("field_initial", "focus_1", "field_1", "focus_2", "field_2")


class PairEvidenceError(ValueError):
    pass


def read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise PairEvidenceError(f"invalid source report: {path.name}")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise PairEvidenceError("malformed source report") from exc
    if not isinstance(result, dict):
        raise PairEvidenceError("source report not an object")
    return result


def require_exact_scene_report(root: Path) -> dict:
    expected = read_json(root / "scene-audio-report.json")
    observed = scene.analyze(root / "nexium-scenes-s16le-48k.pcm",
                             root / "scene-events.csv")
    if expected != observed:
        raise PairEvidenceError("scene analysis changed or PCM/markers tampered")
    if (observed["schema"] != "vh-nexium-scene-audio/v1"
            or observed["result"] != "REPEATED_SCENE_CORRELATED_PCM_CHANGE"
            or observed["consistent_frequency_class_separation"] is not True
            or observed["hardware_status"] != "HARDWARE NOT TESTED"
            or observed["audible_music_confirmed"] is not False
            or observed["scene_change_proven_causal"] is not False
            or tuple(x["scene"] for x in observed["intervals"]) != SCENE_NAMES):
        raise PairEvidenceError("scene evidence insufficient for comparison")
    return observed


def audit(root: Path, provenance_file: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise PairEvidenceError("missing non-symlinked runtime evidence")
    legacy = require_exact_scene_report(root)
    opt_dir = root / "wet-tail-scenes"
    if opt_dir.is_symlink() or not opt_dir.is_dir():
        raise PairEvidenceError("missing experimental scene evidence")
    wet = require_exact_scene_report(opt_dir)
    pair = read_json(provenance_file)
    witness = read_json(opt_dir / "opt-in-scene-witness.json")
    if (pair.get("result") != "SAME_RUN_WET_TAIL_NRO_PAIR_VERIFIED"
            or type(pair.get("run_id")) is not int or pair["run_id"] < 1
            or type(pair.get("run_attempt")) is not int
            or pair["run_attempt"] < 1
            or type(pair.get("git_sha")) is not str
            or len(pair["git_sha"]) != 40
            or type(pair.get("legacy_sha256")) is not str
            or len(pair["legacy_sha256"]) != 64
            or type(pair.get("wet_tail_sha256")) is not str
            or len(pair["wet_tail_sha256"]) != 64
            or pair["wet_tail_sha256"] == pair["legacy_sha256"]):
        raise PairEvidenceError("invalid prerequisite same-run binary provenance")
    if (witness.get("schema") != "vh-nexium-opt-in-scene-pcm/v1"
            or witness.get("result") != "SAME_RUN_OPT_IN_VIRTUAL_PCM_SCENES_OBSERVED"
            or witness.get("git_sha") != pair["git_sha"]
            or type(witness.get("run_id")) is not int
            or witness["run_id"] != pair["run_id"]
            or witness.get("wet_tail_nro_sha256") != pair["wet_tail_sha256"]
            or witness.get("scene_pcm_sha256") != wet["pcm_sha256"]
            or witness.get("hardware_status") != "HARDWARE NOT TESTED"
            or witness.get("speaker_audio_not_verified") is not True
            or witness.get("host_timing_not_guest_sample_accurate") is not True
            or witness.get("wet_tail_effect_causality_not_proven") is not True
            or type(witness.get("music_label_changed_pixels")) is not list
            or len(witness["music_label_changed_pixels"]) != 4
            or any(type(x) is not int or x < 25
                   for x in witness["music_label_changed_pixels"])):
        raise PairEvidenceError("opt-in witness provenance or scene labels invalid")
    records = []
    for x, y in zip(legacy["intervals"], wet["intervals"]):
        if x["scene"] != y["scene"]:
            raise PairEvidenceError("unaligned scene labels")
        records.append({
            "scene": x["scene"],
            "legacy_rms_by_channel": x["rms_by_channel"],
            "opt_in_rms_by_channel": y["rms_by_channel"],
            "legacy_zero_crossings_hz_by_channel":
                x["zero_crossings_hz_by_channel"],
            "opt_in_zero_crossings_hz_by_channel":
                y["zero_crossings_hz_by_channel"],
        })
    return {
        "schema": SCHEMA,
        "result": "TWO_INDEPENDENT_SCENE_CORRELATED_VIRTUAL_PCM_CAPTURES_VALID",
        "git_sha": pair["git_sha"],
        "run_id": pair["run_id"],
        "run_attempt": pair["run_attempt"],
        "legacy_nro_sha256": pair["legacy_sha256"],
        "opt_in_nro_sha256": pair["wet_tail_sha256"],
        "legacy_pcm_sha256": legacy["pcm_sha256"],
        "opt_in_pcm_sha256": wet["pcm_sha256"],
        "legacy_duration_seconds": legacy["pcm_duration_seconds"],
        "opt_in_duration_seconds": wet["pcm_duration_seconds"],
        "legacy_focus_to_field_zcr_ratio":
            legacy["focus_to_field_zero_crossing_ratio"],
        "opt_in_focus_to_field_zcr_ratio":
            wet["focus_to_field_zero_crossing_ratio"],
        "per_scene_descriptive_observations": records,
        "sample_aligned_A_B_comparison": False,
        "reverb_effect_causally_proven": False,
        "host_marker_guest_sample_accurate": False,
        "physical_switch_hardware_tested": False,
        "audible_audio_confirmed": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_evidence", type=Path)
    parser.add_argument("provenance_report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.runtime_evidence, args.provenance_report)
        if args.output.exists() or args.output.is_symlink():
            raise PairEvidenceError("refuse to overwrite comparison receipt")
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2)
                               + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
    except (PairEvidenceError, scene.SceneEvidenceError, OSError,
            UnicodeError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "PAIR_COMPARISON_REJECTED",
                          "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
