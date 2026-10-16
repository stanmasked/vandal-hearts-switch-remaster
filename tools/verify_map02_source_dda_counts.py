#!/usr/bin/env python3
"""Bind observed native DDA FT4 texel decisions to source-keyed MAP02 geometry.

The independent GPU snapshot, OT-order, source/GTE and DDA aggregate verifiers
must pass first. Correlate *exact* FT4 packet signatures and DrawOTag ordinals.
Counts of native DDA samples, PutPixel requests and changed VRAM words are
different quantities. In particular, the PC legacy rasterizer may draw a
primitive when native DDA did not sample it. No implication about PS1 hardware
pixel equivalence or authenticated gameplay follows.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_native_gpu_capture import LOG, VRAM_BYTES, private_file
from tools.verify_map02_native_overdraw import verify_native_overdraw
from tools.verify_map02_dda_texel_counts import (
    MANIFEST as COUNTS_MANIFEST, ROWS, verify_dda_counts,
)
from tools.verify_map02_putpixel_scope import (
    PIXEL_LOG, verify_pixel_ot,
)
from tools.verify_map02_source_native_ft4_join import (
    _native_signature, _source_signature, _ft4_palette_state,
    _ft4_audited_crop_classes,
)

SCHEMA = "vh.map02.source-native-dda-count-join.v1"
MANIFEST = "gpu-native-dda-count-join.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_source_dda_counts(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    manifest_raw = private_file(source_dir, MANIFEST, max_bytes=16 * 1024)
    m = parse_json(manifest_raw, MANIFEST)
    fields(m, ("schema", "source_frame", "gpu_draw_frame",
               "overdraw_manifest_sha256", "native_dda_manifest_sha256"),
           "source-native DDA join")
    if m["schema"] != SCHEMA:
        raise ValueError("unexpected source-native DDA join schema")
    frame = number(m["source_frame"], "source frame", 1, 2**32 - 1)
    gpu_frame = number(m["gpu_draw_frame"], "GPU frame", 1, 2**32 - 1)
    overdraw_raw = private_file(source_dir, "gpu-native-overdraw.json",
                                max_bytes=64 * 1024)
    counts_manifest_raw = private_file(native_dir, COUNTS_MANIFEST,
                                       max_bytes=16 * 1024)
    sha_check(overdraw_raw, m["overdraw_manifest_sha256"], "source overdraw manifest")
    sha_check(counts_manifest_raw, m["native_dda_manifest_sha256"],
              "native DDA manifest")

    # Re-evaluate all upstream evidence rather than trusting manifest claims:
    # source positions/camera/GTE, native FT4, VRAM transitions, and OT LIFO.
    overdraw = verify_native_overdraw(source_dir, native_dir, compiler=compiler)
    counts = verify_dda_counts(native_dir, target_frame=gpu_frame)
    if (overdraw["source_frame"] != frame or
            overdraw["native_gpu_frame"] != gpu_frame or
            counts["native_gpu_frame"] != gpu_frame):
        raise ValueError("source/native DDA frame binding disagrees with verified evidence")

    source_raw = private_file(source_dir, "gpu-events.jsonl",
                              max_bytes=256 * 1024)
    gpu_raw = private_file(native_dir, LOG, max_bytes=128 * 1024)
    rows_raw = private_file(native_dir, ROWS, max_bytes=16 * 1024)
    src = [parse_json(line, "source MAP02 face")
           for line in source_raw.splitlines()]
    native_events = [parse_json(line, "native GPU event")
                     for line in gpu_raw.splitlines()]
    draws = [(event, native_events[i+1]) for i, event
             in enumerate(native_events) if i % 2 == 0
             and event["operation"] == "draw"]
    source_sigs = [_source_signature(face) for face in src]
    match_ordinals = []
    for i, signature in enumerate(source_sigs):
        candidates = [
            ordinal for ordinal, (before, after) in enumerate(draws)
            if _native_signature(before) == signature
        ]
        if len(candidates) != 1:
            raise ValueError(
                f"source face {i}: no unique native FT4 DrawOTag ordinal")
        match_ordinals.append(candidates[0])
    if len(set(match_ordinals)) != len(src):
        raise ValueError("one native FT4 attributed to multiple source faces")

    per_ft4 = {}
    for line in rows_raw.splitlines():
        row = parse_json(line, "verified DDA row")
        per_ft4[row["primitive_ordinal"]] = row
    matched = [0, 0, 0]
    unmatched = [0, 0, 0]
    zero_sample_changed_vram = 0
    source_ft4_without_dda_samples = 0
    full_zero_clut_dda_consistent = 0
    possible_stp_abr = [0, 0, 0, 0]
    no_vram_delta = set()
    nonzero_dda_no_vram_delta = set()
    opaque_dda_no_vram_delta = 0
    stp_dda_no_vram_delta = 0
    unmatched_ordinals = set(per_ft4).difference(match_ordinals)
    for ordinal, row in per_ft4.items():
        if ordinal in unmatched_ordinals:
            for i, key in enumerate(("zero", "stp", "opaque")):
                unmatched[i] += row[key]
    for face_index, ordinal in enumerate(match_ordinals):
        row = per_ft4.get(ordinal)
        if row is None:
            raise ValueError("native FT4 DDA sample row missing for source face")
        values = [row[key] for key in ("zero", "stp", "opaque")]
        for i in range(3):
            matched[i] += values[i]
        before_event, after_event = draws[ordinal]
        before = private_file(native_dir, before_event["snapshot"],
                              expected=VRAM_BYTES)
        after = private_file(native_dir, after_event["snapshot"],
                             expected=VRAM_BYTES)
        changed = before != after
        total_samples = sum(values)
        if not changed:
            no_vram_delta.add(ordinal)
            if total_samples:
                nonzero_dda_no_vram_delta.add(ordinal)
            opaque_dda_no_vram_delta += values[2] > 0
            stp_dda_no_vram_delta += values[1] > 0
        if total_samples == 0:
            source_ft4_without_dda_samples += 1
            if changed:
                # The source PC backend can use the independent barycentric
                # raster fallback. This is an observation, NOT a DDA proof.
                zero_sample_changed_vram += 1
        transparent, _, abr = _ft4_palette_state(before, before_event)
        if transparent:
            # For a fully zero 4-bpp CLUT, the *executed* original DDA
            # can only sample BGR555=0, regardless of UV/texture window.
            if values[1] or values[2]:
                raise ValueError(
                    "native FT4 DDA nonzero texel contradicts all-zero 4-bpp CLUT")
            full_zero_clut_dda_consistent += 1
        crop = _ft4_audited_crop_classes(src[face_index], before, before_event)
        if before_event["semi"] == 1 and crop is not None and crop[1]:
            possible_stp_abr[abr] += 1

    # An optional coordinate-scoped PutPixel proof is independent of
    # aggregate DDA selection: it can include barycentric fallback calls
    # and repeated same-color writes. Require BOTH artifacts if either was
    # supplied, then revalidate the existing source/OT/VRAM join as well.
    pixel_manifest = source_dir / "gpu-putpixel-ot.json"
    pixel_log = native_dir / PIXEL_LOG
    pixel_seen = (pixel_manifest.exists() or pixel_manifest.is_symlink() or
                  pixel_log.exists() or pixel_log.is_symlink())
    pixel_report = None
    if pixel_seen:
        if not (pixel_manifest.exists() and pixel_log.exists()):
            raise ValueError("optional scoped PutPixel evidence is incomplete")
        pixel_report = verify_pixel_ot(source_dir, native_dir, compiler=compiler)
        if pixel_report["source_keyed_ft4_draws_checked"] != len(match_ordinals):
            raise ValueError("scoped PutPixel source FT4 count disagrees with DDA join")

    # A full-frame VRAM equality check cannot see a same-color WritePixel
    # or a pixel written and restored during one primitive. Only direct,
    # independently verified PutPixel events for the chosen private (X,Y)
    # may establish those facts; never infer them from DDA counts alone.
    observed_no_delta_calls = set()
    observed_no_delta_same_color = set()
    observed_no_delta_changed_then_restored = set()
    observed_nonzero_dda_no_delta_same_color = set()
    if pixel_report is not None:
        pixel_raw = private_file(native_dir, PIXEL_LOG, max_bytes=16 * 1024)
        for line in pixel_raw.splitlines():
            call = parse_json(line, "verified scoped PutPixel event")
            ordinal = call["primitive_ordinal"]
            if ordinal not in no_vram_delta:
                continue
            observed_no_delta_calls.add(ordinal)
            if call["before"] == call["after"]:
                observed_no_delta_same_color.add(ordinal)
                if ordinal in nonzero_dda_no_vram_delta:
                    observed_nonzero_dda_no_delta_same_color.add(ordinal)
            else:
                # The per-primitive final snapshot is unchanged; a direct
                # intermediate delta necessarily got restored by a later
                # observed write at this coordinate (upstream validator
                # proves the recorded calls are continuous).
                observed_no_delta_changed_then_restored.add(ordinal)

    return {
        "source_dda_join_manifest_sha256": digest(manifest_raw),
        "source_overdraw_manifest_sha256": digest(overdraw_raw),
        "native_dda_manifest_sha256": digest(counts_manifest_raw),
        "native_dda_texel_counts_sha256": digest(rows_raw),
        "source_frame": frame,
        "native_gpu_frame": gpu_frame,
        "source_keyed_ft4_draws_correlated": len(match_ordinals),
        "native_unmatched_ft4_draws": len(unmatched_ordinals),
        "source_ft4_dda_zero_samples": matched[0],
        "source_ft4_dda_nonzero_stp_samples": matched[1],
        "source_ft4_dda_nonzero_opaque_samples": matched[2],
        "other_ft4_dda_zero_samples": unmatched[0],
        "other_ft4_dda_nonzero_stp_samples": unmatched[1],
        "other_ft4_dda_nonzero_opaque_samples": unmatched[2],
        "source_ft4_draws_with_no_dda_samples": source_ft4_without_dda_samples,
        "source_ft4_draws_with_no_dda_samples_but_vram_changes":
            zero_sample_changed_vram,
        "source_ft4_draws_without_vram_change": len(no_vram_delta),
        "source_ft4_nonzero_dda_samples_without_vram_change":
            len(nonzero_dda_no_vram_delta),
        "source_ft4_opaque_dda_samples_without_vram_change":
            opaque_dda_no_vram_delta,
        "source_ft4_stp_dda_samples_without_vram_change":
            stp_dda_no_vram_delta,
        "source_ft4_no_vram_delta_with_observed_putpixel_calls":
            len(observed_no_delta_calls),
        "source_ft4_no_vram_delta_with_direct_same_color_putpixel":
            len(observed_no_delta_same_color),
        "source_ft4_no_vram_delta_with_direct_transient_putpixel_change":
            len(observed_no_delta_changed_then_restored),
        "source_ft4_nonzero_dda_no_vram_delta_with_same_color_putpixel":
            len(observed_nonzero_dda_no_delta_same_color),
        "source_ft4_all_zero_clut_consistent_with_dda": full_zero_clut_dda_consistent,
        "source_ft4_stp_crop_candidates_by_abr": possible_stp_abr,
        "optional_scoped_putpixel_evidence_verified": pixel_report is not None,
        "observed_semi_putpixel_by_accuracy_and_abr":
            pixel_report["observed_semi_putpixel_by_accuracy_and_abr"]
            if pixel_report else None,
        "observed_opaque_putpixel_by_accuracy":
            pixel_report["observed_opaque_putpixel_by_accuracy"]
            if pixel_report else None,
        "blendg1_equation_verified": False,
        "ps1_hardware_abr_equivalence_verified": False,
        "observed_coordinate_scoped_putpixel_calls":
            pixel_report["observed_native_putpixel_calls"] if pixel_report else 0,
        "observed_putpixel_calls_on_source_ft4":
            pixel_report["calls_attributed_to_source_keyed_ft4"] if pixel_report else 0,
        "observed_same_color_putpixel_calls":
            pixel_report["actual_same_color_calls_invisible_to_vram_delta"]
            if pixel_report else 0,
        "source_geometry_gte_and_ot_order_reverified": True,
        "native_dda_sample_counters_reverified": True,
        "source_to_native_gpu_frame_provenance_authenticated": False,
        "fallback_or_same_color_write_reason_proven": False,
        "pixel_writes_equal_to_samples_proven": False,
        "all_dda_sampled_uv_coordinates_captured": False,
        "physical_ps1_raster_equivalence_proven": False,
        "original_gameplay_authenticated": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    args = p.parse_args()
    try:
        report = verify_source_dda_counts(
            args.source_bundle, args.native_capture, compiler=args.compiler)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
