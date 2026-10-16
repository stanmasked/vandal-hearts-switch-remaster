#!/usr/bin/env python3
"""Verify optional, SHA-bound original-PC BlendG1 witnesses against PutPixel.

Only private, opt-in capture can provide the witness stream. The existing
PutPixel verifier re-checks source geometry, OT order and VRAM endpoints.
This verifier is intentionally separate so absent witness capture never
silently becomes an empty 'successful' hardware proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.verify_map02_native_gpu_capture import private_file
from tools.verify_map02_frame_bundle import fields, parse_json, sha_check
from tools.verify_map02_putpixel_scope import (
    PIXEL_LOG, verify_pixel_ot,
)
from tools.map02_blendg1_witness import compare_blendg1_witnesses

SCHEMA = "vh.map02.native-blendg1-witness.v1"
MANIFEST = "gpu-blendg1-witness.json"
LOG = "blendg1-native-events.jsonl"
MAX_EVENTS = 64



def complete_events(raw, label):
    """Reject truncated/noncanonical JSONL even when the hash is valid."""
    if not raw.endswith(b"\\n") or b"\\r" in raw:
        raise ValueError(label + ": incomplete or noncanonical line ending")
    lines = raw.split(b"\\n")[:-1]
    if not 1 <= len(lines) < MAX_EVENTS or any(not line.strip() for line in lines):
        raise ValueError(label + ": missing, empty, or over event limit")
    return [parse_json(line, label) for line in lines]


def verify_blendg1_witness(source_dir, native_dir, *, compiler="gcc"):
    source_dir = Path(source_dir).absolute()
    native_dir = Path(native_dir).absolute()
    raw_manifest = private_file(source_dir, MANIFEST, max_bytes=4096)
    m = parse_json(raw_manifest, MANIFEST)
    fields(m, ("schema", "pixel_ot_manifest_sha256",
               "putpixel_events_sha256", "blendg1_events_sha256"),
           "BlendG1 witness manifest")
    if m["schema"] != SCHEMA:
        raise ValueError("unsupported BlendG1 witness schema")
    pixel_meta = private_file(source_dir, "gpu-putpixel-ot.json",
                              max_bytes=64 * 1024)
    pixel_raw = private_file(native_dir, PIXEL_LOG, max_bytes=16 * 1024)
    blend_raw = private_file(native_dir, LOG, max_bytes=16 * 1024)
    sha_check(pixel_meta, m["pixel_ot_manifest_sha256"],
              "PutPixel OT manifest")
    sha_check(pixel_raw, m["putpixel_events_sha256"], "PutPixel witness log")
    sha_check(blend_raw, m["blendg1_events_sha256"], "BlendG1 witness log")

    # Must fully authenticate the upstream PC DrawOTag/VRAM evidence first.
    verified = verify_pixel_ot(source_dir, native_dir, compiler=compiler)
    pixels = complete_events(pixel_raw, "verified scoped PutPixel")
    witnesses = complete_events(blend_raw, "BlendG1 witness")
    report = compare_blendg1_witnesses(pixels, witnesses)
    return {
        **report,
        "blendg1_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "verified_putpixel_log_sha256": hashlib.sha256(pixel_raw).hexdigest(),
        "verified_blendg1_log_sha256": hashlib.sha256(blend_raw).hexdigest(),
        "upstream_putpixel_calls": verified["observed_native_putpixel_calls"],
        "original_gameplay_authenticated": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_bundle", type=Path)
    p.add_argument("native_capture", type=Path)
    p.add_argument("--compiler", default="gcc")
    a = p.parse_args()
    try:
        result = verify_blendg1_witness(a.source_bundle, a.native_capture,
                                        compiler=a.compiler)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
