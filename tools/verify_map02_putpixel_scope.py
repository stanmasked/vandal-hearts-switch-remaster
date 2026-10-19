#!/usr/bin/env python3
"""Join observed original PC PutPixel calls to source-keyed DrawOTag FT4.

Validation uses verified source geometry/GTE/VRAM, original AddPrim OT
ordering, actual-format native DrawOTag before/after snapshots and explicit
frame/primitive ordinal markers emitted by the opt-in observer. No color,
pixel coordinate, camera or image data are emitted publicly. Matching a
synthetic fixture does NOT prove genuine gameplay or PS1 hardware behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import private_file, LOG, VRAM_BYTES
from tools.verify_map02_source_native_ft4_join import (
    _source_signature, _native_signature,
)
from tools.verify_map02_native_overdraw import verify_native_overdraw
from tools.map02_pc_writepixel_reference import expected_write_pixel
from tools.map02_observed_blends import summarize_observed_blends

SCHEMA = "vh.map02.native-putpixel-ot.v1"
PIXEL_LOG = "putpixel-native-events.jsonl"
FIELDS = ("stage","step","frame","primitive_ordinal","primitive_type",
          "x","y","before","front","after","abr","semi","textured","accurate")
MAX_CALLS = 64


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def word(raw, addr):
    off = addr * 2
    return raw[off] | (raw[off + 1] << 8)


def verify_pixel_ot(source_dir, native_dir, *, compiler="gcc"):
    source_dir, native_dir = Path(source_dir).absolute(), Path(native_dir).absolute()
    meta_raw = private_file(source_dir, "gpu-putpixel-ot.json", max_bytes=64*1024)
    m = parse_json(meta_raw, "gpu-putpixel-ot.json")
    fields(m, ("schema","source_frame","gpu_draw_frame",
               "overdraw_manifest_sha256", "native_events_sha256",
               "putpixel_events_sha256"), "native pixel/OT join")
    if m["schema"] != SCHEMA:
        raise ValueError("unsupported native pixel/OT evidence schema")
    source_frame = number(m["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(m["gpu_draw_frame"], "GPU DrawOTag frame", 1, 2**32-1)
    overdraw_raw = private_file(source_dir, "gpu-native-overdraw.json", max_bytes=64*1024)
    native_raw = private_file(native_dir, LOG, max_bytes=128*1024)
    pixel_raw = private_file(native_dir, PIXEL_LOG, max_bytes=16*1024)
    sha_check(overdraw_raw, m["overdraw_manifest_sha256"], "overdraw manifest")
    sha_check(native_raw, m["native_events_sha256"], "native GPU event log")
    sha_check(pixel_raw, m["putpixel_events_sha256"], "scoped PutPixel event log")

    verified = verify_native_overdraw(source_dir, native_dir, compiler=compiler)
    if (verified["source_frame"] != source_frame or
            verified["native_gpu_frame"] != gpu_frame):
        raise ValueError("pixel/OT frame assertion differs from verified original trace")
    if verified["source_keyed_ft4_draw_pairs_checked"] < 1:
        raise ValueError("no source-keyed native FT4 to inspect")
    source_raw = private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024)
    source = [parse_json(line, "source GTE FT4") for line in source_raw.splitlines()]
    source_signatures = [_source_signature(e) for e in source]
    pairs = [parse_json(line, "native GPU event") for line in native_raw.splitlines()]
    if len(pairs) % 2:
        raise ValueError("unpaired native GPU event log")

    # 'primitive_ordinal' is one-based? No: 0 for first non-bucket
    # DrawOTag primitive, then 1, 2, ... for every subsequent primitive.
    # GPU transfers do not increment this counter. Do not infer from raw
    # array step, since transfer records can be interleaved in that array.
    native_draws = []
    source_ordinals = set()
    for i in range(0, len(pairs), 2):
        e = pairs[i]
        if e["operation"] != "draw":
            continue
        ordinal = len(native_draws)
        native_draws.append((e, pairs[i+1]))
        sig = _native_signature(e)
        if sig is not None and sig in source_signatures:
            source_ordinals.add(ordinal)
    if len(source_ordinals) != len(source):
        raise ValueError("unmatched source-keyed DrawOTag packets")

    # The source-pinned binary-mode recorder terminates every JSONL
    # event with exactly one LF. Do not accept truncated final records,
    # CRLF or NUL even when a supplied SHA manifest was recomputed.
    if not pixel_raw.endswith(b"\n") or b"\r" in pixel_raw or b"\x00" in pixel_raw:
        raise ValueError("noncanonical scoped PutPixel JSONL line boundaries")
    lines = pixel_raw.split(b"\n")[:-1]
    if not 1 <= len(lines) < MAX_CALLS or any(not line.strip() for line in lines):
        raise ValueError("scoped PutPixel recording empty or reached truncation cap")
    rows = [parse_json(line, f"scoped pixel {i}") for i, line in enumerate(lines)]
    coord = None
    last_ordinal = -1
    grouped = {}
    same_color = requests = opaque = bit15_rises = bit15_falls = 0
    accurate_blend_checked = legacy_blend_checked = 0
    observed_accurate_mode = None
    for index, e in enumerate(rows):
        fields(e, FIELDS, f"scoped pixel {index}")
        if e["stage"] != "native_putpixel":
            raise ValueError("wrong original PC pixel event stage")
        if number(e["step"], "pixel event step", 0, MAX_CALLS-1) != index:
            raise ValueError("non-contiguous scoped PutPixel call indices")
        if number(e["frame"], "PutPixel GPU frame", 1, 2**32-1) != gpu_frame:
            raise ValueError("pixel belongs to a different DrawOTag frame")
        ordinal = number(e["primitive_ordinal"], "native primitive ordinal",
                         0, len(native_draws)-1)
        if ordinal < last_ordinal:
            raise ValueError("scoped PutPixel ordinal moves backward")
        last_ordinal = ordinal
        native_type = native_draws[ordinal][0]["primitive_type"]
        if number(e["primitive_type"], "primitive type", 0, 255) != native_type:
            raise ValueError("PutPixel scoped primitive type disagrees with DrawOTag")
        # The pinned libgpu.c DR_MODE branch only updates persistent
        # texture/window state; it never invokes the raster PutPixel.
        # A same-value call would evade a VRAM-only no-write check.
        if native_type == 5:
            raise ValueError("DR_MODE DrawOTag packet cannot call PutPixel")
        x = number(e["x"], "native pixel x", 0, 1023)
        y = number(e["y"], "native pixel y", 0, 511)
        if coord is None:
            coord = (x, y)
        elif coord != (x, y):
            raise ValueError("mixed sampled PutPixel coordinates")
        for key in ("before", "front", "after"):
            number(e[key], f"BGR555 {key}", 0, 65535)
        number(e["abr"], "ABR", 0, 3)
        semi = number(e["semi"], "semi", 0, 1)
        number(e["textured"], "textured", 0, 1)
        accurate = number(e["accurate"], "accurate mode", 0, 1)
        # AccurateEnabled caches VH_ACCURATE in a function-static int
        # the first time it is called, so one native run cannot switch
        # between legacy and accurate algorithms midway through a log.
        if observed_accurate_mode is None:
            observed_accurate_mode = accurate
        elif observed_accurate_mode != accurate:
            raise ValueError("inconsistent native AccurateEnabled mode in one PutPixel session")
        if semi == 0:
            if e["front"] != e["after"]:
                raise ValueError("opaque PutPixel result differs from actual original copy")
        else:
            # The actual PC WritePixel uses packed 5-bit BlendG1 in
            # accurate mode and clamp/truncate 8-bit arithmetic in the
            # legacy renderer. Every semi-transparency request has a
            # checkable outcome, even if its BGR555 value is unchanged.
            expected = expected_write_pixel(
                e["before"], e["front"], e["abr"], semi,
                e["textured"], e["accurate"])
            if e["after"] != expected:
                raise ValueError(
                    "semi-transparent PutPixel result differs from pinned PC blend")
            if e["accurate"]:
                accurate_blend_checked += 1
            else:
                legacy_blend_checked += 1
        group = grouped.setdefault(ordinal, [])
        if group and group[-1]["after"] != e["before"]:
            raise ValueError("within-primitive native pixel log continuity broken")
        group.append(e)
        same_color += e["before"] == e["after"]
        requests += bool(semi)
        opaque += not semi
        bit15_rises += not (e["before"] & 0x8000) and bool(e["after"] & 0x8000)
        bit15_falls += bool(e["before"] & 0x8000) and not (e["after"] & 0x8000)

    addr = coord[1] * 1024 + coord[0]
    matched_pixel_calls = matched_source_draws = unchanged_source = 0
    source_draws_with_calls = 0
    sampled_source_changed_draws = 0
    sampled_first_changed_pre = None
    sampled_last_changed_post = None
    sampled_bit15_only = sampled_color_only = sampled_color_and_bit15 = 0
    scoped_source_changed_calls = scoped_source_noop_calls = 0
    scoped_source_bit15_only = scoped_source_color_only = 0
    scoped_source_color_and_bit15 = 0
    scoped_source_transient_draws = 0
    source_blend_abr_calls = [0, 0, 0, 0]
    source_blend_accurate_calls = source_blend_legacy_calls = 0
    source_draws_with_multiple_blends = 0
    for ordinal, (before_event, after_event) in enumerate(native_draws):
        before_raw = private_file(native_dir, before_event["snapshot"], expected=VRAM_BYTES)
        after_raw = private_file(native_dir, after_event["snapshot"], expected=VRAM_BYTES)
        before_val, after_val = word(before_raw, addr), word(after_raw, addr)
        group = grouped.get(ordinal, [])
        if group:
            if group[0]["before"] != before_val or group[-1]["after"] != after_val:
                raise ValueError(f"primitive {ordinal}: PutPixel calls contradict VRAM before/after")
            if ordinal in source_ordinals:
                matched_pixel_calls += len(group)
                source_draws_with_calls += 1
                local_changed_calls = 0
                local_blend_calls = 0
                for call in group:
                    if call["semi"]:
                        # Count only calls whose ordinal is proven to
                        # match a source MAP02 FT4, not unrelated draws.
                        source_blend_abr_calls[call["abr"]] += 1
                        source_blend_accurate_calls += bool(call["accurate"])
                        source_blend_legacy_calls += not call["accurate"]
                        local_blend_calls += 1
                    pre, post = call["before"], call["after"]
                    if pre == post:
                        scoped_source_noop_calls += 1
                        continue
                    local_changed_calls += 1
                    scoped_source_changed_calls += 1
                    color_changed = (pre & 0x7fff) != (post & 0x7fff)
                    bit15_changed = bool((pre ^ post) & 0x8000)
                    if color_changed and bit15_changed:
                        scoped_source_color_and_bit15 += 1
                    elif color_changed:
                        scoped_source_color_only += 1
                    else:
                        scoped_source_bit15_only += 1
                # Multiple observed native calls can change the selected
                # word and then restore it *inside one primitive*. The
                # primitive's full VRAM snapshots will miss this activity.
                if before_val == after_val and local_changed_calls:
                    scoped_source_transient_draws += 1
                if local_blend_calls >= 2:
                    source_draws_with_multiple_blends += 1
        elif ordinal in source_ordinals and before_val != after_val:
            # This source-keyed FT4 did change a pixel, but there is no
            # captured PutPixel call that explains its effect.
            raise ValueError(f"source FT4 primitive {ordinal}: unexplained pixel change")
        if ordinal in source_ordinals:
            matched_source_draws += 1
            unchanged_source += before_val == after_val
            if before_val != after_val:
                sampled_source_changed_draws += 1
                if sampled_first_changed_pre is None:
                    sampled_first_changed_pre = before_val
                sampled_last_changed_post = after_val
                color_changed = (before_val & 0x7fff) != (after_val & 0x7fff)
                bit15_changed = bool((before_val ^ after_val) & 0x8000)
                if color_changed and bit15_changed:
                    sampled_color_and_bit15 += 1
                elif color_changed:
                    sampled_color_only += 1
                else:
                    sampled_bit15_only += 1

    # Keep the independent main-branch *observed* STP/ABR bins beside the
    # PR's stricter source-pinned PC WritePixel formula/VRAM replay checks.
    # Neither binning nor formula checking authenticates physical PS1 pixels.
    blend_report = summarize_observed_blends(rows)
    all_bins = blend_report["observed_semi_putpixel_by_accuracy_and_abr"]
    observed_semi_calls = sum(b["calls"] for mode in all_bins for b in mode)
    if (observed_semi_calls != requests or
            sum(blend_report["observed_opaque_putpixel_by_accuracy"]) != opaque or
            sum(b["calls"] for b in all_bins[1]) != accurate_blend_checked or
            sum(b["calls"] for b in all_bins[0]) != legacy_blend_checked):
        raise ValueError("independent observed STP/ABR accounting mismatch")
    if accurate_blend_checked + legacy_blend_checked != requests:
        raise ValueError("source-pinned PC blend mode accounting mismatch")
    if (sum(source_blend_abr_calls) !=
            source_blend_accurate_calls + source_blend_legacy_calls or
            sum(source_blend_abr_calls) > requests):
        raise ValueError("source-keyed FT4 semi-blend accounting mismatch")
    if sampled_source_changed_draws != (
            sampled_bit15_only + sampled_color_only + sampled_color_and_bit15):
        raise ValueError("sampled FT4 word-change classification mismatch")
    if (scoped_source_changed_calls !=
            scoped_source_bit15_only + scoped_source_color_only +
            scoped_source_color_and_bit15 or
            matched_pixel_calls != scoped_source_changed_calls + scoped_source_noop_calls):
        raise ValueError("scoped source FT4 PutPixel call accounting mismatch")

    return {
        **blend_report,
        "pixel_ot_manifest_sha256": digest(meta_raw),
        "native_gpu_event_log_sha256": digest(native_raw),
        "scoped_putpixel_log_sha256": digest(pixel_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "native_drawotag_primitives_checked": len(native_draws),
        "source_keyed_ft4_draws_checked": matched_source_draws,
        "source_ft4_draws_with_scoped_calls": source_draws_with_calls,
        "source_ft4_draws_without_observable_word_change": unchanged_source,
        "source_ft4_sampled_changed_word_draws": sampled_source_changed_draws,
        "source_ft4_sampled_bit15_only_changes": sampled_bit15_only,
        "source_ft4_sampled_color_only_changes": sampled_color_only,
        "source_ft4_sampled_color_and_bit15_changes": sampled_color_and_bit15,
        "source_ft4_scoped_changed_putpixel_calls": scoped_source_changed_calls,
        "source_ft4_scoped_unchanged_putpixel_calls": scoped_source_noop_calls,
        "source_ft4_scoped_bit15_only_putpixel_calls": scoped_source_bit15_only,
        "source_ft4_scoped_color_only_putpixel_calls": scoped_source_color_only,
        "source_ft4_scoped_color_and_bit15_putpixel_calls":
            scoped_source_color_and_bit15,
        "source_ft4_scoped_transient_draws_invisible_to_vram_delta":
            scoped_source_transient_draws,
        "source_ft4_scoped_semitransparent_blend_calls":
            sum(source_blend_abr_calls),
        "source_ft4_scoped_semi_blend_abr0_calls": source_blend_abr_calls[0],
        "source_ft4_scoped_semi_blend_abr1_calls": source_blend_abr_calls[1],
        "source_ft4_scoped_semi_blend_abr2_calls": source_blend_abr_calls[2],
        "source_ft4_scoped_semi_blend_abr3_calls": source_blend_abr_calls[3],
        "source_ft4_scoped_accurate_semi_blend_calls":
            source_blend_accurate_calls,
        "source_ft4_scoped_legacy_semi_blend_calls":
            source_blend_legacy_calls,
        "source_ft4_scoped_draws_with_multiple_semi_blends":
            source_draws_with_multiple_blends,
        "source_ft4_sampled_first_changed_pre_equals_last_changed_post": (
            sampled_first_changed_pre == sampled_last_changed_post
            if sampled_first_changed_pre is not None else None),
        "observed_native_putpixel_calls": len(rows),
        "calls_attributed_to_source_keyed_ft4": matched_pixel_calls,
        "actual_same_color_calls_invisible_to_vram_delta": same_color,
        "semi_transparent_putpixel_requests": requests,
        "accurate_pc_blend_results_checked": accurate_blend_checked,
        "legacy_pc_blend_results_checked": legacy_blend_checked,
        "source_pinned_pc_writepixel_effects_verified": True,
        "single_runtime_accurate_mode_consistent": True,
        "opaque_copy_putpixel_calls": opaque,
        "observed_bit15_unset_to_set_calls": bit15_rises,
        "observed_bit15_set_to_unset_calls": bit15_falls,
        "native_vram_primitive_bounds_consistent": True,
        "pixel_to_primitive_frame_ordinal_matched": True,
        "complete_original_pixel_stream_proven": False,
        "no_missing_putpixel_calls_proven": False,
        "source_ft4_sampled_endpoint_causality_verified": False,
        "missing_pixel_cause_identified": False,
        "physical_ps1_abr_mask_correctness_verified": False,
        "original_gameplay_authenticated": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_gpu_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    args = p.parse_args()
    try:
        report = verify_pixel_ot(args.source_bundle, args.native_gpu_capture,
                                 compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
