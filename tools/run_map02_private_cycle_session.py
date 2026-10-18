#!/usr/bin/env python3
"""Explicit one-shot PRIVATE MAP02 PC capture: launch -> finalize -> seal.

No owned disc, ELF, VRAM, PNG or original source is copied to a public
artifact. The caller supplies existing owner-private directories and an
independently prepared capture plan/full source-bound ELF and receipts.
This is a local orchestration gate, NOT game-content authentication.
"""
import argparse
import json
from pathlib import Path
import subprocess

from tools.check_map02_private_cycle_readiness import verify_private_cycle_readiness
from tools.finalize_map02_private_capture import finalize_private_capture
from tools.map02_local_capture_handoff import PLAN, _validate_plan
from tools.map02_verified_process_launch import launch_observed_pc
from tools.seal_map02_private_finalization import (
    _roots, seal_final_capture, verify_final_seal,
)
from tools.verify_map02_frame_bundle import number
from tools.verify_map02_native_gpu_capture import private_file

SCHEMA = "vh.map02.private-one-shot-cycle.v1"


def execute_private_map02_cycle(source, native, scoped, handoff, cycle,
                                preview, rgb, seal_directory, owned_game,
                                upstream, binary, build_receipt, build_bundle,
                                *, frame, x, y, timeout=900,
                                krom_source=None, compiler="gcc",
                                allow_local_completion=False):
    """Run only after explicit permission to publish missing PRIVATE evidence.

    No shell, no upload, no retry after partial failure. Subsequent attempts
    must use a fresh session, never silently reuse existing output folders.
    """
    frame = number(frame, "selected MAP02 GPU frame", 1, 2**32 - 1)
    x = number(x, "MAP02 pixel X", 0, 1023)
    y = number(y, "MAP02 pixel Y", 0, 511)
    timeout = number(timeout, "MAP02 launch timeout", 1, 86400)
    if compiler not in ("gcc", "clang"):
        raise ValueError("unsupported MAP02 original diagnostic compiler")
    if allow_local_completion is not True:
        raise ValueError("explicit private MAP02 CD witness and PNG completion permission required")

    captures = (source, native, scoped, handoff, cycle, preview, rgb)
    sealed = _roots(captures, seal_directory)
    if tuple(sealed.iterdir()):
        raise ValueError("private MAP02 seal directory must be empty before execution")

    # The original plan's GPU DrawOTag must be the *requested* frame.
    # No original PC process has been started at this point.
    plan_raw = private_file(Path(handoff).absolute(), PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)
    if plan["target_gpu_draw_frame"] != frame:
        raise ValueError("MAP02 requested frame differs from prepared private plan")

    ready = verify_private_cycle_readiness(
        *captures, pc_binary=binary, owned_game_image=owned_game,
        upstream_checkout=upstream, build_receipt_dir=build_receipt,
        build_bundle_dir=build_bundle, krom_source=krom_source)
    if ready["ready_for_controlled_local_launch"] is not True:
        raise ValueError("MAP02 original PC cycle preflight was not confirmed")
    if private_file(Path(handoff).absolute(), PLAN, max_bytes=4096) != plan_raw:
        raise ValueError("MAP02 private launch plan changed before execution")

    observed = launch_observed_pc(
        handoff, native, scoped, binary, owned_game, upstream=upstream,
        x=x, y=y, timeout=timeout, cycle_dir=cycle,
        build_receipt_dir=build_receipt, build_bundle_dir=build_bundle,
        krom_source=krom_source, pc_preoverlay_dir=rgb,
        source_capture_dir=source, native_preview_dir=preview,
        require_complete_preflight=True, stop_after_present=True)
    if (observed["kernel_executable_hash_matched"] is not True or
            observed["same_process_gpu_scoped_nonce_checked"] is not True or
            observed["pc_preoverlay_capture_session_bound"] is not True):
        raise ValueError("MAP02 observed local PC process not source/RGB24-bound")

    # Only these two original-CD/GPU witness and PNG names may be created
    # locally, and only after successful observed process exit.
    finalized = finalize_private_capture(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, frame=frame, compiler=compiler,
        complete_missing=True)
    if (finalized["independently_verified_cd_gpu_process_and_rgb24_png"]
            is not True or finalized["gpu_draw_frame"] != frame or
            finalized["original_map02_rendering_proven"] is not False):
        raise ValueError("MAP02 original CD/GPU/PC RGB24/PNG final join not verified")

    sealed_report = seal_final_capture(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory,
        frame=frame, compiler=compiler)
    if (sealed_report["two_independent_readonly_final_audits"] is not True or
            sealed_report["postpublication_independent_verification_completed"]
            is not True or sealed_report["gpu_draw_frame"] != frame):
        raise ValueError("MAP02 private completion seal not independently verified")

    verified = verify_final_seal(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory,
        frame=frame, compiler=compiler)
    if (verified["sealed_evidence_independently_reverified"] is not True or
            verified["gpu_draw_frame"] != frame or
            verified["private_final_seal_sha256"] !=
            sealed_report["private_final_seal_sha256"] or
            verified["original_map02_rendering_proven"] is not False):
        raise ValueError("MAP02 final seal changed after source-bound execution")
    return {
        "schema": SCHEMA,
        "gpu_draw_frame": frame,
        "private_final_seal_sha256": verified["private_final_seal_sha256"],
        "observed_process_receipt_verified": True,
        "original_cd_gpu_process_rgb24_png_join_verified": True,
        "private_completion_seal_independently_reverified": True,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
        "private_game_files_uploaded": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for role in ("source", "native", "scoped", "handoff", "cycle",
                 "preview", "rgb", "seal"):
        p.add_argument("private_" + role + "_directory", type=Path)
    p.add_argument("private_owned_game_image", type=Path)
    p.add_argument("--upstream-checkout", type=Path, required=True)
    p.add_argument("--pc-binary", type=Path, required=True)
    p.add_argument("--build-receipt-dir", type=Path, required=True)
    p.add_argument("--build-bundle-dir", type=Path, required=True)
    p.add_argument("--krom-source", type=Path)
    p.add_argument("--frame", type=int, required=True)
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--compiler", choices=("gcc", "clang"), default="gcc")
    p.add_argument("--allow-local-completion", action="store_true",
                   help="allow publishing only the named original CD witness and PNG in private folders")
    args = p.parse_args()
    try:
        result = execute_private_map02_cycle(
            *(getattr(args, "private_" + role + "_directory")
              for role in ("source", "native", "scoped", "handoff", "cycle",
                           "preview", "rgb", "seal")),
            args.private_owned_game_image, args.upstream_checkout,
            args.pc_binary, args.build_receipt_dir,
            args.build_bundle_dir, frame=args.frame, x=args.x, y=args.y,
            timeout=args.timeout, krom_source=args.krom_source,
            compiler=args.compiler,
            allow_local_completion=args.allow_local_completion)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Exceptions from the original ELF/CD/asset verifiers may contain
        # user-owned source paths; do not copy those into terminal/CI logs.
        p.error("private MAP02 one-shot execution/finalization unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
