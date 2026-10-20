#!/usr/bin/env python3
"""Aggregate independently verified native PC PutPixel probes at distinct VRAM words.

Each --capture pair is checked through the complete source->GTE->FT4->
DrawOTag->VRAM->PutPixel chain before contributing to public counters.
Separate one-coordinate captures MUST NOT be represented as a single
simultaneous raster observation or as authenticated retail gameplay.
No original MAP02 colors, coordinates, paths or source bytes are emitted.
"""
import argparse
import json
from pathlib import Path
import subprocess

from tools.verify_map02_frame_bundle import parse_json
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_putpixel_scope import PIXEL_LOG, verify_pixel_ot

MAX_SAMPLES = 8

AGGREGATE_FIELDS = (
    "observed_native_putpixel_calls",
    "source_keyed_ft4_draws_checked",
    "source_ft4_draws_with_scoped_calls",
    "source_ft4_draws_without_observable_word_change",
    "calls_attributed_to_source_keyed_ft4",
    "source_ft4_scoped_changed_putpixel_calls",
    "source_ft4_scoped_unchanged_putpixel_calls",
    "source_ft4_scoped_semitransparent_blend_calls",
    "source_ft4_scoped_accurate_semi_blend_calls",
    "source_ft4_scoped_legacy_semi_blend_calls",
    "source_ft4_scoped_draws_with_multiple_semi_blends",
    "source_ft4_scoped_transient_draws_invisible_to_vram_delta",
    "source_ft4_sampled_changed_word_draws",
    "source_ft4_scoped_semi_blend_abr0_calls",
    "source_ft4_scoped_semi_blend_abr1_calls",
    "source_ft4_scoped_semi_blend_abr2_calls",
    "source_ft4_scoped_semi_blend_abr3_calls",
)


def audit_samples(captures, *, compiler="gcc"):
    """Check multiple distinct private coordinates without releasing any.

    Matching frame numbers or hashes are not proof of common run origin.
    The same word cannot appear twice, even under different directory
    names, because summing its calls would double-count observations.
    """
    if not 2 <= len(captures) <= MAX_SAMPLES:
        raise ValueError("expected 2 to 8 independent PutPixel capture pairs")

    seen_coordinates = set()
    source_frame = native_frame = None
    native_hashes = set()
    totals = {name: 0 for name in AGGREGATE_FIELDS}
    for source_dir, native_dir in captures:
        report = verify_pixel_ot(
            Path(source_dir), Path(native_dir), compiler=compiler)
        frame_pair = (report["source_frame"], report["native_gpu_frame"])
        if source_frame is None:
            source_frame, native_frame = frame_pair
        elif frame_pair != (source_frame, native_frame):
            raise ValueError("independent PutPixel captures claim different frame labels")

        # verify_pixel_ot already verified SHA, row shape, bounds, constant
        # coordinate, ordinal order, native source and all VRAM snapshots.
        # Re-read the *private* first row only for deduplication; never
        # include even its hash or numerical position in the public result.
        raw = private_file(Path(native_dir).absolute(), PIXEL_LOG,
                           max_bytes=16 * 1024)
        first = parse_json(raw.splitlines()[0], "first scoped pixel sample")
        coordinate = (first["x"], first["y"])
        if coordinate in seen_coordinates:
            raise ValueError("duplicate sampled VRAM word across capture pairs")
        seen_coordinates.add(coordinate)
        native_hashes.add(report["native_gpu_event_log_sha256"])
        for name in AGGREGATE_FIELDS:
            totals[name] += report[name]

    if (totals["calls_attributed_to_source_keyed_ft4"] >
            totals["observed_native_putpixel_calls"] or
            totals["source_ft4_draws_with_scoped_calls"] >
            totals["source_keyed_ft4_draws_checked"] or
            totals["source_ft4_draws_without_observable_word_change"] >
            totals["source_keyed_ft4_draws_checked"]):
        raise ValueError("independent PutPixel source attribution accounting mismatch")

    if (totals["source_ft4_scoped_semitransparent_blend_calls"] !=
            totals["source_ft4_scoped_accurate_semi_blend_calls"] +
            totals["source_ft4_scoped_legacy_semi_blend_calls"] or
            totals["source_ft4_scoped_semitransparent_blend_calls"] !=
            sum(totals[f"source_ft4_scoped_semi_blend_abr{i}_calls"]
                for i in range(4))):
        raise ValueError("independent PutPixel blend count accounting mismatch")

    return {
        "source_frame": source_frame,
        "native_gpu_frame": native_frame,
        "independent_capture_pairs_verified": len(captures),
        "distinct_private_vram_words_sampled": len(seen_coordinates),
        "all_native_gpu_event_log_hashes_equal": len(native_hashes) == 1,
        **totals,
        "same_native_capture_session_authenticated": False,
        "simultaneous_multi_word_observation_proven": False,
        "complete_putpixel_write_stream_proven": False,
        "ft4_actual_pixel_coverage_verified": False,
        "original_map02_gameplay_authenticated": False,
        "ps1_hardware_pixel_equivalence_verified": False,
        "raw_pixel_coordinates_or_colors_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", nargs=2,
                        metavar=("SOURCE_DIR", "GPU_DIR"), required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        report = audit_samples(args.capture, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
