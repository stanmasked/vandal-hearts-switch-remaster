#!/usr/bin/env python3
"""Re-audit measured PulseAudio host buffers from the six Stage265 raw files.

This is a same-workload observational analysis, not a CPAL callback, driver
threshold, causality, guest deadlock, or physical Switch speaker test.
"""
import argparse
import json
from pathlib import Path

from audit_map02_cpal_alsa_boundary import audit, require
from report_pulse_sink_input_latency import summarize
from verify_map02_nexium_one_binary import (
    verify_evidence_attempts, verify_host_links
)

SCHEMA = "vh-map02-observed-host-buffer-ordering/v1"
RUN = 39411672432
SOURCE = "b6f93340a95506e783303311881ea1c6f58ec24a"


def read_json(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(obj, dict), f"{path}: expected JSON object")
    return obj


def independently_decode_host_buffer(root, ms, repeat):
    name = f"map02-presubmit-nexium-guest-proof-{ms}-r{repeat}"
    d = root / name
    during_file = d / "pulse-sink-inputs-during.txt"
    after_file = d / "pulse-sink-inputs-after-input.txt"
    during = during_file.read_text(encoding="utf-8")
    after = after_file.read_text(encoding="utf-8")
    require(bool(during.strip()) and bool(after.strip()),
            f"{name}: missing raw host buffer snapshots")
    parsed = summarize(during, after)
    stored = read_json(d / "pulse-sink-input-observed.json")
    require(parsed == stored, f"{name}: raw pactl snapshots mismatch stored parser report")
    require(parsed.get("unique_target_each_snapshot") is True,
            f"{name}: host NeXium target ambiguous")
    entries = parsed["nexium_stereo_48k_matches"]
    require(all(len(entries[key]) == 1 for key in ("during", "after")),
            f"{name}: no unique ALSA playback client in both snapshots")
    during_latency = parsed["buffer_latency_us"]["during"]
    after_latency = parsed["buffer_latency_us"]["after"]
    require(type(during_latency) is int and during_latency >= 0 and
            type(after_latency) is int and after_latency >= 0,
            f"{name}: missing actual observed PulseAudio buffer latency")
    return {"hint_ms": ms, "repeat": repeat,
            "pulse_buffer_during_us": during_latency,
            "pulse_buffer_after_us": after_latency,
            "during_target_process": entries["during"][0]["application"],
            "after_target_process": entries["after"][0]["application"],
            "pulse_raw_snapshot_parser_verified": True}


def compare_separation(rows):
    """Can an exact 1D cutoff classify these sampled values (either way)?

    Single-time Pulse 'Buffer Latency' is NOT a stream callback size, a
    period, or a hidden causal variable; this only tests a literal cutoff
    hypothesis on the six *recorded* numbers, nothing more.
    """
    require(len(rows) == 6, "Exactly six independent trials required")
    keys = [(r["hint_ms"], r["repeat"]) for r in rows]
    require(set(keys) == {(ms, r) for ms in (21, 22) for r in (1, 2, 3)}
            and len(set(keys)) == 6,
            "Duplicate, mislabeled or missing original 21/22-ms trial")
    valid_status = {
        21: ("OPTICAL_MISSING_ZERO_VIRTUAL_SINK", "ENTERED_PLAYBUFFER", 0),
        22: ("EIGHT_INDIVIDUAL_PAGES_IN_NONZERO_VIRTUAL_SINK", "CLEANUP_COMPLETED", 1)
    }
    for row in rows:
        ms = row["hint_ms"]
        classification, stage, nonzero = valid_status[ms]
        require(row["classification"] == classification and
                row["stage_name"] == stage and
                (row["virtual_monitor_pcm_nonzero_samples"] > 0) == bool(nonzero)
                and (row["audout_call_entries"] > 0)
                and (row["audout_call_returns"] == 0 if ms == 21
                     else row["audout_call_returns"] == row["audout_call_entries"]),
                "Actual guest optical/PCM result deviates from six-trial observation")
        require(type(row["pulse_buffer_during_us"]) is int and
                row["pulse_buffer_during_us"] >= 0,
                "Missing valid observed PulseAudio buffer sample")
    failed = sorted(r["pulse_buffer_during_us"] for r in rows if r["hint_ms"] == 21)
    succeeded = sorted(r["pulse_buffer_during_us"] for r in rows if r["hint_ms"] == 22)
    # If high values guaranteed success, every success must exceed every
    # failure. If low values guaranteed success, inverse must hold.
    # Equality across opposite outcome classes also prevents a strict cutoff.
    high_separable = min(succeeded) > max(failed)
    low_separable = max(succeeded) < min(failed)
    return {
        "six_required_trials": 6,
        "failure_hint_ms": 21,
        "success_hint_ms": 22,
        "failed_observed_buffer_us": failed,
        "successful_observed_buffer_us": succeeded,
        "one_cutoff_high_buffer_means_success_compatible": high_separable,
        "one_cutoff_low_buffer_means_success_compatible": low_separable,
        "one_monotonic_cutoff_in_either_direction_compatible":
            high_separable or low_separable,
        "classification_basis": "same-run guest CRC8, true monitor PCM bytes and original Pulse sink snapshots",
        "one_sample_per_timepoint_not_callback_period": True,
        "cpal_alsa_root_cause_proven": False,
        "guest_service_deadlock_proven": False,
        "physical_switch_dac_verified": False,
    }


def report(root, run_id=RUN, source_sha=SOURCE):
    identity = verify_host_links(root, source_sha, run_id)
    require(identity["same_host_executable_sha256_all_six_verified"],
            "Same host executable not verified in all six guest artifacts")
    attempt = verify_evidence_attempts(root, source_sha, run_id)
    original = audit(root, source_sha, run_id)
    require(original["all_six_artifact_provenance_and_pcm_integrity_verified"],
            "Raw NRO/PNG/PCM audit not confirmed")
    rows = []
    for trial in original["trials"]:
        evidence = independently_decode_host_buffer(
            root, trial["hint_ms"], trial["repeat"])
        require(trial["buffer_latency_during_us"] == evidence["pulse_buffer_during_us"] and
                trial["buffer_latency_after_us"] == evidence["pulse_buffer_after_us"],
                "Audited Pulse buffer sample differs from raw source")
        rows.append({**trial, **evidence})
    classification = compare_separation(rows)
    require(classification["one_monotonic_cutoff_in_either_direction_compatible"] is False,
            "Historical samples unexpectedly permit a monotonic cutoff")
    return {
        "schema": SCHEMA,
        "result": "SIX_TRIAL_HOST_BUFFER_OBSERVATIONS_INDEPENDENTLY_REDECODED",
        "source_sha": source_sha, "run_id": run_id,
        "verified_run_attempt": attempt,
        "same_guest_nro_sha256_all_six_verified": True,
        "same_nexium_host_executable_sha256_all_six_verified": True,
        "nexium_host_executable_sha256": identity["host_executable_sha256"],
        "raw_pulse_snapshots_redecoded_for_all_six": True,
        "raw_guest_png_crc8_pcm_and_provenance_all_six_verified": True,
        "observational_only": True,
        "comparison": classification,
        "trials": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run-id", type=int, default=RUN)
    parser.add_argument("--source-sha", default=SOURCE)
    parser.add_argument("--output", required=True, type=Path)
    opts = parser.parse_args()
    try:
        data = report(opts.root, opts.run_id, opts.source_sha)
        ret = 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        data = {
            "schema": SCHEMA, "result": "UNVERIFIED", "reason": str(exc),
            "raw_pulse_snapshots_redecoded_for_all_six": False,
            "same_nexium_host_executable_sha256_all_six_verified": False,
            "raw_guest_png_crc8_pcm_and_provenance_all_six_verified": False,
            "cpal_alsa_root_cause_proven": False,
            "physical_switch_dac_verified": False,
        }
        ret = 1
    opts.output.parent.mkdir(parents=True, exist_ok=True)
    opts.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps(data, indent=2, sort_keys=True))
    return ret


if __name__ == "__main__":
    raise SystemExit(main())
