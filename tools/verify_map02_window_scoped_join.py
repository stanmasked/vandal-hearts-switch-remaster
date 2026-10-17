#!/usr/bin/env python3
"""Join SAME-RUN native GPU windows to selected-pixel DrawOTag witnesses.

Original GPU windows and separately staged PutPixel, BlendG1 and direct VRAM
edge rows must all come from one explicitly selected DrawOTag frame. The
global ordinal counts DRAW packets only, across window boundaries. This is
structural native PC evidence, NOT a whole-game-frame or PlayStation proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.map02_blendg1_witness import compare_blendg1_witnesses
from tools.map02_vram_edge_witness import (
    MAX_EDGE_BYTES, parse_and_compare_edges, parse_vram_edges,
)
from tools.verify_map02_blendg1_witness import complete_events
from tools.verify_map02_frame_bundle import number, parse_json
from tools.verify_map02_native_gpu_capture import LOG, private_file, VRAM_BYTES
from tools.verify_map02_native_gpu_windows import verify_native_windows
from tools.publish_map02_native_window_source_witness import (
    verify_published_window_source_witness,
)

PIXELS = "putpixel-native-events.pending.jsonl"
BLENDS = "blendg1-native-events.pending.jsonl"
EDGES = "vram-edges-native-events.pending.jsonl"


def verify_window_scoped_join(native_windows, scoped_capture, *,
                              target_frame, source_dir=None, compiler="gcc"):
    native = _private_directory(native_windows)
    scoped = _private_directory(scoped_capture)
    if native.resolve() == scoped.resolve():
        raise ValueError("native GPU window and scoped capture must be separate")
    frame = number(target_frame, "selected GPU frame", 1, 2**32 - 1)
    windows_report = verify_native_windows(native, target_frame=frame)
    pixels_raw = private_file(scoped, PIXELS, max_bytes=16 * 1024)
    blends_raw = private_file(scoped, BLENDS, max_bytes=16 * 1024)
    edges_raw = private_file(scoped, EDGES, max_bytes=MAX_EDGE_BYTES)
    if {p.name for p in scoped.iterdir()} != {PIXELS, BLENDS, EDGES}:
        raise ValueError("scoped witness contains unlisted/mixed-session files")
    pixels = complete_events(pixels_raw, "same-run PutPixel")
    blends = complete_events(blends_raw, "same-run BlendG1")
    edges = parse_vram_edges(edges_raw)
    edge_report = parse_and_compare_edges(pixels_raw, edges_raw)
    blend_report = compare_blendg1_witnesses(pixels, blends)
    if any(e["frame"] != frame for e in edges):
        raise ValueError("direct VRAM boundary recorded a different DrawOTag frame")

    coordinate = (edges[0]["x"], edges[0]["y"])
    address = (coordinate[1] * 1024 + coordinate[0]) * 2
    if len(edges) != windows_report["native_draw_pairs"]:
        raise ValueError("selected DrawOTag draw boundary count differs from GPU windows")
    ordinal = 0
    across_windows = 0
    draw_indices = []
    for window_index in range(windows_report["recorded_windows"]):
        directory = native / f"window-{window_index:03d}"
        log = private_file(directory, LOG, max_bytes=128 * 1024)
        rows = [parse_json(line, "windowed native GPU event")
                for line in log.splitlines()]
        for index in range(0, len(rows), 2):
            before, after = rows[index:index + 2]
            if before["operation"] != "draw":
                continue
            edge = edges[ordinal]
            if (edge["primitive_ordinal"] != ordinal or
                    edge["primitive_type"] != before["primitive_type"] or
                    edge["primitive_type"] != after["primitive_type"]):
                raise ValueError("global draw ordinal or primitive kind changed across GPU windows")
            prior = private_file(directory, before["snapshot"], expected=VRAM_BYTES)
            next_ = private_file(directory, after["snapshot"], expected=VRAM_BYTES)
            pre_word = int.from_bytes(prior[address:address + 2], "little")
            post_word = int.from_bytes(next_[address:address + 2], "little")
            if (pre_word != edge["before"] or post_word != edge["after"]):
                raise ValueError("native full VRAM snapshot disagrees with direct DrawOTag edge")
            global_event_step = window_index * 64 + index
            if global_event_step != 2 * len(draw_indices) and (
                    window_index != 0 or index != 0):
                # Transfers are legal; global event indices need not equal
                # 2 * draw ordinal, but the index must increase monotonically.
                pass
            if draw_indices and global_event_step <= draw_indices[-1]:
                raise ValueError("global native DrawOTag event index did not increase")
            if window_index and index == 0:
                across_windows += 1
            draw_indices.append(global_event_step)
            ordinal += 1
    if ordinal != len(edges):
        raise ValueError("native GPU windows omit DrawOTag edge ordinals")

    sourced = None
    if source_dir is not None:
        sourced = verify_published_window_source_witness(
            source_dir, native, compiler=compiler)
        if sourced["native_window_file_tree_bound"] is not True:
            raise ValueError("source/GTE window witness not bound to GPU capture")
    return {
        "gpu_frame": frame,
        "global_draw_ordinals_checked": ordinal,
        "global_event_indices_of_first_and_last_draw":
            [draw_indices[0], draw_indices[-1]],
        "draws_at_start_of_following_windows": across_windows,
        "independently_sampled_draw_edges": edge_report[
            "independently_sampled_draw_edges"],
        "unchanged_draws_at_selected_pixel": edge_report[
            "unchanged_draws_without_selected_pixel_writes"],
        "selected_pixel_putpixel_events": edge_report[
            "matched_native_putpixel_events"],
        "selected_pixel_blendg1_events":
            blend_report["observed_blendg1_putpixel_pairs"],
        "all_native_window_file_bytes_sha256":
            windows_report["native_window_all_files_sha256"],
        "putpixel_staged_sha256": hashlib.sha256(pixels_raw).hexdigest(),
        "blendg1_staged_sha256": hashlib.sha256(blends_raw).hexdigest(),
        "direct_vram_edges_staged_sha256":
            hashlib.sha256(edges_raw).hexdigest(),
        "source_gte_subsequence_verified": sourced is not None,
        "whole_original_gameplay_frame_proven": False,
        "physical_ps1_equivalence_proven": False,
        "private_game_bytes_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("native_windows", type=Path)
    p.add_argument("scoped_private_capture", type=Path)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--source-bundle", type=Path)
    p.add_argument("--compiler", default="gcc")
    args = p.parse_args()
    try:
        result = verify_window_scoped_join(
            args.native_windows, args.scoped_private_capture,
            target_frame=args.frame, source_dir=args.source_bundle,
            compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
