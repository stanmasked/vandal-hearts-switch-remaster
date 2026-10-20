#!/usr/bin/env python3
"""Fail-closed, historical six-trial NeXium A/B evidence audit.

This is an offline data-integrity and correlation report, NOT a service-deadlock
or physical Switch-audio test. It never reads ROMs or licensed game samples.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import re
import sys

from decode_map02_prejoin_stage import decode_image
from classify_map02_guest_evidence import classify

SCHEMA = "vh-map02-cpal-alsa-boundary-audit/v1"
PREFIX = "map02-presubmit-nexium-guest-proof-"
EXPECTED = {(ms, n) for ms in (21, 22) for n in (1, 2, 3)}
ARTIFACT = re.compile(r"^map02-presubmit-nexium-guest-proof-(21|22)-r([123])$")
SOURCE = "64a3e81b53d375fae3cfc93b4384ec8e18e68703"
RUN = 39398087760


def require(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(obj, dict), f"{path}: not a JSON object")
    return obj


def raw_monitor(path):
    raw = path.read_bytes()
    require(bool(raw) and len(raw) % 4 == 0,
            f"{path}: missing or misaligned 48 kHz S16LE stereo monitor")
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "frames": len(samples) // 2,
        "nonzero_samples": sum(s != 0 for s in samples),
    }


def inspect_trial(directory, source_sha, run_id, nro_hash, decode=decode_image):
    m = ARTIFACT.fullmatch(directory.name)
    require(m is not None, f"{directory}: unexpected artifact directory")
    latency, repeat = map(int, m.groups())
    manifest = read_json(directory / "manifest.json")
    trial = read_json(directory / "pulse-client-trial.json")
    stage = read_json(directory / "presubmit-guest-prejoin-stage.json")
    pulse = read_json(directory / "pulse-sink-input-observed.json")
    monitor = read_json(directory / "presubmit-monitor-health.json")
    conjunction = read_json(directory / "presubmit-guest-evidence-conjunction.json")

    require(manifest.get("schema") == "vh-map02-presubmit-guest-nro/v1",
            "Wrong NRO manifest schema")
    require(manifest.get("source_sha") == source_sha and
            manifest.get("run_id") == run_id and
            manifest.get("nro_sha256") == nro_hash,
            "NRO manifest does not match expected original run/source/binary")
    require(trial.get("schema") == "vh-map02-pulse-client-latency-trial/v1" and
            trial.get("source_sha") == source_sha and
            trial.get("run_id") == run_id and
            trial.get("nro_sha256") == nro_hash and
            trial.get("variant") == str(latency) and
            trial.get("independent_repeat") == repeat and
            trial.get("attempt") == manifest.get("attempt"),
            "Trial identity does not match artifact name or exact source")

    observed = decode(directory / "presubmit-guest-prejoin-stage.png")
    require(observed == stage and
            stage.get("result") == "PREJOIN_STAGE_SNAPSHOT_CAPTURED",
            "CRC-8/XOR guest stage image differs from claimed JSON receipt")
    require(stage.get("cooperative_stop_requested") is True and
            stage.get("snapshot_before_blocking_thread_join") is True,
            "Missing prejoin snapshot/stop markers")
    entered = stage["audout_playbuffer_call_entries"]
    returned = stage["audout_playbuffer_call_returns"]
    require(type(entered) is int and type(returned) is int and
            0 <= returned <= entered, "Impossible guest call counts")

    health = raw_monitor(directory / "presubmit-virtual-sink-s16le-48k.pcm")
    require(monitor.get("schema") == "vh-map02-latency-monitor-health/v1" and
            monitor.get("raw_pcm_sha256") == health["sha256"] and
            monitor.get("raw_bytes") == health["bytes"] and
            monitor.get("stereo_frames") == health["frames"] and
            monitor.get("nonzero_pcm16_samples") == health["nonzero_samples"] and
            monitor.get("all_zero_monitor_pcm") is (health["nonzero_samples"] == 0),
            "Independent PCM bytes disagree with recorded monitor health")
    require(pulse.get("schema") == "vh-map02-pulse-sink-input-observation/v1" and
            pulse.get("unique_target_each_snapshot") is True,
            "NeXium ALSA host sink-input not uniquely identified twice")
    delays = pulse.get("buffer_latency_us")
    require(isinstance(delays, dict) and
            all(type(delays.get(point)) is int and
                0 <= delays[point] <= 1000000 for point in ("during", "after")),
            "PulseAudio observed buffer latency absent or invalid")

    # Re-compute the report verdict from the actual individual per-trial
    # documents. A failed 21-ms guest may have no post-join optical packet.
    optional_names = {
        "optical": "presubmit-guest.json",
        "raster": "presubmit-guest-raster-sequence.json",
        "sink": "presubmit-sink-parity.json",
    }
    optional = {}
    for key, filename in optional_names.items():
        path = directory / filename
        optional[key] = read_json(path) if path.is_file() else None
    recomputed = classify(optional["optical"], monitor,
                          optional["raster"], optional["sink"], pulse, stage)
    require(conjunction.get("schema") ==
            "vh-map02-guest-evidence-conjunction/v1" and
            conjunction.get("classification") == recomputed["classification"] and
            conjunction.get("prejoin_audout_call_entries") == entered and
            conjunction.get("prejoin_audout_call_returns") == returned and
            conjunction.get("audout_playbuffer_stall_proven") is False and
            conjunction.get("guest_join_deadlock_proven") is False,
            "Stored correlation report contradicts independent evidence")

    return {
        "hint_ms": latency, "repeat": repeat,
        "stage_name": stage["stage_name"],
        "audout_call_entries": entered,
        "audout_call_returns": returned,
        "virtual_monitor_pcm_nonzero_samples": health["nonzero_samples"],
        "buffer_latency_during_us": delays["during"],
        "buffer_latency_after_us": delays["after"],
        "classification": recomputed["classification"],
        "postjoin_guest_receipt_valid": recomputed["guest_8page_receipt_valid"],
        "all_8_pcm_pages_found": recomputed["exact_8_individual_sink_page_matches"],
        "original_artifact_directory": directory.name,
    }


def audit(root, source_sha=SOURCE, run_id=RUN, decode=decode_image):
    nro_dir = root / "map02-audout-presubmit-research-nro"
    nro = nro_dir / "vandal-hearts-map02-audio.nro"
    binary = nro.read_bytes()
    require(len(binary) > 20 and binary[16:20] == b"NRO0",
            "Missing original same-run research NRO")
    digest = hashlib.sha256(binary).hexdigest()
    original = read_json(nro_dir / "manifest.json")
    require(original.get("schema") == "vh-map02-presubmit-guest-nro/v1" and
            original.get("source_sha") == source_sha and
            original.get("run_id") == run_id and
            original.get("nro_sha256") == digest,
            "Research NRO original provenance mismatch")
    require((nro_dir / "nro.sha256").read_text().split()[0] == digest,
            "Original research NRO SHA-256 manifest mismatch")
    directories = sorted(p for p in root.iterdir()
                         if p.is_dir() and p.name.startswith(PREFIX))
    names = [ARTIFACT.fullmatch(d.name) for d in directories]
    require(len(names) == 6 and all(names),
            "Required six independently named guest artifacts missing/extra")
    cases = {(int(m.group(1)), int(m.group(2))) for m in names}
    require(cases == EXPECTED, "Missing or duplicate 21/22-ms repetition")
    rows = [inspect_trial(p, source_sha, run_id, digest, decode) for p in directories]
    rows.sort(key=lambda r: (r["hint_ms"], r["repeat"]))
    by_hint = {
        str(ms): {
            "trials": 3,
            "zero_monitor_pcm_trials": sum(
                r["virtual_monitor_pcm_nonzero_samples"] == 0
                for r in rows if r["hint_ms"] == ms),
            "completed_cleanup_trials": sum(
                r["stage_name"] == "CLEANUP_COMPLETED"
                for r in rows if r["hint_ms"] == ms),
            "observed_buffer_latencies_us": [
                r["buffer_latency_during_us"] for r in rows
                if r["hint_ms"] == ms],
        } for ms in (21, 22)
    }
    return {
        "schema": SCHEMA, "source_sha": source_sha,
        "original_run_id": run_id, "nro_sha256": digest,
        "trials": rows, "by_hint": by_hint,
        "all_six_artifact_provenance_and_pcm_integrity_verified": True,
        "buffer_hint_causality_proven": False,
        "audout_service_deadlock_proven": False,
        "physical_nintendo_switch_audio_proven": False,
        "interpretation": (
            "Observed association across six runs of the same research NRO; "
            "host ALSA/CPAL/PulseAudio buffer state was sampled, not actively "
            "controlled or synchronized to first guest audoutPlayBuffer. "
            "A single prejoin CRC-8 snapshot cannot prove an infinite deadlock."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-sha", default=SOURCE)
    parser.add_argument("--run-id", type=int, default=RUN)
    args = parser.parse_args()
    try:
        result = audit(args.root, args.source_sha, args.run_id)
        status = 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        result = {
            "schema": SCHEMA, "result": "UNVERIFIED",
            "reason": str(exc),
            "all_six_artifact_provenance_and_pcm_integrity_verified": False,
            "buffer_hint_causality_proven": False,
            "audout_service_deadlock_proven": False,
        }
        status = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(result, sort_keys=True, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
