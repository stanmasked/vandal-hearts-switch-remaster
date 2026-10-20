#!/usr/bin/env python3
"""Bind native PC pre-overlay RGB24 output to the sealed same-process cycle.

This checks local private evidence; it does not prove pixel correctness,
gameplay authenticity, or a host OS screenshot. The full pixel comparison
is provided separately by verify_map02_pc_present_rgb24.
"""
import hashlib
import json

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_cycle_cd_gpu_join import (
    _cycle_receipt, _private_evidence_snapshot, CYCLE_RECEIPT,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_pc_present_rgb24 import (
    RGB24_NAME, RGB24_RECEIPT, CAPTURE_SCHEMA, CAPTURE_KEYS,
)

MAX_RGB = 1024 * 512 * 3


def verify_preoverlay_session(rgb_dir, cycle_dir, *, frame,
                              expected_session_sha256):
    frame = number(frame, "target PC draw frame", 1, 2**32 - 1)
    if (type(expected_session_sha256) is not str or
            len(expected_session_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in expected_session_sha256)):
        raise ValueError("invalid expected PC capture session digest")
    rgb = _private_directory(rgb_dir)
    cycle = _private_directory(cycle_dir)
    if (rgb.resolve() == cycle.resolve() or
            rgb.resolve() in cycle.resolve().parents or
            cycle.resolve() in rgb.resolve().parents):
        raise ValueError("PC RGB24 and cycle evidence directories overlap")
    if {p.name for p in rgb.iterdir()} != {RGB24_NAME, RGB24_RECEIPT}:
        raise ValueError("missing or unexpected private PC RGB24 capture files")

    proof = _cycle_receipt(cycle, frame)
    cycle_event = parse_json(proof[0][:-1], CYCLE_RECEIPT)
    if proof[1] != expected_session_sha256 or cycle_event["present_backend_is_hires"]:
        raise ValueError("PC RGB24 capture cycle nonce or backend differs")
    raw_receipt = _private_evidence_snapshot(rgb, RGB24_RECEIPT, max_bytes=1024)
    receipt_bytes = raw_receipt[0]
    if (receipt_bytes.count(b"\n") != 1 or
            not receipt_bytes.endswith(b"\n") or b"\r" in receipt_bytes):
        raise ValueError("invalid PC RGB24 JSONL canonical terminator")
    record = parse_json(receipt_bytes[:-1], RGB24_RECEIPT)
    fields(record, CAPTURE_KEYS, RGB24_RECEIPT)
    if (record["schema"] != CAPTURE_SCHEMA or
            record["pixel_format"] != "rgb24-bottom-up" or
            record["movie_overlay_active"] is not False or
            record["hires_active"] is not False or
            record["source_pinned"] is not True or
            record["presented_window_authenticated"] is not False):
        raise ValueError("unsupported native PC RGB24 capture flags")
    token = record["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(ch not in "0123456789abcdef" for ch in token) or
            hashlib.sha256(token.encode("ascii")).hexdigest() != proof[1]):
        raise ValueError("PC RGB24 capture nonce differs from verified process")
    rect = cycle_event["display_source_rect"]
    if (number(record["gpu_draw_frame"], "captured frame", 1, 2**32 - 1)
            != frame or
            number(record["width"], "captured width", 1, 1024) != rect[2] or
            number(record["height"], "captured height", 1, 512) != rect[3] or
            number(record["bytes"], "captured RGB24 bytes", 3, MAX_RGB)
            != rect[2] * rect[3] * 3):
        raise ValueError("native PC RGB24 frame, dimensions or byte length differ")
    raw_image = _private_evidence_snapshot(rgb, RGB24_NAME, max_bytes=MAX_RGB)
    if len(raw_image[0]) != record["bytes"]:
        raise ValueError("PC RGB24 image payload length differs from process receipt")
    if (_cycle_receipt(cycle, frame) != proof or
            _private_evidence_snapshot(rgb, RGB24_RECEIPT,
                                       max_bytes=1024) != raw_receipt or
            _private_evidence_snapshot(rgb, RGB24_NAME,
                                       max_bytes=MAX_RGB) != raw_image):
        raise ValueError("private PC RGB24 evidence changed during process verification")
    return {
        "schema": "vh.map02.pc-preoverlay-process-session.v1",
        "gpu_draw_frame": frame,
        "capture_session_sha256": proof[1],
        "pc_rgb24_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "pc_rgb24_image_sha256": hashlib.sha256(raw_image[0]).hexdigest(),
        "native_rect": rect,
        "same_process_capture_nonce_checked": True,
        "original_gameplay_authenticated": False,
        "presented_host_window_authenticated": False,
    }
