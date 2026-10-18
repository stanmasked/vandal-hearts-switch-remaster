#!/usr/bin/env python3
"""Independent private MAP02 CD/GPU/process -> native PC RGB24/PNG final join.

This is intentionally a read-only local verifier. Full original CD/GPU/GTE/
process evidence is revalidated independently of the GPU VRAM/PNG/RGB24
pixel audit. Synthetic tests cannot authenticate a retail image or an
actual rendered MAP02 frame. Never publish any private pixels/disc/ELF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.publish_map02_cd_bound_witness import (
    MANIFEST as CD_GPU_MANIFEST, _validate as validate_cd_manifest,
)
from tools.map02_verified_process_launch import (
    RECEIPT as PROCESS_MANIFEST, RGB24_SCHEMA,
    _validate_receipt as validate_process,
)
from tools.verify_map02_cycle_cd_gpu_join import (
    CYCLE_RECEIPT, _cycle_receipt, _private_evidence_snapshot,
    verify_cycle_cd_gpu_join,
)
from tools.verify_map02_pc_present_rgb24 import (
    RGB24_NAME, RGB24_RECEIPT, compare_native_present_rgb24,
)
from tools.export_map02_native_vram_preview import PNG_NAME
from tools.verify_map02_frame_bundle import number, parse_json

SCHEMA = "vh.map02.final-cd-gpu-process-rgb24-png-join.v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_final_pc_frame(source, native, scoped, handoff, cycle, preview, rgb,
                          owned_image, upstream, pc_binary, *,
                          frame, compiler="gcc"):
    frame = number(frame, "selected original DrawOTag frame", 1, 2**32 - 1)
    roots = [_private_directory(p) for p in (
        source, native, scoped, handoff, cycle, preview, rgb
    )]
    resolved = tuple(p.resolve() for p in roots)
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(resolved) for b in resolved[i + 1:]):
        raise ValueError("private MAP02 source, GPU, cycle, RGB and PNG roots overlap")
    source, native, scoped, handoff, cycle, preview, rgb = roots
    if ({p.name for p in preview.iterdir()} != {PNG_NAME} or
            {p.name for p in rgb.iterdir()} != {RGB24_NAME, RGB24_RECEIPT}):
        raise ValueError("private PC RGB24 or PNG capture has unexpected entries")

    # Pin the exact content AND inode identity of original CD/GPU/OS
    # process evidence before either expensive independent verification.
    source_before = _private_evidence_snapshot(
        source, CD_GPU_MANIFEST, max_bytes=4096)
    process_before = _private_evidence_snapshot(
        handoff, PROCESS_MANIFEST, max_bytes=4096)
    cycle_before = _cycle_receipt(cycle, frame)
    rgb_before = (
        _private_evidence_snapshot(rgb, RGB24_NAME, max_bytes=1024 * 512 * 3),
        _private_evidence_snapshot(rgb, RGB24_RECEIPT, max_bytes=1024),
    )
    png_before = _private_evidence_snapshot(
        preview, PNG_NAME, max_bytes=1024 * 512 * 4)

    original = validate_cd_manifest(
        parse_json(source_before[0], CD_GPU_MANIFEST))
    process = validate_process(process_before[0])
    session = cycle_before[1]
    if (original["gpu_draw_frame"] != frame or
            process["schema"] != RGB24_SCHEMA or
            process["pc_preoverlay_capture_session_bound"] is not True or
            process["pc_preoverlay_image_sha256"] != digest(rgb_before[0][0]) or
            process["pc_preoverlay_receipt_sha256"] != digest(rgb_before[1][0]) or
            process["gpu_draw_frame"] != frame or
            original["capture_session_sha256"] != session or
            process["capture_session_sha256"] != session or
            original["observed_process_receipt_sha256"] !=
            digest(process_before[0])):
        raise ValueError("final original CD/GPU witness is not bound to this process")

    original_join = verify_cycle_cd_gpu_join(
        source, native, scoped, handoff, cycle, owned_image, upstream,
        pc_binary, frame=frame, compiler=compiler)
    if (original_join["source_cd_gpu_process_witness_sha256"] !=
            digest(source_before[0]) or
            original_join["single_process_cycle_receipt_sha256"] !=
            digest(cycle_before[0]) or
            original_join["capture_session_sha256"] != session or
            original_join["same_process_event_order_and_prior_cd_gpu_witness_join_verified"]
            is not True or
            original_join["same_process_draw_primitive_count_matches_native_gpu_windows"]
            is not True):
        raise ValueError("full CD/GPU/process join is inconsistent with pinned records")
    if (original_join["observed_pc_hires_present_backend"] is not False or
            original_join["presented_framebuffer_verified"] is not False or
            original_join["original_map02_rendering_proven"] is not False):
        raise ValueError("full original CD/GPU join overstates native PC presentation")

    rgb_join = compare_native_present_rgb24(
        native, cycle, preview, rgb, frame=frame)
    if (rgb_join["capture_session_sha256"] != session or
            rgb_join["gpu_draw_frame"] != frame or
            rgb_join["native_draw_pairs"] !=
            original_join["verified_draw_primitive_count"] or
            rgb_join["observed_pc_display_source_rect"] !=
            original_join["observed_pc_display_source_rect"] or
            rgb_join["private_pc_preoverlay_rgb24_sha256"] !=
            digest(rgb_before[0][0]) or
            rgb_join["private_png_sha256"] != digest(png_before[0]) or
            rgb_join["bottom_up_pc_rgb24_matches_native_vram"] is not True or
            rgb_join["private_png_matches_native_vram"] is not True or
            rgb_join["same_process_rgb24_receipt_matches_cycle_nonce_and_frame"]
            is not True or
            rgb_join["presented_host_window_authenticated"] is not False):
        raise ValueError("original CD/GPU/process and PC RGB24/PNG evidence differ")

    # No state can be swapped while the unrelated expensive validators run.
    if (_private_evidence_snapshot(source, CD_GPU_MANIFEST, max_bytes=4096)
            != source_before or
            _private_evidence_snapshot(handoff, PROCESS_MANIFEST,
                                       max_bytes=4096) != process_before or
            _cycle_receipt(cycle, frame) != cycle_before or
            _private_evidence_snapshot(rgb, RGB24_NAME,
                                       max_bytes=1024 * 512 * 3) != rgb_before[0] or
            _private_evidence_snapshot(rgb, RGB24_RECEIPT,
                                       max_bytes=1024) != rgb_before[1] or
            _private_evidence_snapshot(preview, PNG_NAME,
                                       max_bytes=1024 * 512 * 4) != png_before):
        raise ValueError("final original CD/GPU/process/RGB24 files changed during audit")

    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "capture_session_sha256": session,
        "source_cd_gpu_process_witness_sha256": digest(source_before[0]),
        "observed_process_receipt_sha256": digest(process_before[0]),
        "single_process_cycle_receipt_sha256": digest(cycle_before[0]),
        "pc_preoverlay_capture_receipt_sha256": digest(rgb_before[1][0]),
        "pc_preoverlay_rgb24_sha256": digest(rgb_before[0][0]),
        "private_native_vram_png_sha256": digest(png_before[0]),
        "native_display_source_rect": rgb_join["observed_pc_display_source_rect"],
        "matched_native_draw_primitives": rgb_join["native_draw_pairs"],
        "independent_full_cd_gpu_process_witness_verified": True,
        "pc_preoverlay_rgb24_and_native_vram_png_match": True,
        "process_receipt_binds_pc_rgb24_pixels_and_capture_receipt": True,
        "source_pinned_full_elf_execution_claim_from_prior_witness": True,
        "presented_host_window_authenticated": False,
        "full_original_gameplay_authenticated": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
        "game_bytes_uploaded": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_source_bundle", type=Path)
    parser.add_argument("private_native_gpu", type=Path)
    parser.add_argument("private_scoped_capture", type=Path)
    parser.add_argument("private_process_handoff", type=Path)
    parser.add_argument("private_cycle_receipts", type=Path)
    parser.add_argument("private_native_vram_png", type=Path)
    parser.add_argument("private_pc_preoverlay_rgb24", type=Path)
    parser.add_argument("private_owned_game_image", type=Path)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--pc-binary", type=Path, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    args = parser.parse_args()
    try:
        result = verify_final_pc_frame(
            args.private_source_bundle, args.private_native_gpu,
            args.private_scoped_capture, args.private_process_handoff,
            args.private_cycle_receipts, args.private_native_vram_png,
            args.private_pc_preoverlay_rgb24, args.private_owned_game_image,
            args.upstream_checkout, args.pc_binary, frame=args.frame,
            compiler=args.compiler)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("private MAP02 final CD/GPU/process/RGB24 audit unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
