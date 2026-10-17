#!/usr/bin/env python3
"""Re-verify completed SHA-bound DrawOTag VRAM edge witness, fail closed."""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_frame_bundle import fields, number, parse_json, sha_check
from tools.verify_map02_blendg1_witness import (
    MANIFEST as BLEND_MANIFEST, LOG as BLEND_LOG, verify_blendg1_witness,
)
from tools.verify_map02_putpixel_scope import PIXEL_LOG
from tools.map02_vram_edge_witness import MAX_EDGE_BYTES, parse_and_compare_edges
from tools.publish_map02_vram_edges_witness import (
    MANIFEST, EDGE_LOG, SCHEMA,
)


def verify_vram_edges(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    raw_meta = private_file(source_dir, MANIFEST, max_bytes=4096)
    meta = parse_json(raw_meta, MANIFEST)
    fields(meta, ("schema", "blendg1_manifest_sha256",
                  "putpixel_events_sha256", "blendg1_events_sha256",
                  "vram_edges_sha256", "independently_sampled_draw_edges"),
           MANIFEST)
    if meta["schema"] != SCHEMA:
        raise ValueError("invalid native VRAM edge manifest schema")
    blend_meta = private_file(source_dir, BLEND_MANIFEST, max_bytes=4096)
    pixel = private_file(native_dir, PIXEL_LOG, max_bytes=16 * 1024)
    blend = private_file(native_dir, BLEND_LOG, max_bytes=16 * 1024)
    edges = private_file(native_dir, EDGE_LOG, max_bytes=MAX_EDGE_BYTES)
    for value, name, digest in (
        (blend_meta, "BlendG1 manifest", meta["blendg1_manifest_sha256"]),
        (pixel, "verified PutPixel", meta["putpixel_events_sha256"]),
        (blend, "verified BlendG1", meta["blendg1_events_sha256"]),
        (edges, "independent native VRAM edges", meta["vram_edges_sha256"]),
    ):
        sha_check(value, digest, name)
    report = parse_and_compare_edges(pixel, edges)
    if number(meta["independently_sampled_draw_edges"], "draw edge count",
              1, 8192) != report["independently_sampled_draw_edges"]:
        raise ValueError("native VRAM edge count mismatches manifest")
    checked = verify_blendg1_witness(source_dir, native_dir, compiler=compiler)
    if (checked["upstream_putpixel_calls"] != report["matched_native_putpixel_events"]
            or checked["verified_blendg1_log_sha256"] !=
            hashlib.sha256(blend).hexdigest()):
        raise ValueError("upstream DrawOTag/VRAM witness mismatch")
    for root, name, original, limit in (
        (source_dir, MANIFEST, raw_meta, 4096),
        (source_dir, BLEND_MANIFEST, blend_meta, 4096),
        (native_dir, PIXEL_LOG, pixel, 16 * 1024),
        (native_dir, BLEND_LOG, blend, 16 * 1024),
        (native_dir, EDGE_LOG, edges, MAX_EDGE_BYTES),
    ):
        if private_file(root, name, max_bytes=limit) != original:
            raise ValueError("VRAM edge witness changed during verification")
    return {
        **report,
        "vram_edges_manifest_sha256": hashlib.sha256(raw_meta).hexdigest(),
        "verified_original_pc_source_chain": True,
        "original_gameplay_authenticated": False,
        "ps1_hardware_equivalence_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    try:
        report = verify_vram_edges(a.source_bundle, a.native_capture,
                                   compiler=a.compiler)
    except (OSError, ValueError) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
