#!/usr/bin/env python3
"""Compare a PRIVATE PC-present RGB24 scratch dump with native VRAM and PNG.

The pinned PC port writes s_rgbaScratch in BOTTOM-UP row order after BGR555
conversion, before optional OSD, overlays, letterboxing, SDL/GL presentation.
This tool compares *supplied* raw bytes, not an authenticated OS screenshot.
No original assets or binary screenshots are stored in the public repository.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.export_map02_native_vram_preview import (
    PNG_NAME, WIDTH, _read_original_snapshot, bgr555_png,
)
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_cycle_cd_gpu_join import (
    CYCLE_RECEIPT, _cycle_receipt, _private_evidence_snapshot,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_windows import verify_native_windows

RGB24_NAME = "map02-pc-present-preoverlay-rgb24.bin"
RGB24_RECEIPT = "map02-pc-present-preoverlay-receipt.jsonl"
CAPTURE_SCHEMA = "vh.map02.pc-preoverlay-capture.v1"
SCHEMA = "vh.map02.pc-present-rgb24-compare.v2"
CAPTURE_KEYS = ("schema", "capture_session", "gpu_draw_frame", "width",
                "height", "bytes", "pixel_format", "movie_overlay_active",
                "hires_active", "source_pinned", "presented_window_authenticated")


def pc_present_bottom_up(vram, rect):
    """Recreate only pinned pc_gpu_window.c's *pre-overlay* RGB24 loop."""
    if type(rect) is not list or len(rect) != 4:
        raise ValueError("PC present rectangle must have exactly four entries")
    x, y, w, h = rect
    x = number(x, "PC source x", 0, WIDTH - 1)
    y = number(y, "PC source y", 0, 511)
    w = number(w, "PC source width", 1, WIDTH)
    h = number(h, "PC source height", 1, 512)
    if x + w > WIDTH or y + h > 512:
        raise ValueError("PC present rectangle exceeds native GPU VRAM")
    if len(vram) != WIDTH * 512 * 2:
        raise ValueError("native GPU VRAM snapshot must be exactly 1 MiB")
    out = bytearray(w * h * 3)
    for py in range(h):
        source_row = (y + py) * WIDTH
        dest_row = (h - 1 - py) * w * 3
        for px in range(w):
            off = 2 * (source_row + x + px)
            p = vram[off] | (vram[off + 1] << 8)
            dst = dest_row + px * 3
            red, green, blue = p & 31, (p >> 5) & 31, (p >> 10) & 31
            out[dst] = (red << 3) | (red >> 2)
            out[dst + 1] = (green << 3) | (green >> 2)
            out[dst + 2] = (blue << 3) | (blue >> 2)
    return bytes(out)


def compare_native_present_rgb24(native_dir, cycle_dir, preview_dir,
                                 rgb24_dir, *, frame):
    """Validate all four disjoint private inputs; produce only safe hashes.

    The RGB24 file is an external observation whose provenance this tool
    cannot authenticate. A future process-side capture must supply it.
    """
    frame = number(frame, "original PC DrawOTag frame", 1, 2**32 - 1)
    native, cycle, preview, rgbdir = (
        _private_directory(p) for p in
        (native_dir, cycle_dir, preview_dir, rgb24_dir)
    )
    dirs = tuple(p.resolve() for p in (native, cycle, preview, rgbdir))
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(dirs) for b in dirs[i + 1:]):
        raise ValueError("MAP02 evidence, preview and RGB24 directories must be separate")
    if {p.name for p in preview.iterdir()} != {PNG_NAME}:
        raise ValueError("private MAP02 preview directory has unexpected entries")
    if {p.name for p in rgbdir.iterdir()} != {RGB24_NAME, RGB24_RECEIPT}:
        raise ValueError("private PC-present RGB24 directory has unexpected entries")

    proof = _cycle_receipt(cycle, frame)
    event = parse_json(proof[0][:-1], CYCLE_RECEIPT)
    if event["present_backend_is_hires"]:
        raise ValueError("hi-res PC present buffer is not native VRAM RGB24")
    rect = event["display_source_rect"]
    receipt = _private_evidence_snapshot(rgbdir, RGB24_RECEIPT, max_bytes=1024)
    if (receipt[0].count(b"\\n") != 1 or not receipt[0].endswith(b"\\n")
            or b"\\r" in receipt[0]):
        raise ValueError("noncanonical private PC RGB24 capture receipt")
    captured = parse_json(receipt[0][:-1], RGB24_RECEIPT)
    fields(captured, CAPTURE_KEYS, RGB24_RECEIPT)
    if (captured["schema"] != CAPTURE_SCHEMA or
            captured["pixel_format"] != "rgb24-bottom-up" or
            captured["movie_overlay_active"] is not False or
            captured["hires_active"] is not False or
            captured["source_pinned"] is not True or
            captured["presented_window_authenticated"] is not False):
        raise ValueError("unsupported or overstated private PC RGB24 capture receipt")
    token = captured["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(ch not in "0123456789abcdef" for ch in token) or
            hashlib.sha256(token.encode("ascii")).hexdigest() != proof[1]):
        raise ValueError("private PC RGB24 capture session differs from sealed cycle")
    if (number(captured["gpu_draw_frame"], "captured PC frame", 1, 2**32-1)
            != frame or
            number(captured["width"], "captured width", 1, WIDTH)
            != rect[2] or
            number(captured["height"], "captured height", 1, 512)
            != rect[3] or
            number(captured["bytes"], "captured RGB24 bytes", 3, WIDTH * 512 * 3)
            != rect[2] * rect[3] * 3):
        raise ValueError("private PC RGB24 capture frame or dimensions differ")
    audit = verify_native_windows(native, target_frame=frame)
    if (audit["capture_session_sha256"] != proof[1] or
            audit["native_draw_pairs"] !=
            event["observed_draw_primitive_count"]):
        raise ValueError("PC present session or DRAW count does not match native GPU evidence")

    seen = audit["globally_ordered_native_gpu_events"]
    endpoint = (native / f"window-{(seen - 1) // 64:03d}" /
                f"gpu-{(seen - 1) % 64:04d}-vram.bin")
    vram, pinned = _read_original_snapshot(endpoint)
    digest = hashlib.sha256(vram).hexdigest()
    if digest != audit["final_native_vram_sha256"]:
        raise ValueError("native GPU final VRAM endpoint SHA-256 mismatch")
    expected_rgb = pc_present_bottom_up(vram, rect)
    actual_rgb = _private_evidence_snapshot(
        rgbdir, RGB24_NAME, max_bytes=WIDTH * 512 * 3)
    if actual_rgb[0] != expected_rgb:
        raise ValueError("pre-overlay PC RGB24 buffer differs from native VRAM")
    expected_png = bgr555_png(
        vram, x=rect[0], y=rect[1], width=rect[2], height=rect[3])
    actual_png = _private_evidence_snapshot(
        preview, PNG_NAME, max_bytes=WIDTH * 512 * 4)
    if actual_png[0] != expected_png:
        raise ValueError("private PNG differs from native VRAM display rectangle")

    # Recheck each source and both distinct cycle receipt/seal inodes.
    if (verify_native_windows(native, target_frame=frame) != audit or
            _read_original_snapshot(endpoint) != (vram, pinned) or
            _cycle_receipt(cycle, frame) != proof or
            _private_evidence_snapshot(
                rgbdir, RGB24_NAME, max_bytes=WIDTH * 512 * 3) != actual_rgb or
            _private_evidence_snapshot(
                rgbdir, RGB24_RECEIPT, max_bytes=1024) != receipt or
            _private_evidence_snapshot(
                preview, PNG_NAME, max_bytes=WIDTH * 512 * 4) != actual_png):
        raise ValueError("MAP02 RGB24/VRAM/PNG evidence changed during comparison")
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "capture_session_sha256": proof[1],
        "native_draw_pairs": audit["native_draw_pairs"],
        "observed_pc_display_source_rect": rect,
        "final_native_vram_sha256": digest,
        "private_png_sha256": hashlib.sha256(actual_png[0]).hexdigest(),
        "private_pc_preoverlay_rgb24_sha256":
            hashlib.sha256(actual_rgb[0]).hexdigest(),
        "compared_source_pixels": rect[2] * rect[3],
        "bottom_up_pc_rgb24_matches_native_vram": True,
        "same_process_rgb24_receipt_matches_cycle_nonce_and_frame": True,
        "pc_preoverlay_source_pinned_receipt_observed": True,
        "private_png_matches_native_vram": True,
        "external_rgb24_source_provenance_authenticated": False,
        "presented_host_window_authenticated": False,
        "original_map02_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "game_bytes_uploaded": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_native_gpu_windows", type=Path)
    p.add_argument("private_cycle_receipts", type=Path)
    p.add_argument("private_native_png", type=Path)
    p.add_argument("private_pc_preoverlay_rgb24", type=Path)
    p.add_argument("--frame", type=int, required=True)
    args = p.parse_args()
    try:
        result = compare_native_present_rgb24(
            args.private_native_gpu_windows, args.private_cycle_receipts,
            args.private_native_png, args.private_pc_preoverlay_rgb24,
            frame=args.frame)
    except (OSError, ValueError):
        p.error("private MAP02 PC presentation scratch comparison failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
