#!/usr/bin/env python3
"""Bind a *claimed* private BGR555 frame pair to a replayed MAP02 native trace.

Strict ELF/probe and independent GPU/FT4/VRAM replay are required. A matching
frame number + hashes is evidence consistency, NOT a kernel-authenticated
pixel capture, source-disc authenticity or PS1 raster equivalence.
"""
import argparse
import json
from pathlib import Path

from tools.compare_map02_private_bgr555_frames import compare
from tools.audit_map02_launch_two_word_binding import audit_launch_two_word

TRUE_FIELDS = (
    "same_native_gpu_log_sha256_verified",
    "native_elf_image_required_for_join",
    "native_probe_symbols_required_for_join",
    "native_probe_symbols_inspected",
    "native_elf_process_image_observed",
    "private_dependency_inventory_stable_through_replays",
    "original_launcher_receipt_replayed_twice",
    "preflight_executable_and_original_receipt_replayed",
    "source_gte_ft4_ot_vram_putpixel_replayed",
    "two_distinct_private_words_verified",
)
FALSE_FIELDS = (
    "native_process_to_log_causality_authenticated",
    "retail_map02_gameplay_authenticated",
    "ps1_or_switch_pixel_equivalence_verified",
    "hd_replacement_authorized",
    "raw_pixel_coordinates_or_colors_emitted",
)


def bridge(frame_pair_dir, native_dir, source_dir, *, launch_receipt,
           preflight_report, executable, compiler="gcc"):
    """Run two real validators; never consume a caller-authored audit summary."""
    if compiler not in ("gcc", "clang"):
        raise ValueError("MAP02 comparison compiler selector invalid")
    before = compare(frame_pair_dir)
    native = audit_launch_two_word(
        native_dir, source_dir,
        launch_receipt=launch_receipt, preflight_report=preflight_report,
        executable=executable, compiler=compiler,
        require_native_elf_image=True, require_native_probe_symbols=True)
    if not isinstance(native, dict) or native.get("schema") != (
            "vh.map02.private-launch-two-word-join.v1"):
        raise ValueError("MAP02 native launch witness schema invalid")
    if any(native.get(field) is not True for field in TRUE_FIELDS):
        raise ValueError("MAP02 strict native process / GPU witness incomplete")
    if any(native.get(field) is not False for field in FALSE_FIELDS):
        raise ValueError("MAP02 native provenance or HD flag unexpectedly asserted")
    count = native.get("source_keyed_ft4_draws_checked")
    if type(count) is not int or count < 1:
        raise ValueError("MAP02 source-keyed native draw evidence missing")
    if (type(native.get("source_frame")) is not int or
            type(native.get("native_gpu_frame")) is not int or
            native["source_frame"] != before["frame"] or
            native["native_gpu_frame"] != before["frame"]):
        raise ValueError("MAP02 claimed frame and native GPU capture labels differ")
    # Catch even a self-consistent replacement of both a raw image and its
    # manifest while the independent native/source replay was running.
    after = compare(frame_pair_dir)
    if before != after:
        raise ValueError("MAP02 frame pair changed during native witness replay")
    return {
        "schema": "vh.map02.private-frame-native-join.v1",
        "frame": before["frame"],
        "width": before["width"],
        "height": before["height"],
        "reference_sha256": before["reference_sha256"],
        "candidate_sha256": before["candidate_sha256"],
        "frame_manifest_sha256": before["manifest_sha256"],
        "difference_mask_sha256": before["difference_mask_sha256"],
        "different_bgr555_pixels": before["different_bgr555_pixels"],
        "exact_bgr555_pixel_matches": before["exact_bgr555_pixel_matches"],
        "changed_scanlines": before["changed_scanlines"],
        "stp_bit_differences": before["stp_bit_differences"],
        "original_launch_receipt_sha256": native["original_launch_receipt_sha256"],
        "two_word_manifest_sha256": native["two_word_manifest_sha256"],
        "native_gpu_event_log_sha256": native["native_gpu_event_log_sha256"],
        "source_keyed_ft4_draws_checked": count,
        "strict_native_elf_probe_replay_verified": True,
        "same_frame_labels_verified": True,
        "private_frame_pair_stable_through_native_replay": True,
        "frame_bytes_causally_bound_to_executed_game": False,
        "retail_disc_resources_authenticated": False,
        "ps1_reference_capture_authenticated": False,
        "pc_port_frame_capture_authenticated": False,
        "ps1_hardware_pixel_equivalence_verified": False,
        "hd_replacement_authorized": False,
        "raw_pixel_values_or_private_paths_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-pair", required=True, type=Path)
    parser.add_argument("--native-capture", required=True, type=Path)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--launch-receipt", required=True, type=Path)
    parser.add_argument("--preflight-report", required=True, type=Path)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = parser.parse_args()
    try:
        result = bridge(
            args.frame_pair, args.native_capture, args.source_capture,
            launch_receipt=args.launch_receipt,
            preflight_report=args.preflight_report,
            executable=args.executable, compiler=args.compiler)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
