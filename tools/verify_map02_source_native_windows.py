#!/usr/bin/env python3
"""Source/GTE-verified MAP02 FT4 subset joined to separately bounded GPU windows.

The source and PC GPU frame counters are *different clocks*. An explicit
user-supplied, SHA-pinned claim states their relationship. An exact FT4
texture/geometry match and a correctly ordered original OT subsequence are
required, plus equality of all referenced source texture/CLUT words.
This is a local consistency witness, NOT retail provenance or PS1 fidelity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_frame_bundle import (
    fields, number, parse_json, safe_file_max, sha_check, verify_bundle,
    VRAM_BYTES,
)
from tools.verify_map02_native_gpu_capture import LOG, private_file
from tools.verify_map02_native_gpu_windows import (
    INDEX, verify_native_windows,
)
from tools.verify_map02_source_native_ft4_join import (
    _source_signature, _native_signature, _material_bytes_equal,
)
from tools.verify_map02_source_native_ot_order import (
    expected_addprim_draw_indices,
)

CLAIM = "gpu-native-window-source-claim.json"
CLAIM_SCHEMA = "vh.map02.native-window-source-claim.v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_window_source_join(source_dir, window_dir, *, compiler="gcc"):
    source = _private_directory(source_dir)
    native = _private_directory(window_dir)
    raw_claim = safe_file_max(source, CLAIM, 4096)
    claim = parse_json(raw_claim, CLAIM)
    fields(claim, (
        "schema", "source_frame", "gpu_draw_frame",
        "source_bundle_manifest_sha256", "source_events_sha256",
        "native_window_index_sha256", "source_events_in_addprim_order",
        "one_clear_otag_one_draw_otag",
    ), CLAIM)
    if claim["schema"] != CLAIM_SCHEMA:
        raise ValueError("unknown MAP02 window source-claim schema")
    if (claim["source_events_in_addprim_order"] is not True or
            claim["one_clear_otag_one_draw_otag"] is not True):
        raise ValueError("source AddPrim chronology and single OT pass must be claimed")
    source_frame = number(claim["source_frame"], "source frame", 1, 2**32-1)
    gpu_frame = number(claim["gpu_draw_frame"], "native GPU frame", 1, 2**32-1)
    bundle_raw = safe_file_max(source, "bundle.json", 64*1024)
    events_raw = safe_file_max(source, "gpu-events.jsonl", 256*1024)
    index_raw = private_file(native, INDEX, max_bytes=4096)
    sha_check(bundle_raw, claim["source_bundle_manifest_sha256"],
              "original MAP02 bundle")
    sha_check(events_raw, claim["source_events_sha256"],
              "original source GTE FT4 events")
    sha_check(index_raw, claim["native_window_index_sha256"],
              "same-run native GPU window receipt")

    # The expensive independently captured decoded MAP02, compiled PC GTE
    # and source texture VRAM verification is mandatory, never mocked here.
    checked_source = verify_bundle(source, compiler=compiler)
    if (checked_source["frame"] != source_frame or
            checked_source["submitted_faces_checked"] < 1):
        raise ValueError("verified MAP02 source frame/face count disagreement")
    checked_native = verify_native_windows(native, target_frame=gpu_frame)

    source_events = [
        parse_json(line, "source original FT4") for line in
        events_raw.splitlines()
    ]
    if len(source_events) != checked_source["submitted_faces_checked"]:
        raise ValueError("source FT4 line count changed during verification")
    source_manifest = parse_json(bundle_raw, "original source bundle")
    ot_size = number(source_manifest["ot_size"], "original OT size", 5, 4096)

    # Every window has been independently checked for snapshots, privacy,
    # event ordering, and exact full-VRAM continuity, including boundaries.
    native_ft4 = []
    native_draw_count = 0
    for idx in range(checked_native["recorded_windows"]):
        window = native / f"window-{idx:03d}"
        raw = private_file(window, LOG, max_bytes=128*1024)
        records = [parse_json(line, "windowed GPU draw")
                   for line in raw.splitlines()]
        for i in range(0, len(records), 2):
            before, after = records[i:i+2]
            if before["operation"] != "draw":
                continue
            native_draw_count += 1
            if _native_signature(before) is None:
                continue
            if (before["window"] != after["window"] or
                    before["draw_mode"] != after["draw_mode"] or
                    before["ft4"] != after["ft4"]):
                raise ValueError("GPU FT4 state changed inside one draw pair")
            native_ft4.append((before, window))

    # Unambiguous signatures are required; do not guess which repeated
    # polygon originated from a given submitted source face.
    candidates = [_native_signature(item[0]) for item in native_ft4]
    positions = []
    source_vram = private_file(source, "gpu-vram-le.bin", expected=VRAM_BYTES)
    material_words = 0
    for event in source_events:
        signature = _source_signature(event)
        hits = [i for i, sig in enumerate(candidates) if sig == signature]
        if len(hits) != 1:
            raise ValueError("source MAP02 FT4 absent or ambiguous in GPU windows")
        position = hits[0]
        gpu_before, window = native_ft4[position]
        vram = private_file(window, gpu_before["snapshot"], expected=VRAM_BYTES)
        same, count = _material_bytes_equal(source_vram, vram, event)
        if not same:
            raise ValueError("source texture/CLUT words differ from GPU draw VRAM")
        material_words += count
        positions.append(position)
    if len(set(positions)) != len(source_events):
        raise ValueError("source FT4 events alias one native GPU draw")
    expected = expected_addprim_draw_indices(source_events, ot_size)
    actual = sorted(range(len(source_events)), key=lambda i: positions[i])
    if actual != expected:
        raise ValueError("windowed native FT4 relative DrawOTag order mismatch")

    # Check the binding inputs again after CPU/GTE execution and VRAM reads.
    for root, name, original, limit in (
        (source, CLAIM, raw_claim, 4096),
        (source, "bundle.json", bundle_raw, 64*1024),
        (source, "gpu-events.jsonl", events_raw, 256*1024),
        (native, INDEX, index_raw, 4096),
    ):
        if private_file(root, name, max_bytes=limit) != original:
            raise ValueError("source/window binding inputs changed during verification")
    # Second complete audit also catches changed snapshot bytes.
    final_native = verify_native_windows(native, target_frame=gpu_frame)
    if final_native != checked_native:
        raise ValueError("GPU window evidence changed during source join")
    return {
        "source_claim_sha256": sha(raw_claim),
        "verified_source_bundle_sha256": sha(bundle_raw),
        "verified_source_events_sha256": sha(events_raw),
        "native_window_index_sha256": sha(index_raw),
        "native_window_all_files_sha256":
            checked_native["native_window_all_files_sha256"],
        "source_frame": source_frame,
        "gpu_draw_frame": gpu_frame,
        "source_ft4_exact_matches": len(source_events),
        "native_draw_pairs": native_draw_count,
        "native_gpu_events": checked_native["globally_ordered_native_gpu_events"],
        "native_windows": checked_native["recorded_windows"],
        "source_texture_palette_words_checked": material_words,
        "original_gte_compiled_and_checked": True,
        "source_ft4_relative_ot_order_checked": True,
        "source_addprim_chronology_authenticated": False,
        "full_original_scene_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_windows", type=Path)
    p.add_argument("--compiler", default="gcc")
    args = p.parse_args()
    try:
        report = verify_window_source_join(
            args.source_bundle, args.native_windows, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Source claims and private GPU inputs may contain owner paths.
        # Do not reproduce untrusted error text in public CI/terminal logs.
        p.error("private MAP02 source/native window join unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
