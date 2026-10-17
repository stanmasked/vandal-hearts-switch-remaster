#!/usr/bin/env python3
"""Fail-closed two-word synchronized original-PC DrawOTag/PutPixel audit.

Verify TWO distinct coordinates from ONE bounded interleaved PutPixel JSONL
against the SAME native GPU event stream and full primitive VRAM snapshots.
The source->GTE->FT4->OT joins are fully rechecked. Valid JSONL is still
not proof that the original instrumented executable actually ran.
Only public aggregate counts/hashes are emitted, never raw BGR555/XY data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.map02_pc_writepixel_reference import expected_write_pixel
from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import LOG, VRAM_BYTES, private_file
from tools.verify_map02_native_overdraw import verify_native_overdraw
from tools.verify_map02_putpixel_scope import FIELDS, MAX_CALLS, PIXEL_LOG, word
from tools.verify_map02_source_native_ft4_join import _native_signature, _source_signature

SCHEMA = "vh.map02.native-putpixel-multi-ot.v1"
MANIFEST = "gpu-putpixel-multi-ot.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_multi_pixel_ot(source_dir, native_dir, *, compiler="gcc",
                          manifest_bytes=None):
    source_dir, native_dir = Path(source_dir).absolute(), Path(native_dir).absolute()
    # The private publisher can validate an exact in-memory candidate
    # BEFORE the file exists, avoiding transient, unverified evidence.
    # The public CLI always reads the published file from disk.
    if manifest_bytes is None:
        manifest_raw = private_file(source_dir, MANIFEST, max_bytes=64*1024)
    elif type(manifest_bytes) is bytes and 0 < len(manifest_bytes) <= 64*1024:
        manifest_raw = manifest_bytes
    else:
        raise ValueError("invalid in-memory two-word manifest candidate")
    manifest = parse_json(manifest_raw, MANIFEST)
    fields(manifest, (
        "schema", "source_frame", "gpu_draw_frame",
        "overdraw_manifest_sha256", "native_events_sha256",
        "putpixel_events_sha256",
    ), "native two-word pixel/OT join")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unknown two-word native PutPixel manifest schema")
    source_frame = number(manifest["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(manifest["gpu_draw_frame"], "GPU frame", 1, 2**32-1)
    overdraw_raw = private_file(source_dir, "gpu-native-overdraw.json", max_bytes=64*1024)
    gpu_raw = private_file(native_dir, LOG, max_bytes=128*1024)
    pixel_raw = private_file(native_dir, PIXEL_LOG, max_bytes=16*1024)
    sha_check(overdraw_raw, manifest["overdraw_manifest_sha256"], "overdraw manifest")
    sha_check(gpu_raw, manifest["native_events_sha256"], "native GPU event log")
    sha_check(pixel_raw, manifest["putpixel_events_sha256"], "multi PutPixel event log")

    checked = verify_native_overdraw(source_dir, native_dir, compiler=compiler)
    if (checked["source_frame"], checked["native_gpu_frame"]) != (
            source_frame, gpu_frame):
        raise ValueError("two-word sample frame binding disagrees with verified FT4")
    src_raw = private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024)
    source_signatures = [
        _source_signature(parse_json(line, "source FT4"))
        for line in src_raw.splitlines()
    ]
    gpu_events = [parse_json(line, "native GPU event") for line in gpu_raw.splitlines()]
    native_draws = [gpu_events[i:i+2] for i in range(0, len(gpu_events), 2)
                    if gpu_events[i]["operation"] == "draw"]
    source_ordinals = set()
    for ordinal, (pre, post) in enumerate(native_draws):
        sig = _native_signature(pre)
        if sig is not None and sig in source_signatures:
            source_ordinals.add(ordinal)
    if len(source_ordinals) != len(source_signatures):
        raise ValueError("two-word sample missing uniquely source-keyed FT4")

    if not pixel_raw.endswith(b"\n") or b"\r" in pixel_raw or b"\x00" in pixel_raw:
        raise ValueError("noncanonical two-word PutPixel JSONL")
    lines = pixel_raw.split(b"\n")[:-1]
    if not 2 <= len(lines) < MAX_CALLS or any(not line.strip() for line in lines):
        raise ValueError("two-word PutPixel log empty or reached truncation cap")
    # One shared sequence for BOTH addresses: do not group/re-sort before
    # verifying actual original DrawOTag primitive ordinal chronology.
    coordinates = set()
    grouped = {}
    last_ordinal = -1
    accurate_mode = None
    semi_total = 0
    source_calls = source_semi = source_noops = 0
    source_abr = [0, 0, 0, 0]
    source_changed_calls = source_transient_pairs = 0
    source_multi_blend_pairs = 0
    # Sequence within a DrawOTag primitive, before grouping by coordinate:
    # later tests distinguish A,B from A,B,A without exposing XY.
    ordinal_word_sequence = {}
    for index, line in enumerate(lines):
        e = parse_json(line, f"multi pixel call {index}")
        fields(e, FIELDS, f"multi pixel call {index}")
        if e["stage"] != "native_putpixel":
            raise ValueError("not an original scoped native PutPixel call")
        if number(e["step"], "global multi-word call step", 0, MAX_CALLS-1) != index:
            raise ValueError("multi-word PutPixel calls have discontinuous global steps")
        if number(e["frame"], "native GPU frame", 1, 2**32-1) != gpu_frame:
            raise ValueError("multi-word PutPixel event belongs to another frame")
        ordinal = number(e["primitive_ordinal"], "DrawOTag primitive ordinal",
                         0, len(native_draws)-1)
        if ordinal < last_ordinal:
            raise ValueError("multi-word PutPixel DrawOTag ordinal goes backward")
        last_ordinal = ordinal
        native_type = native_draws[ordinal][0]["primitive_type"]
        if number(e["primitive_type"], "primitive type", 0, 255) != native_type:
            raise ValueError("multi-word PutPixel primitive type mismatch")
        if native_type == 5:
            raise ValueError("DR_MODE cannot call native PutPixel")
        coordinate = (
            number(e["x"], "sample X", 0, 1023),
            number(e["y"], "sample Y", 0, 511),
        )
        coordinates.add(coordinate)
        if len(coordinates) > 2:
            raise ValueError("more than two native VRAM words sampled")
        for key in ("before", "front", "after"):
            number(e[key], f"BGR555 {key}", 0, 65535)
        abr = number(e["abr"], "ABR mode", 0, 3)
        semi = number(e["semi"], "semi", 0, 1)
        textured = number(e["textured"], "textured", 0, 1)
        accurate = number(e["accurate"], "accurate PC mode", 0, 1)
        if accurate_mode is None:
            accurate_mode = accurate
        elif accurate_mode != accurate:
            raise ValueError("inconsistent AccurateEnabled in two-word native stream")
        if expected_write_pixel(e["before"], e["front"], abr, semi,
                                textured, accurate) != e["after"]:
            raise ValueError("two-word PutPixel differs from source-pinned PC WritePixel")
        group = grouped.setdefault((ordinal, coordinate), [])
        ordinal_word_sequence.setdefault(ordinal, []).append(coordinate)
        if group and group[-1]["after"] != e["before"]:
            raise ValueError("two-word PutPixel per-primitive word continuity broken")
        group.append(e)
        semi_total += bool(semi)
        if ordinal in source_ordinals:
            source_calls += 1
            source_noops += e["before"] == e["after"]
            source_changed_calls += e["before"] != e["after"]
            if semi:
                source_semi += 1
                source_abr[abr] += 1

    if len(coordinates) != 2:
        raise ValueError("exactly two distinct native VRAM coordinates required")

    source_changed_word_pairs = 0
    source_word_pairs_with_calls = 0
    source_ft4_draws_with_both_words_observed = 0
    source_ft4_draws_changing_both_words = 0
    source_ft4_draws_with_both_words_semi = 0
    source_ft4_draws_with_word_revisit = 0
    source_ft4_draws_with_both_words_changed_by_putpixel = 0
    source_ft4_draws_with_both_words_writes_but_only_one_net_delta = 0
    # Each GPU primitive snapshot is read once then checked at both words.
    # The native lower gate already checked full-VRAM adjacency and hashes.
    for ordinal, (pre, post) in enumerate(native_draws):
        before = private_file(native_dir, pre["snapshot"], expected=VRAM_BYTES)
        after = private_file(native_dir, post["snapshot"], expected=VRAM_BYTES)
        if ordinal in source_ordinals:
            groups = [grouped.get((ordinal, coord), ()) for coord in coordinates]
            if all(groups):
                source_ft4_draws_with_both_words_observed += 1
                if all(any(e["semi"] for e in group) for group in groups):
                    source_ft4_draws_with_both_words_semi += 1
            # A,B,A (also A,B,B,A) is observable inside one
            # primitive, unlike A,A,B. Neither coordinate is reported.
            sequence = ordinal_word_sequence.get(ordinal, ())
            seen_words = set()
            previous_word = None
            for observed_word in sequence:
                if observed_word in seen_words and observed_word != previous_word:
                    source_ft4_draws_with_word_revisit += 1
                    break
                seen_words.add(observed_word)
                previous_word = observed_word
        local_changed_coordinates = 0
        local_changed_call_coordinates = 0
        for coord in coordinates:
            address = coord[1]*1024 + coord[0]
            pre_value, post_value = word(before, address), word(after, address)
            group = grouped.get((ordinal, coord), ())
            if group:
                if group[0]["before"] != pre_value or group[-1]["after"] != post_value:
                    raise ValueError("two-word PutPixel contradicts native primitive VRAM bounds")
            if ordinal not in source_ordinals:
                continue
            if pre_value != post_value:
                source_changed_word_pairs += 1
                local_changed_coordinates += 1
                if not group:
                    raise ValueError("source-keyed FT4 has unexplained sampled word change")
            if group:
                source_word_pairs_with_calls += 1
                changed = sum(e["before"] != e["after"] for e in group)
                if changed:
                    local_changed_call_coordinates += 1
                blend_count = sum(bool(e["semi"]) for e in group)
                if changed and pre_value == post_value:
                    source_transient_pairs += 1
                if blend_count >= 2:
                    source_multi_blend_pairs += 1
        if ordinal in source_ordinals:
            if local_changed_coordinates == 2:
                source_ft4_draws_changing_both_words += 1
            if local_changed_call_coordinates == 2:
                source_ft4_draws_with_both_words_changed_by_putpixel += 1
                if local_changed_coordinates == 1:
                    source_ft4_draws_with_both_words_writes_but_only_one_net_delta += 1

    if source_semi != sum(source_abr) or source_calls != (
            source_changed_calls + source_noops) or source_semi > semi_total:
        raise ValueError("two-word source FT4 sample accounting mismatch")
    if not (
            source_ft4_draws_with_both_words_writes_but_only_one_net_delta
            <= source_ft4_draws_with_both_words_changed_by_putpixel
            <= source_ft4_draws_with_both_words_observed
            <= len(source_ordinals)):
        raise ValueError("two-word FT4 PutPixel overlap accounting mismatch")
    if source_ft4_draws_changing_both_words > (
            source_ft4_draws_with_both_words_changed_by_putpixel):
        raise ValueError("both-word VRAM changes lack observed PutPixel writes")
    return {
        "two_word_manifest_sha256": sha(manifest_raw),
        "native_gpu_event_log_sha256": sha(gpu_raw),
        "interleaved_putpixel_log_sha256": sha(pixel_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "distinct_private_vram_words_verified": len(coordinates),
        "native_drawotag_primitives_checked": len(native_draws),
        "source_keyed_ft4_draws_checked": len(source_ordinals),
        "all_native_putpixel_calls_observed": len(lines),
        "all_native_semitransparent_calls": semi_total,
        "source_keyed_ft4_putpixel_calls": source_calls,
        "source_keyed_ft4_semitransparent_calls": source_semi,
        "source_ft4_abr0_calls": source_abr[0],
        "source_ft4_abr1_calls": source_abr[1],
        "source_ft4_abr2_calls": source_abr[2],
        "source_ft4_abr3_calls": source_abr[3],
        "source_ft4_changed_putpixel_calls": source_changed_calls,
        "source_ft4_same_value_putpixel_calls": source_noops,
        "source_ft4_changed_word_draw_coordinate_pairs": source_changed_word_pairs,
        "source_ft4_draw_coordinate_pairs_with_calls": source_word_pairs_with_calls,
        "source_ft4_transient_write_restore_pairs": source_transient_pairs,
        "source_ft4_coordinate_pairs_with_multiple_blends": source_multi_blend_pairs,
        "source_ft4_draws_with_both_words_observed":
            source_ft4_draws_with_both_words_observed,
        "source_ft4_draws_changing_both_sampled_words":
            source_ft4_draws_changing_both_words,
        "source_ft4_draws_with_both_words_semitransparent":
            source_ft4_draws_with_both_words_semi,
        "source_ft4_draws_with_interleaved_word_revisit":
            source_ft4_draws_with_word_revisit,
        "source_ft4_draws_with_both_words_changed_by_putpixel":
            source_ft4_draws_with_both_words_changed_by_putpixel,
        "source_ft4_draws_with_both_words_changed_but_one_net_delta":
            source_ft4_draws_with_both_words_writes_but_only_one_net_delta,
        "one_interleaved_global_putpixel_step_sequence": True,
        "two_coordinates_checked_against_same_native_drawotag_snapshots": True,
        "source_pinned_pc_writepixel_results_checked": True,
        "native_capture_process_identity_authenticated": False,
        "complete_original_putpixel_stream_proven": False,
        "physical_ps1_pixel_equivalence_verified": False,
        "real_map02_gameplay_authenticated": False,
        "raw_pixel_coordinates_or_colors_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_gpu_capture", type=Path)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = verify_multi_pixel_ot(
            args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
