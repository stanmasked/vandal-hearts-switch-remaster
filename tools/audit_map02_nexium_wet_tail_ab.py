#!/usr/bin/env python3
"""Provenance and co-execution audit for separate NeXium WET_TAIL=0/1 runs.

Neither independent PCM differences nor guest selection screenshots
can prove an isolated/synchronized STUDIO_C effect. Fail closed otherwise.
"""
import argparse
import array
import hashlib
import json
import math
import sys
from pathlib import Path

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pcm_info(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) % 4:
        raise ValueError("Missing/partial stereo 16-bit PCM: " + str(path))
    vals = array.array("h")
    vals.frombytes(raw)
    if sys.byteorder != "little":
        vals.byteswap()
    n = len(vals)
    rms = math.sqrt(sum(float(x) * x for x in vals) / n)
    return {"frames": n // 2, "seconds": round(n / 96000, 3),
            "rms": round(rms, 3),
            "samples_ge_256": sum(abs(x) >= 256 for x in vals),
            "sha256": sha(raw)}

def audit(root, expected_run_id, expected_attempt, expected_sha,
          minimum_seconds=20):
    root = Path(root)
    receipt = json.loads((root / "manifest.json").read_text())
    if receipt.get("schema") != "vh-map02-wet-tail-pair/v1":
        raise ValueError("Invalid pair manifest schema")
    if receipt.get("run_id") != expected_run_id or receipt.get("run_attempt") != expected_attempt:
        raise ValueError("Pair provenance run/attempt mismatch")
    if receipt.get("git_sha") != expected_sha or len(expected_sha) != 40:
        raise ValueError("Pair provenance checkout SHA mismatch")
    if minimum_seconds <= 0:
        raise ValueError("Nonpositive duration gate")
    modes = {}
    for mode in (0, 1):
        name = f"wet-tail-{mode}"
        binary = (root / f"map02-wet-tail-{mode}.nro").read_bytes()
        if len(binary) < 20 or binary[16:20] != b"NRO0":
            raise ValueError(f"Invalid NRO0 binary mode={mode}")
        digest = sha(binary)
        if digest != receipt["legacy_sha256" if mode == 0 else "wet_tail_sha256"]:
            raise ValueError(f"NRO pair checksum mismatch for mode={mode}")
        pcm = pcm_info(root / f"{name}.pcm")
        scene = json.loads((root / f"{name}-scene.json").read_text())
        sink = (root / f"{name}-sinks.txt").read_text(errors="replace")
        optical = bool(
            scene.get("status_blue_pixels", 0) >= 24 and
            scene.get("selection_range_pixels", 0) >= 300 and
            scene.get("cancelled_range_pixels", 10**9) <= 100 and
            scene.get("screen_size") == [1280, 720]
        )
        modes[name] = {"nro_sha256": digest, "nro_bytes": len(binary),
                       "pcm": pcm, "guest_sink_input_observed": "nexium" in sink.lower(),
                       "selection_cancel_optically_verified": optical,
                       "selection_range_pixels": scene.get("selection_range_pixels"),
                       "cancelled_range_pixels": scene.get("cancelled_range_pixels"),
                       "status_blue_pixels": scene.get("status_blue_pixels")}
    first, second = modes["wet-tail-0"], modes["wet-tail-1"]
    distinct_nros = first["nro_sha256"] != second["nro_sha256"]
    sustained_signal = all(
        mode["pcm"]["seconds"] >= minimum_seconds and
        mode["pcm"]["samples_ge_256"] >= 9600 and mode["pcm"]["rms"] >= 32
        for mode in (first, second)
    )
    scene_evidence = all(mode["selection_cancel_optically_verified"] for mode in (first, second))
    sink_evidence = all(mode["guest_sink_input_observed"] for mode in (first, second))
    ok = distinct_nros and sustained_signal and scene_evidence and sink_evidence
    return {"schema": "vh-map02-nexium-wet-tail-ab/v1",
            "run_id": expected_run_id, "run_attempt": expected_attempt,
            "git_sha": expected_sha,
            "modes": modes,
            "checks": {"distinct_mode_binaries": distinct_nros,
                       "both_guest_scene_inputs_observed": scene_evidence,
                       "both_guest_pcm_nonzero": sustained_signal,
                       "both_guest_sink_inputs_observed": sink_evidence,
                       "binary_provenance_from_same_run": True},
            "result": "TWO_MODES_GUEST_AUDIO_AND_SCENE_INPUT_OBSERVED"
                      if ok else "WET_TAIL_GUEST_AB_UNVERIFIED",
            "sample_aligned": False,
            "reverb_tail_causally_proven_by_guest_pcm": False,
            "host_synthetic_reverb_causality_tested_here": False,
            "original_ps1_music_verified": False,
            "physical_switch_audio_tested": False}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--attempt", type=int, required=True)
    p.add_argument("--sha", required=True)
    p.add_argument("--min-seconds", type=float, default=20.0)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        result = audit(args.root, args.run_id, args.attempt, args.sha, args.min_seconds)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        result = {"schema": "vh-map02-nexium-wet-tail-ab/v1",
                  "result": "GUEST_AB_AUDIT_FAILED_CLOSED", "error": str(exc),
                  "reverb_tail_causally_proven_by_guest_pcm": False,
                  "physical_switch_audio_tested": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["result"] == "TWO_MODES_GUEST_AUDIO_AND_SCENE_INPUT_OBSERVED" else 1

if __name__ == "__main__":
    raise SystemExit(main())
