#!/usr/bin/env python3
"""Finish a PRIVATE MAP02 capture in the only safe order.

Requires a separately prepared and executed source-pinned PC process.
Never starts the game, reads its output over the network or uploads game
pixels. Optional --complete-missing creates only two explicitly named
owner-private local artifacts; any other missing evidence fails closed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.publish_map02_blendg1_witness import _private_directory
from tools.publish_map02_cd_bound_witness import (
    MANIFEST as CD_MANIFEST,
    publish_original_cd_witness,
    verify_published_original_cd_witness,
)
from tools.map02_verified_process_launch import (
    RECEIPT as PROCESS_RECEIPT, RGB24_SCHEMA, _validate_receipt,
)
from tools.verify_map02_cycle_cd_gpu_join import (
    _cycle_receipt, _private_evidence_snapshot,
)
from tools.verify_map02_pc_preoverlay_session import verify_preoverlay_session
from tools.export_map02_native_vram_preview import (
    PNG_NAME, export_native_vram_preview,
)
from tools.verify_map02_final_pc_frame_join import verify_final_pc_frame
from tools.verify_map02_frame_bundle import number

SCHEMA = "vh.map02.private-postcapture-finalization.v1"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def finalize_private_capture(source, native, scoped, handoff, cycle,
                             preview, rgb, owned_game, upstream, pc_binary,
                             *, frame, compiler="gcc", complete_missing=False):
    """Revalidate all evidence and return metadata only, never the raw PNG.

    A successful report is intentionally NOT a retail gameplay attestation.
    Missing original CD/GPU witness or PNG are created only when explicitly
    requested. No unexpected pre-existing output is overwritten/deleted.
    """
    frame = number(frame, "MAP02 final capture frame", 1, 2**32 - 1)
    if type(complete_missing) is not bool:
        raise ValueError("complete-missing must be an explicit boolean")
    roots = tuple(_private_directory(p) for p in (
        source, native, scoped, handoff, cycle, preview, rgb))
    resolved = tuple(p.resolve() for p in roots)
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(resolved) for b in resolved[i + 1:]):
        raise ValueError("private MAP02 capture directories overlap")
    source, native, scoped, handoff, cycle, preview, rgb = roots

    # Nothing may be published until the OS-observed v3 process receipt
    # and the captured native RGB24 have been independently cross-bound
    # to the SAME clean-exit CD->GPU cycle.
    process_raw = _private_evidence_snapshot(
        handoff, PROCESS_RECEIPT, max_bytes=4096)
    process = _validate_receipt(process_raw[0])
    cycle_receipt = _cycle_receipt(cycle, frame)
    if (process["schema"] != RGB24_SCHEMA or
            process["gpu_draw_frame"] != frame or
            process["capture_session_sha256"] != cycle_receipt[1] or
            process["pc_preoverlay_capture_session_bound"] is not True):
        raise ValueError("unbound MAP02 process, cycle or RGB24 session")
    pc_capture = verify_preoverlay_session(
        rgb, cycle, frame=frame,
        expected_session_sha256=cycle_receipt[1])
    if (pc_capture["pc_rgb24_image_sha256"] !=
            process["pc_preoverlay_image_sha256"] or
            pc_capture["pc_rgb24_receipt_sha256"] !=
            process["pc_preoverlay_receipt_sha256"]):
        raise ValueError("MAP02 process receipt does not bind current RGB24 capture")

    # Preflight both intended output locations BEFORE the first write.
    # Do not turn a partially populated folder into a seemingly complete run.
    cd_target = source / CD_MANIFEST
    png_target = preview / PNG_NAME
    cd_existing = cd_target.exists() or cd_target.is_symlink()
    png_entries = {p.name for p in preview.iterdir()}
    if (png_entries not in (set(), {PNG_NAME}) or
            (cd_existing and cd_target.is_symlink()) or
            (PNG_NAME in png_entries and png_target.is_symlink())):
        raise ValueError("unexpected or linked MAP02 finalization files")
    if not complete_missing and (not cd_existing or not png_entries):
        raise ValueError("MAP02 final artifacts missing; explicit completion required")
    # Re-read these private inputs after all expensive validators too.
    if (_private_evidence_snapshot(
            handoff, PROCESS_RECEIPT, max_bytes=4096) != process_raw or
            _cycle_receipt(cycle, frame) != cycle_receipt):
        raise ValueError("MAP02 process or sealed cycle changed before finalization")

    if cd_existing:
        cd_result = verify_published_original_cd_witness(
            source, native, scoped, handoff, owned_game, upstream,
            pc_binary, frame=frame, compiler=compiler)
    else:
        cd_result = publish_original_cd_witness(
            source, native, scoped, handoff, owned_game, upstream,
            pc_binary, frame=frame, compiler=compiler)
    # Even a just-created witness must independently reopen and verify.
    reread_cd = verify_published_original_cd_witness(
        source, native, scoped, handoff, owned_game, upstream,
        pc_binary, frame=frame, compiler=compiler)
    if reread_cd != cd_result:
        raise ValueError("MAP02 source CD/GPU witness changed after publication")

    if not png_entries:
        exported = export_native_vram_preview(
            native, preview, frame=frame, cycle_directory=cycle)
        if (exported["schema"] !=
                "vh.map02.cycle-bound-native-vram-preview.v1" or
                exported["capture_session_sha256"] != cycle_receipt[1] or
                exported["private_game_bytes_uploaded"] is not False):
            raise ValueError("native VRAM preview failed source-bound audit")

    result = verify_final_pc_frame(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, pc_binary, frame=frame, compiler=compiler)
    if (result["source_cd_gpu_process_witness_sha256"] !=
            reread_cd["private_map02_cd_final_sha256"] or
            result["observed_process_receipt_sha256"] !=
            _sha(process_raw[0]) or
            result["single_process_cycle_receipt_sha256"] !=
            _sha(cycle_receipt[0]) or
            result["capture_session_sha256"] != cycle_receipt[1] or
            result["pc_preoverlay_rgb24_sha256"] !=
            pc_capture["pc_rgb24_image_sha256"] or
            result["pc_preoverlay_capture_receipt_sha256"] !=
            pc_capture["pc_rgb24_receipt_sha256"] or
            result["independent_full_cd_gpu_process_witness_verified"] is not True or
            result["pc_preoverlay_rgb24_and_native_vram_png_match"] is not True or
            result["original_map02_rendering_proven"] is not False):
        raise ValueError("MAP02 finalized CD/GPU/process/RGB24 audit inconsistent")
    # Ensure preflight inputs were not swapped after the final join.
    if (_private_evidence_snapshot(
            handoff, PROCESS_RECEIPT, max_bytes=4096) != process_raw or
            _cycle_receipt(cycle, frame) != cycle_receipt or
            verify_preoverlay_session(
                rgb, cycle, frame=frame,
                expected_session_sha256=cycle_receipt[1]) != pc_capture):
        raise ValueError("MAP02 private evidence changed after final verification")
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "capture_session_sha256": cycle_receipt[1],
        "source_cd_gpu_process_witness_sha256":
            result["source_cd_gpu_process_witness_sha256"],
        "process_receipt_sha256": result["observed_process_receipt_sha256"],
        "native_vram_png_sha256": result["private_native_vram_png_sha256"],
        "private_pc_preoverlay_rgb24_sha256":
            result["pc_preoverlay_rgb24_sha256"],
        "verified_draw_primitives": result["matched_native_draw_primitives"],
        "private_cd_witness_created": not cd_existing,
        "private_native_vram_png_created": not png_entries,
        "independently_verified_cd_gpu_process_and_rgb24_png": True,
        "original_map02_rendering_proven": False,
        "presented_host_window_authenticated": False,
        "physical_ps1_equivalence_proven": False,
        "game_bytes_uploaded": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_source_bundle", type=Path)
    p.add_argument("private_native_gpu", type=Path)
    p.add_argument("private_scoped", type=Path)
    p.add_argument("private_process_handoff", type=Path)
    p.add_argument("private_cycle", type=Path)
    p.add_argument("private_png_preview", type=Path)
    p.add_argument("private_pc_preoverlay_rgb24", type=Path)
    p.add_argument("private_owned_game_image", type=Path)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    p.add_argument("--complete-missing", action="store_true",
                   help="explicitly publish missing private CD witness and PNG")
    args = p.parse_args()
    try:
        report = finalize_private_capture(
            args.private_source_bundle, args.private_native_gpu,
            args.private_scoped, args.private_process_handoff,
            args.private_cycle, args.private_png_preview,
            args.private_pc_preoverlay_rgb24,
            args.private_owned_game_image,
            args.upstream_checkout, args.pc_binary, frame=args.frame,
            compiler=args.compiler, complete_missing=args.complete_missing)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        p.error("private MAP02 postcapture finalization failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
