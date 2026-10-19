#!/usr/bin/env python3
"""Strict, privacy-preserving MAP02 source-face -> native PC GPU FT4 packet join.

Requires TWO separately verified private inputs:
  * an original-format decoded MAP02 + source/GTE/VRAM bundle;
  * an opt-in native PC GPU DrawOTag before/after VRAM capture.
The two frame counters are different clocks. An explicit, SHA-bound
user assertion binds them; equality is NEVER assumed or guessed.

A link is accepted only if its GPU XY (0,1,3,2), every UV, tpage,
CLUT and the full active texture window match exactly, there are no
ambiguous duplicates, and the input source/palette VRAM words relevant
to the face agree with the VRAM snapshot before its GPU draw.
No asset bytes, colors, camera values or source locations are output.
This is a *consistency check*, not authentication of retail gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import (
    MAX_FACES, fields, number, parse_json, safe_file_max, sha_check,
    verify_bundle,
)
from tools.verify_map02_native_gpu_capture import (
    LOG as NATIVE_LOG, private_file, verify_capture, VRAM_BYTES,
)
from tools.verify_map02_vram_timeline import (
    EVENT_LIMIT, read_events, referenced_words, verify_timeline,
)

SCHEMA = "vh.map02.source-native-ft4-join.v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _source_signature(event):
    corners = event["gte"]["perimeter_xy"]
    t = event["texture"]
    u, v, w, h = (t["u"], t["v"], t["w"], t["h"])
    xy = [coordinate for index in (0, 1, 3, 2)
          for coordinate in corners[index]]
    uv = [u, v, u+w, v, u, v+h, u+w, v+h]
    window = [t["mask_x"], t["mask_y"], t["offset_x"], t["offset_y"]]
    return xy, uv, t["tpage"], t["clut"], window


def _native_signature(event):
    packet = event["ft4"]
    if event["operation"] != "draw" or packet is None:
        return None
    return (packet["xy"], packet["uv"], packet["tpage"],
            packet["clut"], event["window"])


def _material_bytes_equal(source, before, event):
    """Compare every 16-bit source word that either VRAM source samples.

    The output-frame pixels may legitimately differ due to earlier
    primitives; do not compare whole render-target VRAM with a frozen
    texture reference. If a different texel index selects a different
    CLUT entry, the union of both palettes is checked too.
    """
    texture_a, palette_a = referenced_words(event, source)
    texture_b, palette_b = referenced_words(event, before)
    addresses = texture_a | texture_b | palette_a | palette_b
    for word in addresses:
        offset = word * 2
        if source[offset:offset+2] != before[offset:offset+2]:
            return False, len(addresses)
    return True, len(addresses)



def _ft4_provably_outside_drawenv(draw_env, ft4_xy):
    """Conservative necessary coverage test for pinned PC native FT4 raster.

    DDA triangle spans cannot leave the vertex X/Y extrema by more than
    a few integer rounding steps. An eight-pixel guard on every side
    intentionally errs towards *unknown*, avoiding false cull claims at
    scan-conversion boundaries. This is not a pixel-level rasterizer.
    Native geometry is GPU corner order and DRAWENV.ofs shifts vertices,
    never the clip itself. Return None if the legacy trace lacks DRAWENV.
    """
    if draw_env is None:
        return None
    if type(draw_env) is not list or len(draw_env) != 6:
        raise ValueError("invalid native FT4 DRAWENV clip snapshot")
    if type(ft4_xy) is not list or len(ft4_xy) != 8:
        raise ValueError("invalid native FT4 GPU vertex coordinates")
    clip_x, clip_y, width, height, ofs_x, ofs_y = draw_env
    if width == 0 or height == 0:
        return True
    xs = [ft4_xy[i] + ofs_x for i in range(0, 8, 2)]
    ys = [ft4_xy[i] + ofs_y for i in range(1, 8, 2)]
    slack = 8
    return (max(xs) + slack < clip_x or
            min(xs) - slack >= clip_x + width or
            max(ys) + slack < clip_y or
            min(ys) - slack >= clip_y + height)


def _ft4_draw_delta(before_vram, after_vram, source_event,
                    draw_env=None, ft4_xy=None):
    """Count FT4 VRAM changes and, when captured, enforce PC raster clip.

    Both the native DDA and fallback use the half-open absolute drawing area
    [clip.x,clip.x+clip.w) x [clip.y,clip.y+clip.h). The GPU draw offset
    shifts triangle vertices, NOT that clipping rectangle. This test checks
    changed bytes against *captured* DRAWENV rather than guessed FT4 bounds.
    Self-modifying texture/CLUT writes are legal if they lie in the clip.
    """
    if len(before_vram) != VRAM_BYTES or len(after_vram) != VRAM_BYTES:
        raise ValueError("native FT4 before/after VRAM size mismatch")
    pre_texture, pre_palette = referenced_words(source_event, before_vram)
    post_texture, post_palette = referenced_words(source_event, after_vram)
    material_words = pre_texture | post_texture | pre_palette | post_palette
    clip = None
    if draw_env is not None:
        if type(draw_env) is not list or len(draw_env) != 6:
            raise ValueError("invalid native FT4 DRAWENV clip snapshot")
        x, y, width, height, _, _ = draw_env
        clip = (x, y, x + width, y + height)
    geometry_excluded = _ft4_provably_outside_drawenv(draw_env, ft4_xy)
    changed = material_changed = 0
    for word in range(VRAM_BYTES // 2):
        off = word * 2
        if before_vram[off:off+2] == after_vram[off:off+2]:
            continue
        changed += 1
        material_changed += word in material_words
        if clip is not None:
            cx = word % 1024
            cy = word // 1024
            if not (clip[0] <= cx < clip[2] and clip[1] <= cy < clip[3]):
                raise ValueError(
                    "native FT4 changed VRAM outside captured DRAWENV drawing area")
    if changed and geometry_excluded:
        raise ValueError(
            "native FT4 changed VRAM despite geometry entirely outside captured DRAWENV")
    return changed, material_changed, clip is not None, geometry_excluded is True


def _ft4_palette_state(before_vram, native_event):
    """Return (all transparent, STP-capable, ABR mode) for a 4-bpp CLUT.

    PC raster's native pass uses SampleTexture and skips 0000h texels. Every
    possible 4-bpp index selects one of exactly sixteen BGR555 CLUT words.
    If all sixteen are literally zero, no sampled texel can write pixels,
    regardless of DDA interpolation, UV window, or sampled index. Black with
    bit15 set (0x8000) is NOT zero and must not trigger this proof.
    STP and ABR are evidence of *possible* blending, never proof that a
    zero-delta primitive was blended away.
    """
    page = native_event["ft4"]["tpage"]
    mode = (page >> 7) & 3
    abr = (page >> 5) & 3
    if mode != 0:  # source-keyed MAP02 currently audits 4-bpp only
        return False, False, abr
    clut = native_event["ft4"]["clut"]
    row = (clut >> 6) & 511
    x = (clut & 63) * 16
    base = (row * 1024 + x) * 2
    colors = [
        before_vram[base + i*2] | (before_vram[base + i*2 + 1] << 8)
        for i in range(16)
    ]
    all_transparent = all(c == 0 for c in colors)
    stp_possible = (native_event["semi"] == 1 and
                    any((c & 0x8000) != 0 for c in colors))
    return all_transparent, stp_possible, abr




def _ft4_audited_crop_classes(source_event, before_vram, native_event):
    """Return (transparent, STP, opaque) counts in the audited 4-bpp UV crop.

    Each UV of the source-backed 16x16 crop is decoded using the exact PC
    texture-window and 4-bit nibble/CLUT addressing formulas. This set is
    NOT the set of texels sampled by DDA; coverage, roundoff, and repeated
    sampling are not proven here. Its STP entries are candidates only.
    """
    packet = native_event["ft4"]
    if (packet["tpage"] >> 7) & 3:
        return None
    texture = source_event["texture"]
    window = native_event["window"]
    mask_x, mask_y, offset_x, offset_y = window
    mask_x *= 8
    mask_y *= 8
    offset_x = (offset_x & window[0]) * 8
    offset_y = (offset_y & window[1]) * 8
    tpage = packet["tpage"]
    page_x = (tpage & 15) * 64
    page_y = ((tpage >> 4) & 1) * 256
    clut = packet["clut"]
    palette_offset = (((clut >> 6) & 511) * 1024 +
                      (clut & 63) * 16) * 2
    classes = [0, 0, 0]
    for v in range(texture["v"], texture["v"] + texture["h"] + 1):
        vy = (v & ~mask_y) | offset_y
        for u in range(texture["u"], texture["u"] + texture["w"] + 1):
            ux = (u & ~mask_x) | offset_x
            word_offset = ((page_y + vy) * 1024 +
                           page_x + ux // 4) * 2
            word = (before_vram[word_offset] |
                    (before_vram[word_offset + 1] << 8))
            index = (word >> ((ux & 3) * 4)) & 15
            palette_byte = palette_offset + index * 2
            bgr555 = (before_vram[palette_byte] |
                      (before_vram[palette_byte + 1] << 8))
            classification = 0 if bgr555 == 0 else (1 if bgr555 & 0x8000 else 2)
            classes[classification] += 1
    return tuple(classes)



def _native_after_vram(native_dir, native_events, before):
    """Retrieve paired post-draw snapshot only after native capture verified."""
    next_step = before["step"] + 1
    if next_step >= len(native_events):
        raise ValueError("missing paired FT4 post-draw VRAM snapshot")
    after = native_events[next_step]
    if (after["phase"] != "after" or
            after["operation"] != "draw" or
            after["step"] != next_step):
        raise ValueError("invalid FT4 after-draw snapshot association")
    return private_file(native_dir, after["snapshot"], expected=VRAM_BYTES)



def _verified_native_draw_packets(native_events):
    """Return only FT4 draws with internally stable per-primitive GPU state."""
    gpu_draw_events = []
    for i in range(0, len(native_events), 2):
        before, after = native_events[i:i+2]
        if _native_signature(before) is None:
            continue
        # A DR_MODE primitive may change GPU state; an individual FT4 must
        # not change its texture/window registers between before and after.
        if (before["window"] != after["window"] or
                before["draw_mode"] != after["draw_mode"]):
            raise ValueError("native FT4 texture/draw state changed during primitive")
        gpu_draw_events.append(before)
    return gpu_draw_events


def _unique_ft4_matches(source_events, native_ft4):
    """Match exact packets without assuming order or inventing source keys."""
    if not native_ft4:
        raise ValueError("native capture has no FT4 draw packets")
    source_signatures = [_source_signature(e) for e in source_events]
    draw_signatures = [_native_signature(e) for e in native_ft4]
    selected = []
    for face_index, sig in enumerate(source_signatures):
        matches = [i for i, candidate in enumerate(draw_signatures)
                   if sig == candidate]
        if not matches:
            raise ValueError(
                f"source face event {face_index}: no exact GPU FT4 geometry/UV/page/CLUT/window match")
        if len(matches) != 1:
            raise ValueError(
                f"source face event {face_index}: ambiguous GPU FT4 packets ({len(matches)})")
        selected.append(matches[0])
    if len(set(selected)) != len(selected):
        raise ValueError("one GPU FT4 packet matches multiple source-keyed MAP02 faces")
    return selected


def verify_join(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    manifest_raw = safe_file_max(source_dir, "gpu-face-join.json", 64*1024)
    manifest = parse_json(manifest_raw, "gpu-face-join.json")
    fields(manifest, (
        "schema", "source_frame", "gpu_draw_frame",
        "bundle_manifest_sha256", "native_events_sha256",
    ), "source/native mapping")
    if manifest["schema"] != SCHEMA:
        raise ValueError("unsupported source/native join schema")
    source_frame = number(manifest["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(manifest["gpu_draw_frame"], "native GPU frame", 1, 2**32-1)
    bundle_raw = private_file(source_dir, "bundle.json", max_bytes=64*1024)
    log_raw = private_file(native_dir, NATIVE_LOG, max_bytes=128*1024)
    sha_check(bundle_raw, manifest["bundle_manifest_sha256"], "source manifest")
    sha_check(log_raw, manifest["native_events_sha256"], "native GPU event log")

    # Do not match unverified source geometry or a damaged GPU capture.
    source_report = verify_bundle(source_dir, compiler=compiler)
    native_report = verify_capture(native_dir, target_frame=gpu_frame)
    if source_report["frame"] != source_frame:
        raise ValueError("declared source frame differs from verified bundle")
    if native_report["frame"] != gpu_frame:
        raise ValueError("declared native frame differs from verified capture")
    if native_report["record_cap_reached"]:
        raise ValueError("native trace exhausted its 64-record cap; cannot make exhaustive join")
    if source_report["submitted_faces_checked"] > MAX_FACES:
        raise ValueError("too many source faces")
    source_events = [
        parse_json(line, f"source event {i}")
        for i, line in enumerate(
            private_file(source_dir, "gpu-events.jsonl", max_bytes=256*1024).splitlines())
    ]
    native_events = [
        parse_json(line, f"GPU event {i}")
        for i, line in enumerate(log_raw.splitlines())
    ]
    # Every before/after pair has already passed source-native validation.
    gpu_draw_events = _verified_native_draw_packets(native_events)
    selected = _unique_ft4_matches(source_events, gpu_draw_events)

    reference = private_file(source_dir, "gpu-vram-le.bin", expected=VRAM_BYTES)
    material_words_checked = 0
    matched_draw_changed = matched_material_changed = no_pixel_delta = clip_checked = 0
    proved_no_coverage = no_delta_unknown = all_zero_clut = 0
    stp_blend_possible_unknown = 0
    stp_candidate_abr = [0, 0, 0, 0]
    audited_crop = [0, 0, 0]
    for face_index, match_index in enumerate(selected):
        native = gpu_draw_events[match_index]
        snapshot = private_file(native_dir, native["snapshot"], expected=VRAM_BYTES)
        equal, word_count = _material_bytes_equal(
            reference, snapshot, source_events[face_index])
        if not equal:
            raise ValueError(
                f"source face event {face_index}: texture or CLUT words differ "
                "from native VRAM immediately before primitive")
        material_words_checked += word_count
        post = _native_after_vram(native_dir, native_events, native)
        n, m, checked, excluded = _ft4_draw_delta(
            snapshot, post, source_events[face_index], native.get("draw_env"),
            native["ft4"]["xy"])
        transparent, _, abr_mode = _ft4_palette_state(snapshot, native)
        crop = _ft4_audited_crop_classes(source_events[face_index], snapshot, native)
        if crop is not None:
            for cls in range(3):
                audited_crop[cls] += crop[cls]
        stp_possible = (native["semi"] == 1 and crop is not None and crop[1] > 0)
        if transparent and n:
            raise ValueError("native FT4 changed VRAM with entirely zero 4-bpp CLUT")
        clip_checked += checked
        proved_no_coverage += excluded
        all_zero_clut += transparent and not excluded
        no_delta_unknown += n == 0 and not excluded and not transparent
        stp_candidate = (n == 0 and not excluded and
                         not transparent and stp_possible)
        stp_blend_possible_unknown += stp_candidate
        if stp_candidate:
            stp_candidate_abr[abr_mode] += 1
        matched_draw_changed += n
        matched_material_changed += m
        no_pixel_delta += n == 0

    # The draw walk is not in source submission order; no attempt to sort
    # by source index, material, depth, position or replay guessed OT order.
    return {
        "join_manifest_sha256": sha(manifest_raw),
        "source_bundle_manifest_sha256": sha(bundle_raw),
        "native_gpu_event_log_sha256": sha(log_raw),
        "source_frame": source_frame,
        "native_gpu_frame": gpu_frame,
        "source_face_count": len(source_events),
        "native_gpu_ft4_packets": len(gpu_draw_events),
        "uniquely_matched_source_faces": len(selected),
        "material_vram_words_compared": material_words_checked,
        "matched_ft4_draw_changed_vram_words": matched_draw_changed,
        "matched_ft4_draw_changed_texture_or_clut_words": matched_material_changed,
        "matched_ft4_draws_without_vram_change": no_pixel_delta,
        "matched_ft4_draws_with_drawenv_clip_checked": clip_checked,
        "matched_ft4_draws_proven_no_coverage": proved_no_coverage,
        "matched_ft4_draws_zero_delta_cause_unknown": no_delta_unknown,
        "matched_ft4_draws_zero_delta_full_4bpp_clut_transparent": all_zero_clut,
        "matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible":
            stp_blend_possible_unknown,
        "matched_ft4_zero_delta_stp_candidate_abr0": stp_candidate_abr[0],
        "matched_ft4_zero_delta_stp_candidate_abr1": stp_candidate_abr[1],
        "matched_ft4_zero_delta_stp_candidate_abr2": stp_candidate_abr[2],
        "matched_ft4_zero_delta_stp_candidate_abr3": stp_candidate_abr[3],
        "matched_ft4_audited_crop_transparent_texels": audited_crop[0],
        "matched_ft4_audited_crop_stp_texels": audited_crop[1],
        "matched_ft4_audited_crop_opaque_texels": audited_crop[2],
        "native_dda_texel_sampling_path_observed": False,
        "native_ft4_pixels_bit_exact_to_ps1": False,
        "screen_corners_uv_page_clut_window_exact": True,
        "source_gte_verified_by_compiled_reference": True,
        "native_before_after_capture_verified": True,
        "source_to_gpu_frame_binding_authenticated": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_raster_pixels_verified": False,
        "raw_game_data_emitted": False,
    }



TIMELINE_JOIN_SCHEMA = "vh.map02.source-native-ft4-timeline-join.v1"


def verify_timeline_join(source_dir, native_dir, *, compiler="gcc"):
    """Bind independently audited multi-VRAM source submissions to native FT4.

    The source/GTE submission frame and native DrawOTag frame are DIFFERENT
    clocks. Require an explicit user-authored SHA-bound mapping; do not infer
    frame equality, OT execution order, or GPU rasterization identity.
    Each source face's own snapshot (not a frame-wide VRAM image) is compared
    to the native GPU's pre-draw texture/CLUT words.
    """
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    raw_manifest = safe_file_max(source_dir, "gpu-face-timeline-join.json", 64*1024)
    mapping = parse_json(raw_manifest, "gpu-face-timeline-join.json")
    fields(mapping, ("schema", "source_frame", "gpu_draw_frame",
                     "timeline_manifest_sha256", "native_events_sha256"),
           "source/native timeline mapping")
    if mapping["schema"] != TIMELINE_JOIN_SCHEMA:
        raise ValueError("unsupported source/native timeline join schema")
    source_frame = number(mapping["source_frame"], "source frame", 1, 2**32-1)
    native_frame = number(mapping["gpu_draw_frame"], "GPU draw frame", 1, 2**32-1)
    timeline_raw = private_file(source_dir, "timeline.json", max_bytes=64*1024)
    native_raw = private_file(native_dir, NATIVE_LOG, max_bytes=128*1024)
    sha_check(timeline_raw, mapping["timeline_manifest_sha256"], "timeline manifest")
    sha_check(native_raw, mapping["native_events_sha256"], "native GPU log")

    timeline_report = verify_timeline(source_dir, compiler=compiler)
    native_report = verify_capture(native_dir, target_frame=native_frame)
    if timeline_report["frame"] != source_frame:
        raise ValueError("mapped source frame differs from verified timeline")
    if native_report["frame"] != native_frame:
        raise ValueError("mapped native frame differs from verified capture")
    if native_report["record_cap_reached"]:
        raise ValueError("native capture exhausted 64-record limit; incomplete")

    source_events = read_events(private_file(
        source_dir, "gpu-events.jsonl", max_bytes=EVENT_LIMIT))
    native_events = [parse_json(line, f"GPU event {i}")
                     for i, line in enumerate(native_raw.splitlines())]
    native_ft4 = _verified_native_draw_packets(native_events)
    selected = _unique_ft4_matches(source_events, native_ft4)

    compared = 0
    matched_draw_changed = matched_material_changed = no_pixel_delta = clip_checked = 0
    proved_no_coverage = no_delta_unknown = all_zero_clut = 0
    stp_blend_possible_unknown = 0
    stp_candidate_abr = [0, 0, 0, 0]
    audited_crop = [0, 0, 0]
    for source_index, native_index in enumerate(selected):
        reference = private_file(
            source_dir, f"gpu-vram-{source_index:03d}.bin", expected=VRAM_BYTES)
        before = private_file(
            native_dir, native_ft4[native_index]["snapshot"],
            expected=VRAM_BYTES)
        matched, count = _material_bytes_equal(
            reference, before, source_events[source_index])
        if not matched:
            raise ValueError(
                f"source submission {source_index}: texture or CLUT words differ "
                "from native VRAM immediately before primitive")
        compared += count
        post = _native_after_vram(native_dir, native_events, native_ft4[native_index])
        n, m, checked, excluded = _ft4_draw_delta(
            before, post, source_events[source_index],
            native_ft4[native_index].get("draw_env"),
            native_ft4[native_index]["ft4"]["xy"])
        transparent, _, abr_mode = _ft4_palette_state(
            before, native_ft4[native_index])
        crop = _ft4_audited_crop_classes(
            source_events[source_index], before, native_ft4[native_index])
        if crop is not None:
            for cls in range(3):
                audited_crop[cls] += crop[cls]
        stp_possible = (native_ft4[native_index]["semi"] == 1 and
                        crop is not None and crop[1] > 0)
        if transparent and n:
            raise ValueError("native FT4 changed VRAM with entirely zero 4-bpp CLUT")
        clip_checked += checked
        proved_no_coverage += excluded
        all_zero_clut += transparent and not excluded
        no_delta_unknown += n == 0 and not excluded and not transparent
        stp_candidate = (n == 0 and not excluded and
                         not transparent and stp_possible)
        stp_blend_possible_unknown += stp_candidate
        if stp_candidate:
            stp_candidate_abr[abr_mode] += 1
        matched_draw_changed += n
        matched_material_changed += m
        no_pixel_delta += n == 0

    return {
        "timeline_join_manifest_sha256": sha(raw_manifest),
        "source_timeline_manifest_sha256": sha(timeline_raw),
        "native_gpu_event_log_sha256": sha(native_raw),
        "source_frame": source_frame,
        "native_gpu_frame": native_frame,
        "source_submissions_verified": len(source_events),
        "native_ft4_packets": len(native_ft4),
        "uniquely_matched_source_faces": len(selected),
        "per_submission_vram_snapshots_compared": len(selected),
        "material_vram_words_compared": compared,
        "matched_ft4_draw_changed_vram_words": matched_draw_changed,
        "matched_ft4_draw_changed_texture_or_clut_words": matched_material_changed,
        "matched_ft4_draws_without_vram_change": no_pixel_delta,
        "matched_ft4_draws_with_drawenv_clip_checked": clip_checked,
        "matched_ft4_draws_proven_no_coverage": proved_no_coverage,
        "matched_ft4_draws_zero_delta_cause_unknown": no_delta_unknown,
        "matched_ft4_draws_zero_delta_full_4bpp_clut_transparent": all_zero_clut,
        "matched_ft4_draws_zero_delta_unknown_with_stp_blend_possible":
            stp_blend_possible_unknown,
        "matched_ft4_zero_delta_stp_candidate_abr0": stp_candidate_abr[0],
        "matched_ft4_zero_delta_stp_candidate_abr1": stp_candidate_abr[1],
        "matched_ft4_zero_delta_stp_candidate_abr2": stp_candidate_abr[2],
        "matched_ft4_zero_delta_stp_candidate_abr3": stp_candidate_abr[3],
        "matched_ft4_audited_crop_transparent_texels": audited_crop[0],
        "matched_ft4_audited_crop_stp_texels": audited_crop[1],
        "matched_ft4_audited_crop_opaque_texels": audited_crop[2],
        "native_dda_texel_sampling_path_observed": False,
        "native_ft4_pixels_bit_exact_to_ps1": False,
        "screen_corners_uv_page_clut_window_exact": True,
        "pc_gte_source_timeline_verified": True,
        "native_gpu_capture_verified": True,
        "source_gpu_frames_assumed_same": False,
        "draw_execution_order_assumed": False,
        "native_stream_authenticated_complete": False,
        "source_to_gpu_frame_binding_authenticated": False,
        "retail_gameplay_authenticated": False,
        "ps1_hardware_raster_pixels_verified": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_gpu_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    p.add_argument("--timeline", action="store_true",
                   help="use per-submission VRAM timeline and SHA-bound "
                        "gpu-face-timeline-join.json instead of a single frame bundle")
    args = p.parse_args()
    try:
        if args.timeline:
            report = verify_timeline_join(
                args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
        else:
            report = verify_join(
                args.source_bundle, args.native_gpu_capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
