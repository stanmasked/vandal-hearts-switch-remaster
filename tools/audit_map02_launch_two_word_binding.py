#!/usr/bin/env python3
"""Replay two independent private witnesses over the SAME native GPU log.

This is a reproducible SHA/frame cross-check, not process causality attestation:
without a kernel-authenticated recorder channel, even complete software replay
cannot prove which process wrote native GPU or retail MAP02 capture bytes.
Original game bytes and chosen pixel coordinates stay in private directories.
"""
import argparse
import json
from pathlib import Path
import subprocess

from tools.verify_map02_private_capture_receipt import replay_receipt
from tools.verify_map02_putpixel_multi_scope import verify_multi_pixel_ot


def audit_launch_two_word(capture_dir, source_dir, *,
                          launch_receipt, preflight_report, executable,
                          compiler="gcc"):
    """Bind replayed launcher & source FT4 witnesses to identical native bytes."""
    capture_dir = Path(capture_dir).absolute()
    source_dir = Path(source_dir).absolute()
    if (capture_dir.is_symlink() or source_dir.is_symlink()
            or not capture_dir.is_dir() or not source_dir.is_dir()):
        raise ValueError("private source or native capture directory unavailable or linked")
    if capture_dir == source_dir:
        raise ValueError("source FT4 and captured native GPU directories must differ")

    # This independently rechecks the original preflight/executable SHA,
    # full native DDA/VRAM evidence and the exact post-launch JSON receipt.
    launch = replay_receipt(
        capture_dir, receipt_file=launch_receipt,
        preflight_report=preflight_report, executable=executable)
    # This independently repeats source->GTE->FT4/OT/native GPU full-VRAM
    # and both interleaved WritePixel histories.
    sampled = verify_multi_pixel_ot(source_dir, capture_dir,
                                    compiler=compiler)

    if type(launch["frame"]) is not int or launch["frame"] != sampled["native_gpu_frame"]:
        raise ValueError("launch and two-word GPU target frames disagree")
    if launch["raw_evidence_matches_original_receipt"] is not True:
        raise ValueError("original private launch evidence is not replayable")
    # verify_session() populates native_gpu_binding.gpu_events_sha256 from
    # verified original GPU event bytes; the scoped FT4 witness has independently
    # checked its own original native GPU event log's exact SHA.
    native_binding = launch["native_gpu_event_log_sha256"]
    if native_binding != sampled["native_gpu_event_log_sha256"]:
        raise ValueError("launch and two-word FT4 native GPU log digests differ")
    if sampled["distinct_private_vram_words_verified"] != 2:
        raise ValueError("two-word native VRAM observation incomplete")

    return {
        "schema": "vh.map02.private-launch-two-word-join.v1",
        "source_frame": sampled["source_frame"],
        "native_gpu_frame": sampled["native_gpu_frame"],
        "original_launch_receipt_sha256": launch["original_receipt_sha256"],
        "two_word_manifest_sha256": sampled["two_word_manifest_sha256"],
        "native_gpu_event_log_sha256": native_binding,
        "same_native_gpu_log_sha256_verified": True,
        "preflight_executable_and_original_receipt_replayed": True,
        "source_gte_ft4_ot_vram_putpixel_replayed": True,
        "two_distinct_private_words_verified": True,
        "source_keyed_ft4_draws_checked": sampled["source_keyed_ft4_draws_checked"],
        "native_process_to_log_causality_authenticated": False,
        "retail_map02_gameplay_authenticated": False,
        "ps1_or_switch_pixel_equivalence_verified": False,
        "hd_replacement_authorized": False,
        "raw_pixel_coordinates_or_colors_emitted": False,
    }



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_capture_directory", type=Path)
    parser.add_argument("source_bundle_directory", type=Path)
    parser.add_argument("--launch-receipt", required=True, type=Path)
    parser.add_argument("--preflight-report", required=True, type=Path)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        report = audit_launch_two_word(
            args.private_capture_directory, args.source_bundle_directory,
            launch_receipt=args.launch_receipt,
            preflight_report=args.preflight_report,
            executable=args.executable, compiler=args.compiler)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
