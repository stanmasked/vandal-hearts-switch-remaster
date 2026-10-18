#!/usr/bin/env python3
"""Private MAP02 *structural* capture preflight before expensive source/GTE checks.

Read-only. Requires independently supplied source-keyed manifests and actual
native VRAM before/after snapshots. Does not generate a manifest, infer retail
gameplay provenance, or upload/print any pixels or game bytes.

This is NOT verify_map02_vram_edges_witness: final authentication still invokes
the full original PC source-keyed GTE/OT/VRAM and BlendG1 verification chain.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat

from tools.map02_blendg1_witness import compare_blendg1_witnesses
from tools.map02_vram_edge_witness import (
    MAX_EDGE_BYTES, parse_vram_edges, compare_vram_edges,
)
from tools.publish_map02_blendg1_witness import _private_directory
from tools.verify_map02_blendg1_witness import complete_events
from tools.verify_map02_frame_bundle import (
    MAP_BYTES, PINNED_PC_SOURCE, VRAM_BYTES,
    fields, number, parse_json, sha_check,
)
from tools.verify_map02_native_gpu_capture import (
    LOG as NATIVE_LOG, MAX_RECORDS, private_file, validate_meta,
    verify_capture_receipt,
)
from tools.verify_map02_putpixel_scope import FIELDS, SCHEMA as PIXEL_SCHEMA

STAGED_PIXEL = "putpixel-native-events.pending.jsonl"
STAGED_BLEND = "blendg1-native-events.pending.jsonl"
STAGED_EDGES = "vram-edges-native-events.pending.jsonl"


def _snapshot_word(directory, filename, x, y):
    """Read one native VRAM sample without accepting an inode substitution.

    This checks only a two-byte sample, NOT the provenance of a whole frame.
    O_NONBLOCK ensures a FIFO substituted at open cannot hang the preflight.
    """
    # Treat the event-supplied name as untrusted, including at direct
    # call sites: never allow a slash, dot segment or another file type.
    if (type(filename) is not str or
            re.fullmatch(r"gpu-[0-9]{4}-vram\\.bin", filename) is None):
        raise ValueError("invalid native VRAM snapshot filename")
    if (type(x) is not int or type(y) is not int or
            not 0 <= x < 1024 or not 0 <= y < 512):
        raise ValueError("invalid native VRAM sample coordinates")
    path = directory / filename
    flags = (os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) |
             getattr(os, "O_NOFOLLOW", 0) |
             getattr(os, "O_NONBLOCK", 0))
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ValueError("native VRAM snapshot unavailable or linked") from None
    try:
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                    info.st_nlink, info.st_size, info.st_mtime_ns,
                    info.st_ctime_ns)

        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
                info.st_uid != os.geteuid() or info.st_nlink != 1 or
                info.st_size != VRAM_BYTES):
            raise ValueError("native VRAM snapshot has wrong type or size")
        address = (y * 1024 + x) * 2
        first = os.pread(fd, 2, address)
        second = os.pread(fd, 2, address)
        if len(first) != 2 or len(second) != 2:
            raise ValueError("truncated native VRAM pixel")
        if (first != second or identity(os.fstat(fd)) != identity(info) or
                identity(os.stat(path, follow_symlinks=False)) != identity(info)):
            raise ValueError("native VRAM snapshot changed during sample")
        return int.from_bytes(first, "little")
    except OSError:
        raise ValueError("native VRAM snapshot sample unavailable") from None
    finally:
        os.close(fd)


def _jsonl(raw, label, *, max_rows=64):
    if not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError(label + ": incomplete or noncanonical JSONL")
    lines = raw.split(b"\n")[:-1]
    if not 1 <= len(lines) <= max_rows or any(not x for x in lines):
        raise ValueError(label + ": absent or over row limit")
    result = [parse_json(x, label) for x in lines]
    if any(type(x) is not dict for x in result):
        raise ValueError(label + ": event is not a JSON object")
    return result


def inspect_staged_capture(source_dir, native_dir):
    """Preflight only, never promote/modify files or authenticate retail MAP02."""
    source = _private_directory(source_dir)
    native = _private_directory(native_dir)

    bundle_raw = private_file(source, "bundle.json", max_bytes=64 * 1024)
    bundle = parse_json(bundle_raw, "bundle.json")
    fields(bundle, ("schema", "frame", "vram_snapshot_frame", "ot_size",
                    "pc_source_commit", "decoded_map_sha256", "vram_sha256",
                    "events_sha256"), "source bundle",
           optional=("pc_game_binary_sha256",))
    if bundle["schema"] != "vh.map02.frame.v1" or (
            bundle["pc_source_commit"] != PINNED_PC_SOURCE):
        raise ValueError("unrecognized original-PC source bundle/revision")
    source_frame = number(bundle["frame"], "original MAP02 source frame",
                          1, 2**32 - 1)
    if number(bundle["vram_snapshot_frame"], "source VRAM frame",
              1, 2**32 - 1) != source_frame:
        raise ValueError("source VRAM and MAP02 frame labels differ")
    number(bundle["ot_size"], "source OT size", 5, 4096)
    sha_check(private_file(source, "map02.decoded.bin", expected=MAP_BYTES),
              bundle["decoded_map_sha256"], "source MAP02 decoded map")
    sha_check(private_file(source, "gpu-vram-le.bin", expected=VRAM_BYTES),
              bundle["vram_sha256"], "source VRAM snapshot")
    events_raw = private_file(source, "gpu-events.jsonl", max_bytes=256 * 1024)
    sha_check(events_raw, bundle["events_sha256"], "source GTE FT4 events")
    events = _jsonl(events_raw, "source FT4", max_rows=32)
    if any(e.get("stage") != "map02_ft4_submit" or
           e.get("frame") != source_frame for e in events):
        raise ValueError("unrelated original source FT4 event")
    if "pc_game_binary_sha256" in bundle:
        # Validate only syntax; caller-supplied fingerprint is not proof.
        digest = bundle["pc_game_binary_sha256"]
        if (type(digest) is not str or len(digest) != 64 or
                any(ch not in "0123456789abcdef" for ch in digest)):
            raise ValueError("invalid supplied original game fingerprint")

    pixel_manifest_raw = private_file(source, "gpu-putpixel-ot.json",
                                      max_bytes=64 * 1024)
    pixel_meta = parse_json(pixel_manifest_raw, "gpu-putpixel-ot.json")
    fields(pixel_meta, ("schema", "source_frame", "gpu_draw_frame",
                        "overdraw_manifest_sha256", "native_events_sha256",
                        "putpixel_events_sha256"), "PutPixel source manifest")
    if pixel_meta["schema"] != PIXEL_SCHEMA or number(
            pixel_meta["source_frame"], "PutPixel source frame",
            1, 2**32 - 1) != source_frame:
        raise ValueError("PutPixel source frame or schema mismatch")
    gpu_frame = number(pixel_meta["gpu_draw_frame"], "GPU DrawOTag frame",
                       1, 2**32 - 1)
    overdraw_raw = private_file(source, "gpu-native-overdraw.json",
                                max_bytes=64 * 1024)
    sha_check(overdraw_raw, pixel_meta["overdraw_manifest_sha256"],
              "overdraw evidence")
    overdraw = parse_json(overdraw_raw, "gpu-native-overdraw.json")
    fields(overdraw, ("schema", "source_frame", "gpu_draw_frame",
                      "ot_order_manifest_sha256", "native_events_sha256"),
           "overdraw source manifest")
    if (overdraw["schema"] != "vh.map02.native-overdraw.v1" or
            number(overdraw["source_frame"], "overdraw source frame",
                   1, 2**32 - 1) != source_frame or
            number(overdraw["gpu_draw_frame"], "overdraw GPU frame",
                   1, 2**32 - 1) != gpu_frame):
        raise ValueError("overdraw frame or schema differs")
    ot_raw = private_file(source, "gpu-ot-order-join.json",
                          max_bytes=64 * 1024)
    sha_check(ot_raw, overdraw["ot_order_manifest_sha256"],
              "original AddPrim/OT join")

    native_raw = private_file(native, NATIVE_LOG, max_bytes=128 * 1024)
    sha_check(native_raw, pixel_meta["native_events_sha256"],
              "native original-PC GPU log")
    sha_check(native_raw, overdraw["native_events_sha256"],
              "overdraw native event log")
    native_rows = _jsonl(native_raw, "native GPU", max_rows=MAX_RECORDS)
    if len(native_rows) % 2 or len(native_rows) == MAX_RECORDS:
        raise ValueError("native GPU events incomplete or at truncation cap")
    capture_receipt = verify_capture_receipt(
        native, target_frame=gpu_frame, events=native_rows)
    pairs = []
    for i in range(0, len(native_rows), 2):
        before, after = native_rows[i:i + 2]
        validate_meta(before, i, gpu_frame)
        validate_meta(after, i + 1, gpu_frame)
        for name in ("frame", "operation", "rect", "dest", "rgb",
                     "primitive_type", "semi", "ft4", "draw_env"):
            if before.get(name) != after.get(name):
                raise ValueError("native GPU before/after provenance changed")
        pairs.append((before, after))

    pixels_raw = private_file(native, STAGED_PIXEL, max_bytes=16 * 1024)
    blend_raw = private_file(native, STAGED_BLEND, max_bytes=16 * 1024)
    edge_raw = private_file(native, STAGED_EDGES, max_bytes=MAX_EDGE_BYTES)
    sha_check(pixels_raw, pixel_meta["putpixel_events_sha256"],
              "independently supplied PutPixel digest")
    pixels = complete_events(pixels_raw, "staged native PutPixel")
    blends = complete_events(blend_raw, "staged native BlendG1")
    edges = parse_vram_edges(edge_raw)
    for i, p in enumerate(pixels):
        fields(p, FIELDS, "staged PutPixel")
        if p["step"] != i or p["frame"] != gpu_frame:
            raise ValueError("scoped PutPixel step or frame mismatch")
    if edges[0]["frame"] != gpu_frame:
        raise ValueError("independent VRAM edges recorded a different frame")
    compare_blendg1_witnesses(pixels, blends)
    report = compare_vram_edges(pixels, edges)

    native_draws = [(a, b) for a, b in pairs if a["operation"] == "draw"]
    if not native_draws or len(native_draws) != len(edges):
        raise ValueError("independent DrawOTag edges differ from native draw-pair count")
    if len(events) > len(native_draws):
        raise ValueError("source-keyed FT4 submissions exceed captured native draws")
    x, y = edges[0]["x"], edges[0]["y"]
    # Every snapshot referenced by transfer AND draw pairs must exist, be
    # regular and be full-size. Read only the selected native word.
    for before, after in pairs:
        _snapshot_word(native, before["snapshot"], x, y)
        _snapshot_word(native, after["snapshot"], x, y)
        if before["operation"] == "load" and after["upload"]:
            rect = after["rect"]
            area = rect[2] * rect[3]
            if not 0 < area <= 16384:
                raise ValueError("invalid source VRAM upload extent")
            private_file(native, after["upload"], expected=area * 2)
    for ordinal, (pair, edge) in enumerate(zip(native_draws, edges)):
        before, after = pair
        if (before["primitive_type"] != edge["primitive_type"] or
                before["frame"] != edge["frame"] or
                edge["primitive_ordinal"] != ordinal):
            raise ValueError("direct edge differs from GPU draw-pair identity")
        if (_snapshot_word(native, before["snapshot"], x, y) != edge["before"] or
                _snapshot_word(native, after["snapshot"], x, y) != edge["after"]):
            raise ValueError("edge differs from independent full native VRAM snapshot")

    # Source files may still be synthetic despite perfect hashes.
    return {
        "structural_preflight_passed": True,
        "source_frame": source_frame,
        "gpu_draw_frame": gpu_frame,
        "source_ft4_submissions": len(events),
        "native_draw_pairs": len(native_draws),
        "native_capture_receipt_checked": capture_receipt["capture_receipt_supplied"],
        "native_hook_loss_not_detected": capture_receipt[
            "capture_window_closed_without_detected_loss"],
        "independently_sampled_draw_edges": len(edges),
        "verified_structure_putpixel_events": len(pixels),
        "verified_structure_blendg1_events": len(blends),
        "unchanged_sampled_pixel_draws": report[
            "unchanged_draws_without_selected_pixel_writes"],
        "source_binary_fingerprint_supplied": "pc_game_binary_sha256" in bundle,
        "whole_gpu_frame_capture_proven": False,
        "source_gte_ot_vram_fully_verified": False,
        "original_gameplay_authenticated": False,
        "ps1_hardware_equivalence_proven": False,
        "gameplay_bytes_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_bundle", type=Path)
    parser.add_argument("native_capture", type=Path)
    args = parser.parse_args()
    try:
        report = inspect_staged_capture(args.source_bundle, args.native_capture)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
