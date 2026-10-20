#!/usr/bin/env python3
"""Report *observed* repeat VRAM changes by source-keyed MAP02 native FT4 draws.

Requires an already verified source->GPU FT4 packet join and the claimed
AddPrim/DrawOTag relative ordering gate. Reject incomplete before/after
snapshots and intervening VRAM gaps. This observes BGR555 word differences,
NOT invisible same-color writes, true FT4 pixel coverage, STP/ABR policy,
GPU mask-test/write decisions or physical PlayStation raster equivalence.
All original game bytes remain private. Only aggregate counts and hashes
are output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import (
    fields, number, parse_json, safe_file_max, sha_check,
)
from tools.verify_map02_native_gpu_capture import (
    LOG as NATIVE_LOG, private_file, VRAM_BYTES,
)
from tools.verify_map02_source_native_ft4_join import (
    _native_signature, _source_signature,
)
from tools.verify_map02_source_native_ot_order import verify_ot_join

SCHEMA = "vh.map02.native-overdraw.v1"
VRAM_WIDTH = 1024
VRAM_HEIGHT = 512
VRAM_WORDS = VRAM_WIDTH * VRAM_HEIGHT


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bbox(ft4):
    """Only an axis-aligned screen-space proxy, not a raster fill rule."""
    xy = ft4["xy"]
    xmin = max(0, min(xy[::2]))
    xmax = min(VRAM_WIDTH - 1, max(xy[::2]))
    ymin = max(0, min(xy[1::2]))
    ymax = min(VRAM_HEIGHT - 1, max(xy[1::2]))
    return xmin, ymin, xmax, ymax


def verify_native_overdraw(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    manifest_raw = safe_file_max(source_dir, "gpu-native-overdraw.json", 64 * 1024)
    manifest = parse_json(manifest_raw, "gpu-native-overdraw.json")
    fields(manifest, (
        "schema", "source_frame", "gpu_draw_frame",
        "ot_order_manifest_sha256", "native_events_sha256",
    ), "native overdraw manifest")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unknown native overdraw manifest schema")
    source_frame = number(manifest["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(manifest["gpu_draw_frame"], "native GPU frame", 1, 2**32-1)
    ot_raw = private_file(source_dir, "gpu-ot-order-join.json", max_bytes=64*1024)
    native_raw = private_file(native_dir, NATIVE_LOG, max_bytes=128*1024)
    sha_check(ot_raw, manifest["ot_order_manifest_sha256"], "OT order evidence")
    sha_check(native_raw, manifest["native_events_sha256"], "native GPU event log")

    # This independently rechecks original decoded source, compiled PC GTE,
    # every FT4 corner/UV/page/CLUT/window, source-texture VRAM equality,
    # paired GPU capture and full claimed AddPrim depth/LIFO subsequence.
    ot_report = verify_ot_join(source_dir, native_dir, compiler=compiler)
    if ot_report["source_frame"] != source_frame or ot_report["native_gpu_frame"] != gpu_frame:
        raise ValueError("native overdraw frame binding contradicts verified OT join")

    src_raw = private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024)
    source = [parse_json(line, "source face event") for line in src_raw.splitlines()]
    native = [parse_json(line, "native GPU event") for line in native_raw.splitlines()]
    source_signature = [_source_signature(e) for e in source]
    chosen = {}
    for step in range(0, len(native), 2):
        sig = _native_signature(native[step])
        if sig is None:
            continue
        matches = [i for i, source_sig in enumerate(source_signature) if sig == source_sig]
        if len(matches) > 1:
            raise ValueError("source-matched GPU FT4 packet remains ambiguous")
        if len(matches) == 1:
            chosen[step] = matches[0]
    if len(chosen) != len(source):
        raise ValueError("native source-keyed FT4 evidence incomplete")

    # Each snapshot pair comes from the opt-in *synchronous* native GPU
    # recorder. If any after->next-before bytes differ, the capture has
    # unaccounted intervening VRAM effects and the per-primitive pixel
    # attribution is not trustworthy. Equal snapshots still cannot rule
    # out a write and restoration between sampling instants.
    previous_after = None
    seen = bytearray(VRAM_WORDS)
    seen_inside_bbox = bytearray(VRAM_WORDS)
    # First PRE and last POST values for every word visibly changed by a
    # source-keyed FT4. No coordinate or word value leaves the private audit.
    first_pre_word = {}
    last_post_word = {}
    bit15_only_changes = 0
    color_only_changes = 0
    color_and_bit15_changes = 0
    changed_draw_words = 0
    unique_draw_words = 0
    repeated_draw_words = 0
    repeated_inside_bbox_words = 0
    inside_bbox_words = 0
    outside_bbox_words = 0
    bit15_set_transitions = 0
    bit15_clear_transitions = 0
    unchanged_face_draws = 0
    total_native_draw_pairs = 0
    for step in range(0, len(native), 2):
        event = native[step]
        before = private_file(native_dir, event["snapshot"], expected=VRAM_BYTES)
        after = private_file(native_dir, native[step+1]["snapshot"], expected=VRAM_BYTES)
        if previous_after is not None and before != previous_after:
            raise ValueError(
                f"native event {step}: unobserved VRAM difference between "
                "consecutive recorded GPU operations"
            )
        previous_after = after
        if event["operation"] == "draw":
            total_native_draw_pairs += 1
        if step not in chosen:
            continue
        bounds = _bbox(event["ft4"])
        local_changed = 0
        xmin, ymin, xmax, ymax = bounds
        for byte_offset in range(0, VRAM_BYTES, 2):
            if (before[byte_offset] == after[byte_offset] and
                    before[byte_offset + 1] == after[byte_offset + 1]):
                continue
            local_changed += 1
            changed_draw_words += 1
            address = byte_offset // 2
            pre_word = before[byte_offset] | (before[byte_offset + 1] << 8)
            post_word = after[byte_offset] | (after[byte_offset + 1] << 8)
            if address not in first_pre_word:
                first_pre_word[address] = pre_word
            last_post_word[address] = post_word
            color_changed = (pre_word & 0x7fff) != (post_word & 0x7fff)
            bit15_changed = bool((pre_word ^ post_word) & 0x8000)
            if color_changed and bit15_changed:
                color_and_bit15_changes += 1
            elif color_changed:
                color_only_changes += 1
            else:
                bit15_only_changes += 1
            if seen[address] == 0:
                unique_draw_words += 1
                seen[address] = 1
            elif seen[address] == 1:
                repeated_draw_words += 1
                seen[address] = 2

            x = address % VRAM_WIDTH
            y = address // VRAM_WIDTH
            if xmin <= x <= xmax and ymin <= y <= ymax:
                inside_bbox_words += 1
                if seen_inside_bbox[address] == 0:
                    seen_inside_bbox[address] = 1
                elif seen_inside_bbox[address] == 1:
                    repeated_inside_bbox_words += 1
                    seen_inside_bbox[address] = 2
            else:
                # Do NOT reject: screen XY vs VRAM render-target offsets,
                # drawing-area state and clipping are not source-attested.
                outside_bbox_words += 1
            before_bit15 = (before[byte_offset+1] & 0x80) != 0
            after_bit15 = (after[byte_offset+1] & 0x80) != 0
            if not before_bit15 and after_bit15:
                bit15_set_transitions += 1
            elif before_bit15 and not after_bit15:
                bit15_clear_transitions += 1
        if local_changed == 0:
            unchanged_face_draws += 1

    # This compares the two endpoints of each touched word's selected-FT4
    # history, NOT the first/last frame snapshot or a complete write ledger.
    # Unmatched primitives may also affect a word between these endpoints.
    endpoint_equal = sum(
        last_post_word[address] == initial
        for address, initial in first_pre_word.items()
    )
    repeated_endpoint_equal = sum(
        seen[address] == 2 and last_post_word[address] == initial
        for address, initial in first_pre_word.items()
    )
    if changed_draw_words != (
        bit15_only_changes + color_only_changes + color_and_bit15_changes
    ):
        raise ValueError("FT4 change classification accounting mismatch")

    return {
        "overdraw_manifest_sha256": sha(manifest_raw),
        "source_ot_order_manifest_sha256": sha(ot_raw),
        "native_gpu_event_log_sha256": sha(native_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "source_keyed_ft4_draw_pairs_checked": len(chosen),
        "all_native_gpu_draw_pairs": total_native_draw_pairs,
        "consecutive_native_vram_boundaries_exact": True,
        "changed_vram_words_on_source_ft4_draws": changed_draw_words,
        "distinct_vram_words_changed_by_source_ft4": unique_draw_words,
        "source_ft4_first_pre_equals_last_post_words": endpoint_equal,
        "source_ft4_first_pre_differs_last_post_words":
            unique_draw_words - endpoint_equal,
        "source_ft4_repeatedly_changed_first_pre_equals_last_post_words":
            repeated_endpoint_equal,
        "source_ft4_bit15_only_word_changes": bit15_only_changes,
        "source_ft4_color_only_word_changes": color_only_changes,
        "source_ft4_color_and_bit15_word_changes": color_and_bit15_changes,
        "vram_words_changed_by_two_or_more_source_ft4_draws": repeated_draw_words,
        "changed_words_inside_ft4_screen_aabb_proxy": inside_bbox_words,
        "changed_words_outside_ft4_screen_aabb_proxy": outside_bbox_words,
        "words_changed_by_two_or_more_ft4_inside_screen_aabb_proxy":
            repeated_inside_bbox_words,
        "bit15_unset_to_set_word_changes": bit15_set_transitions,
        "bit15_set_to_unset_word_changes": bit15_clear_transitions,
        "source_ft4_pairs_without_observable_vram_changes": unchanged_face_draws,
        "full_gpu_frame_authenticated": False,
        "intervening_write_then_restore_excluded": False,
        "ft4_word_change_causality_or_coverage_verified": False,
        "ft4_actual_pixel_coverage_verified": False,
        "unchanged_pixel_proves_transparency_or_mask_reject": False,
        "stp_abr_mask_state_correctness_verified": False,
        "ps1_hardware_pixels_verified": False,
        "retail_gameplay_authenticated": False,
        "raw_game_bytes_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_gpu_capture", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = verify_native_overdraw(
            args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
