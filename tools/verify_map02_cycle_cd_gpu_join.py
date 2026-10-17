#!/usr/bin/env python3
"""Independently join a real in-process CD->DrawOTag ordering receipt to the
already published MAP02 CD/GPU/GTE/kernel-process SHA witness.

This is a local *verification*, not a publisher and not proof of a rendered
original MAP02 scene. The full original witness is reverified on every run;
no shortcut via matching JSON identifiers is accepted. No original disc,
executable, texture or VRAM bytes are printed, copied or uploaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.publish_map02_cd_bound_witness import (
    MANIFEST as CD_GPU_MANIFEST,
    verify_published_original_cd_witness,
)
from tools.verify_map02_frame_bundle import fields, number, parse_json
from tools.verify_map02_native_gpu_capture import private_file

CYCLE_RECEIPT = "map02-single-process-cycle.jsonl"
CYCLE_SCHEMA = "vh.map02.cycle-order.v1"
SCHEMA = "vh.map02.same-process-cycle-cd-gpu-join.v1"
CYCLE_KEYS = (
    "schema", "capture_session", "gpu_draw_frame",
    "ordered_source_hooks_observed", "cd_payload_verified_by_this_receipt",
    "original_map02_rendering_proven", "physical_ps1_equivalence_proven",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _cycle_receipt(directory, frame):
    root = _private_directory(directory)
    if {entry.name for entry in root.iterdir()} != {CYCLE_RECEIPT}:
        raise ValueError("cycle directory must contain exactly one receipt")
    path = root / CYCLE_RECEIPT
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("cycle receipt must be a private 0600 regular file")
    raw = private_file(root, CYCLE_RECEIPT, max_bytes=2048)
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw:
        raise ValueError("noncanonical cycle receipt JSONL")
    event = parse_json(raw[:-1], CYCLE_RECEIPT)
    fields(event, CYCLE_KEYS, CYCLE_RECEIPT)
    if (event["schema"] != CYCLE_SCHEMA or
            event["ordered_source_hooks_observed"] is not True or
            event["cd_payload_verified_by_this_receipt"] is not False or
            event["original_map02_rendering_proven"] is not False or
            event["physical_ps1_equivalence_proven"] is not False):
        raise ValueError("unsupported or overstated single-process cycle receipt")
    if number(event["gpu_draw_frame"], "cycle DrawOTag frame",
              1, 2**32-1) != frame:
        raise ValueError("single-process cycle and GPU frame mismatch")
    token = event["capture_session"]
    if (type(token) is not str or len(token) != 32 or
            any(c not in "0123456789abcdef" for c in token)):
        raise ValueError("invalid single-process cycle nonce")
    return raw, _sha(token.encode("ascii"))


def verify_cycle_cd_gpu_join(source, native, scoped, handoff, cycle, image,
                             upstream, pc_binary, *, frame, compiler="gcc"):
    frame = number(frame, "selected DrawOTag frame", 1, 2**32-1)
    roots = [_private_directory(p) for p in
             (source, native, scoped, handoff, cycle)]
    if len({p.resolve() for p in roots}) != 5:
        raise ValueError("source, GPU, scoped, process and cycle directories must differ")
    source, native, scoped, handoff, cycle = roots
    cycle_raw, cycle_session_sha256 = _cycle_receipt(cycle, frame)
    before = private_file(source, CD_GPU_MANIFEST, max_bytes=4096)
    original = parse_json(before, CD_GPU_MANIFEST)
    if (type(original) is not dict or
            original.get("gpu_draw_frame") != frame or
            original.get("capture_session_sha256") != cycle_session_sha256):
        raise ValueError("original CD/GPU manifest and ordered cycle are not one session")

    # This is intentionally the expensive FULL original source/CD/GPU/process
    # audit, not a mocked assertion or a trust-only schema comparison.
    verified = verify_published_original_cd_witness(
        source, native, scoped, handoff, image, upstream, pc_binary,
        frame=frame, compiler=compiler)
    if verified["private_map02_cd_final_sha256"] != _sha(before):
        raise ValueError("original CD/GPU manifest SHA differs after re-verification")
    if (private_file(source, CD_GPU_MANIFEST, max_bytes=4096) != before or
            _cycle_receipt(cycle, frame) !=
            (cycle_raw, cycle_session_sha256)):
        raise ValueError("cycle or original CD/GPU evidence changed during verification")

    # Return hashes only; the nonce and all original game material remain private.
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "source_cd_gpu_process_witness_sha256": _sha(before),
        "single_process_cycle_receipt_sha256": _sha(cycle_raw),
        "capture_session_sha256": cycle_session_sha256,
        "same_process_event_order_and_prior_cd_gpu_witness_join_verified": True,
        "full_original_gameplay_authenticated": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_source_bundle", type=Path)
    parser.add_argument("private_gpu_windows", type=Path)
    parser.add_argument("private_scoped_capture", type=Path)
    parser.add_argument("private_local_handoff", type=Path)
    parser.add_argument("private_cycle_order", type=Path)
    parser.add_argument("private_owned_us_disc", type=Path)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--pc-binary", type=Path, required=True)
    parser.add_argument("--frame", type=int, required=True)
    parser.add_argument("--compiler", default="gcc")
    args = parser.parse_args()
    try:
        result = verify_cycle_cd_gpu_join(
            args.private_source_bundle, args.private_gpu_windows,
            args.private_scoped_capture, args.private_local_handoff,
            args.private_cycle_order, args.private_owned_us_disc,
            args.upstream_checkout, args.pc_binary,
            frame=args.frame, compiler=args.compiler)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
