#!/usr/bin/env python3
"""Audit bounded original PC *executed* native PutPixel samples.

This log is from actual WritePixel invocations at one selected native VRAM
coordinate. Missing calls have NO defined cause, and a successful sample
does not bind it to a specific MAP02 face or DrawOTag frame. In particular,
a same-value write is OBSERVED but invisible in before/after VRAM diffs.
Only a raw log SHA and aggregate statistics are emitted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat

from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.map02_pc_writepixel_reference import expected_write_pixel

NAME = "putpixel-native-events.jsonl"
MAX_RECORDS = 64
MAX_BYTES = 16 * 1024
ATTRIBUTES = ("stage", "step", "x", "y", "before", "front", "after",
              "abr", "semi", "textured", "accurate")


def verify_pixel_calls(directory):
    directory = Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("private pixel directory missing or linked")
    path = directory / NAME
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("pixel sample log missing, linked or nonregular")
    size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise ValueError("pixel sample log empty or exceeds cap")
    raw = path.read_bytes()
    rows = raw.splitlines()
    if not 1 <= len(rows) <= MAX_RECORDS or any(not line.strip() for line in rows):
        raise ValueError("pixel sample record count invalid or incomplete")
    chosen = None
    opaque_calls = blend_calls = accurate_calls = same_color_calls = 0
    changed_calls = bit15_rises = bit15_falls = gaps = 0
    accurate_blend_checked = legacy_blend_checked = 0
    observed_accurate_mode = None
    prev_after = None
    for index, line in enumerate(rows):
        e = parse_json(line, f"pixel sample event {index}")
        fields(e, ATTRIBUTES, f"pixel sample event {index}")
        if e["stage"] != "native_putpixel":
            raise ValueError("not an original native PutPixel sample")
        if number(e["step"], "pixel sample step", 0, MAX_RECORDS-1) != index:
            raise ValueError("noncontiguous pixel sample sequence")
        x = number(e["x"], "sample x", 0, 1023)
        y = number(e["y"], "sample y", 0, 511)
        if chosen is None:
            chosen = (x, y)
        elif (x, y) != chosen:
            raise ValueError("mixed sampled pixel coordinates")
        before = number(e["before"], "pre-WritePixel BGR555", 0, 65535)
        front = number(e["front"], "input BGR555", 0, 65535)
        after = number(e["after"], "post-WritePixel BGR555", 0, 65535)
        number(e["abr"], "ABR", 0, 3)
        semi = number(e["semi"], "semi-transparency", 0, 1)
        number(e["textured"], "textured", 0, 1)
        accurate = number(e["accurate"], "PC accurate-mode flag", 0, 1)
        # The pinned PC AccurateEnabled() caches VH_ACCURATE in a static
        # local variable. It cannot change during one native capture.
        if observed_accurate_mode is None:
            observed_accurate_mode = accurate
        elif observed_accurate_mode != accurate:
            raise ValueError("inconsistent native AccurateEnabled mode in one PutPixel session")

        # The actual pinned original WritePixel always copies c directly
        # when semiTrans == 0. Reject the only outcome the source alone
        # lets us verify without reconstructing blend/dither decisions.
        if semi == 0:
            if front != after:
                raise ValueError("opaque native WritePixel result violates pinned PC source")
        else:
            expected = expected_write_pixel(before, front, e["abr"], semi,
                                            e["textured"], accurate)
            if after != expected:
                raise ValueError("semi-transparent native WritePixel differs from pinned PC blend")
            if accurate:
                accurate_blend_checked += 1
            else:
                legacy_blend_checked += 1
        if prev_after is not None and prev_after != before:
            # Other native GPU operations or uploads may modify this word
            # between calls. Do not invent their cause or silently say no gap.
            gaps += 1
        prev_after = after
        opaque_calls += (semi == 0)
        blend_calls += (semi != 0)
        accurate_calls += accurate
        same_color_calls += (before == after)
        changed_calls += (before != after)
        bit15_rises += (before & 0x8000 == 0 and after & 0x8000 != 0)
        bit15_falls += (before & 0x8000 != 0 and after & 0x8000 == 0)
    return {
        "private_putpixel_log_sha256": hashlib.sha256(raw).hexdigest(),
        "native_putpixel_calls_observed": len(rows),
        "opaque_copy_calls": opaque_calls,
        "semi_transparent_blend_requests": blend_calls,
        "accurate_pc_blend_results_checked": accurate_blend_checked,
        "legacy_pc_blend_results_checked": legacy_blend_checked,
        "original_pc_writepixel_effects_verified": True,
        "single_runtime_accurate_mode_consistent": True,
        "accurate_gpu_mode_calls": accurate_calls,
        "same_color_write_calls_invisible_to_vram_delta": same_color_calls,
        "changed_word_write_calls": changed_calls,
        "bit15_unset_to_set_calls": bit15_rises,
        "bit15_set_to_unset_calls": bit15_falls,
        "gaps_between_consecutive_sampled_calls": gaps,
        "original_opaque_copy_invariant_checked": True,
        "record_cap_reached": len(rows) == MAX_RECORDS,
        "no_unlogged_putpixel_calls_proven": False,
        "no_raster_or_transparency_skip_proven": False,
        "observations_matched_to_map02_faces": False,
        "blending_or_mask_hardware_accuracy_verified": False,
        "physical_ps1_raster_equivalence_verified": False,
        "real_gameplay_authenticated": False,
        "raw_pixel_values_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_capture_dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify_pixel_calls(args.private_capture_dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
