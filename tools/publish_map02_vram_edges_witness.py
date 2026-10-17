#!/usr/bin/env python3
"""Publish direct DrawOTag VRAM edges ONLY with verified PutPixel/BlendG1 evidence.

The original-PC source-keyed verifier must have already succeeded for the
BlendG1 witness. This tool never derives an edge from a PutPixel record and
never produces a manifest from unverified pending capture alone.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from tools.publish_map02_blendg1_witness import (
    _private_directory, _prepare_private_file,
)
from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_frame_bundle import fields, parse_json, sha_check
from tools.verify_map02_blendg1_witness import (
    MANIFEST as BLEND_MANIFEST, LOG as BLEND_LOG, verify_blendg1_witness,
)
from tools.verify_map02_putpixel_scope import PIXEL_LOG
from tools.map02_vram_edge_witness import (
    MAX_EDGE_BYTES, parse_and_compare_edges,
)

SCHEMA = "vh.map02.native-vram-edge-witness.v1"
PENDING = "vram-edges-native-events.pending.jsonl"
EDGE_LOG = "vram-edges-native-events.jsonl"
MANIFEST = "gpu-vram-edges-witness.json"


def publish_vram_edges(source_dir, native_dir, *, compiler="gcc"):
    source_dir = _private_directory(source_dir)
    native_dir = _private_directory(native_dir)
    witness_meta = private_file(source_dir, BLEND_MANIFEST, max_bytes=4096)
    m = parse_json(witness_meta, BLEND_MANIFEST)
    fields(m, ("schema", "pixel_ot_manifest_sha256",
               "putpixel_events_sha256", "blendg1_events_sha256"),
           BLEND_MANIFEST)
    pixel = private_file(native_dir, PIXEL_LOG, max_bytes=16 * 1024)
    blend = private_file(native_dir, BLEND_LOG, max_bytes=16 * 1024)
    staged = private_file(native_dir, PENDING, max_bytes=MAX_EDGE_BYTES)
    sha_check(pixel, m["putpixel_events_sha256"], "verified PutPixel")
    sha_check(blend, m["blendg1_events_sha256"], "verified BlendG1")
    report = parse_and_compare_edges(pixel, staged)

    # Required and non-bypassable: includes original source-keyed DrawOTag/VRAM
    # and independently observed BlendG1 validation.
    upstream = verify_blendg1_witness(source_dir, native_dir, compiler=compiler)
    if upstream["observed_blendg1_putpixel_pairs"] < 1:
        raise ValueError("no verified BlendG1 evidence")
    if upstream["upstream_putpixel_calls"] != report["matched_native_putpixel_events"]:
        raise ValueError("source-keyed PutPixel verification disagrees with VRAM edges")

    for root, name, expected, limit in (
        (source_dir, BLEND_MANIFEST, witness_meta, 4096),
        (native_dir, PIXEL_LOG, pixel, 16 * 1024),
        (native_dir, BLEND_LOG, blend, 16 * 1024),
        (native_dir, PENDING, staged, MAX_EDGE_BYTES),
    ):
        if private_file(root, name, max_bytes=limit) != expected:
            raise ValueError("VRAM witness input changed during verification")

    final = native_dir / EDGE_LOG
    marker = source_dir / MANIFEST
    if any(p.exists() or p.is_symlink() for p in (final, marker)):
        raise ValueError("refuse overwriting completed VRAM edge witness")

    manifest = {
        "schema": SCHEMA,
        "blendg1_manifest_sha256": hashlib.sha256(witness_meta).hexdigest(),
        "putpixel_events_sha256": hashlib.sha256(pixel).hexdigest(),
        "blendg1_events_sha256": hashlib.sha256(blend).hexdigest(),
        "vram_edges_sha256": hashlib.sha256(staged).hexdigest(),
        "independently_sampled_draw_edges": report["independently_sampled_draw_edges"],
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True,
                               separators=(",", ":")) + "\n").encode("utf-8")
    temp_final = temp_marker = None
    linked_final = linked_marker = False
    try:
        temp_final = _prepare_private_file(final, staged)
        temp_marker = _prepare_private_file(marker, manifest_raw)
        os.link(temp_final, final)
        linked_final = True
        if final.read_bytes() != staged:
            raise ValueError("VRAM edges readback failure")
        os.link(temp_marker, marker)  # the ONLY completion marker, LAST
        linked_marker = True
        if marker.read_bytes() != manifest_raw:
            raise ValueError("VRAM edge manifest readback failure")
    except BaseException:
        if linked_marker:
            marker.unlink(missing_ok=True)
        if linked_final:
            final.unlink(missing_ok=True)
        raise
    finally:
        if temp_final is not None:
            temp_final.unlink(missing_ok=True)
        if temp_marker is not None:
            temp_marker.unlink(missing_ok=True)
    return {
        **report,
        "vram_edges_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    try:
        result = publish_vram_edges(a.source_bundle, a.native_capture,
                                    compiler=a.compiler)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
