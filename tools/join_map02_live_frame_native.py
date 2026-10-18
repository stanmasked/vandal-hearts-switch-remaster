#!/usr/bin/env python3
"""Fail-closed digest join: native replay + child-pipe image + claimed frame pair.

The replayed live process channel and original native GPU/FT4 logs may still
have been produced by DIFFERENT launches. This file never authenticates
same-session origin or allows HD substitution.
"""
import argparse
import json
from pathlib import Path

from tools.bridge_map02_private_frame_native import bridge
from tools.replay_map02_live_frame_receipt import replay


def join(frame_pair_dir, live_dir, native_dir, source_dir, *,
         launch_receipt, preflight_report, executable, compiler="gcc"):
    first = replay(live_dir, executable=executable)
    joined = bridge(
        frame_pair_dir, native_dir, source_dir,
        launch_receipt=launch_receipt,
        preflight_report=preflight_report,
        executable=executable, compiler=compiler)
    if joined.get("schema") != "vh.map02.private-frame-native-join.v1":
        raise ValueError("MAP02 native frame bridge schema invalid")
    if (type(joined.get("frame")) is not int
            or type(joined.get("width")) is not int
            or type(joined.get("height")) is not int
            or (joined["frame"], joined["width"], joined["height"]) != (
                first["frame"], first["width"], first["height"])):
        raise ValueError("MAP02 native-frame labels do not match live pipe")
    if joined.get("candidate_sha256") != first["image_sha256"]:
        raise ValueError("MAP02 candidate BGR555 pixels differ from live ELF pipe")
    for field in ("strict_native_elf_probe_replay_verified",
                  "same_frame_labels_verified",
                  "private_frame_pair_stable_through_native_replay"):
        if joined.get(field) is not True:
            raise ValueError("MAP02 required independent native bridge gate absent")
    for field in ("frame_bytes_causally_bound_to_executed_game",
                  "pc_port_frame_capture_authenticated",
                  "hd_replacement_authorized"):
        if joined.get(field) is not False:
            raise ValueError("MAP02 native bridge asserted unproven provenance")
    second = replay(live_dir, executable=executable)
    if first != second:
        raise ValueError("MAP02 live pipe evidence changed through native GPU replay")
    return {
        "schema": "vh.map02.live-frame-claimed-pair-native-digest-join.v1",
        "frame": first["frame"], "width": first["width"],
        "height": first["height"],
        "candidate_sha256": first["image_sha256"],
        "executable_sha256": first["executable_sha256"],
        "live_receipt_sha256": first["receipt_sha256"],
        "native_gpu_event_log_sha256": joined["native_gpu_event_log_sha256"],
        "original_launch_receipt_sha256": joined["original_launch_receipt_sha256"],
        "claimed_reference_sha256": joined["reference_sha256"],
        "candidate_pixels_match_replayed_live_pipe": True,
        "native_gpu_trace_independently_replayed": True,
        "live_pipe_stable_during_native_replay": True,
        "same_process_gpu_event_and_frame_causality_authenticated": False,
        "retail_disc_or_ps1_reference_authenticated": False,
        "hd_replacement_authorized": False,
        "private_pixel_bytes_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frame-pair", type=Path, required=True)
    p.add_argument("--live-frame", type=Path, required=True)
    p.add_argument("--native-capture", type=Path, required=True)
    p.add_argument("--source-capture", type=Path, required=True)
    p.add_argument("--launch-receipt", type=Path, required=True)
    p.add_argument("--preflight-report", type=Path, required=True)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = p.parse_args()
    try:
        result = join(
            args.frame_pair, args.live_frame, args.native_capture,
            args.source_capture, launch_receipt=args.launch_receipt,
            preflight_report=args.preflight_report,
            executable=args.executable, compiler=args.compiler)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
