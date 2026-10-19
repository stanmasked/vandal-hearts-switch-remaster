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

from tools.check_map02_private_launch_layout import (
    _directory_identity, inspect_private_launch_layout,
)
from tools.check_map02_private_cycle_readiness import verify_private_cycle_readiness
from tools.finalize_map02_private_capture import finalize_private_capture
from tools.map02_local_capture_handoff import PLAN, _validate_plan
from tools.map02_verified_process_launch import launch_observed_pc
from tools.seal_map02_private_finalization import (
    _dir_identity, _roots, seal_final_capture, verify_final_seal,
)
from tools.verify_map02_frame_bundle import number
from tools.verify_map02_native_gpu_capture import private_file

SCHEMA = "vh.map02.private-one-shot-cycle.v1"
# These fixed identifiers are safe to print after errors from private inputs.
# Never emit raw exception messages, child output, paths, or source contents.
SAFE_STAGES = (
    "argument-validation", "private-layout", "capture-plan",
    "full-preflight", "observed-process", "capture-finalization",
    "seal-publication", "seal-verification", "complete",
)

# A readiness result is not a boolean permission token. Its complete
# no-gameplay/no-publication contract must agree with the independent
# preflight before the coordinator can start the original PC binary.
READINESS_TRUE = (
    "source_bound_plan_checked", "original_pc_source_identity_checked",
    "complete_pc_elf_symbols_checked", "complete_pc_elf_bytes_checked",
    "private_original_image_bytes_checked",
    "pinned_full_elf_build_receipt_checked",
    "prelaunch_inputs_stable_across_checks",
)
READINESS_FALSE = (
    "gameplay_process_started", "original_map02_rendering_proven",
    "hardware_ps1_equivalence_proven", "game_content_emitted",
)
READINESS_FIELDS = frozenset((
    "schema", "private_directories_checked", "capture_folders_empty",
    "ready_for_controlled_local_launch", *READINESS_TRUE, *READINESS_FALSE,
))


def _require_full_readiness_report(ready):
    if type(ready) is not dict or ready.get("ready_for_controlled_local_launch") is not True:
        raise ValueError("MAP02 original PC cycle preflight was not confirmed")
    if (set(ready) != READINESS_FIELDS or
            ready.get("schema") != "vh.map02.private-pc-cycle-readiness.v1" or
            type(ready.get("private_directories_checked")) is not int or
            ready["private_directories_checked"] != 7 or
            type(ready.get("capture_folders_empty")) is not int or
            ready["capture_folders_empty"] != 5 or
            any(ready.get(k) is not True for k in READINESS_TRUE) or
            any(ready.get(k) is not False for k in READINESS_FALSE)):
        raise ValueError("MAP02 original PC cycle preflight report contract mismatch")


def execute_private_map02_cycle(source, native, scoped, handoff, cycle,
                                preview, rgb, seal_directory, owned_game,
                                upstream, binary, build_receipt, build_bundle,
                                *, frame, x, y, timeout=900,
                                krom_source=None, compiler="gcc",
                                allow_local_completion=False,
                                dry_run=False, stage_callback=None):
    """Run only after explicit permission to publish missing PRIVATE evidence.

    No shell, no upload, no retry after partial failure. Subsequent attempts
    must use a fresh session, never silently reuse existing output folders.
    """
    def enter(stage):
        if stage_callback is not None:
            stage_callback(stage)

    enter("argument-validation")
    frame = number(frame, "selected MAP02 GPU frame", 1, 2**32 - 1)
    x = number(x, "MAP02 pixel X", 0, 1023)
    y = number(y, "MAP02 pixel Y", 0, 511)
    timeout = number(timeout, "MAP02 launch timeout", 1, 86400)
    if compiler not in ("gcc", "clang"):
        raise ValueError("unsupported MAP02 original diagnostic compiler")
    if type(dry_run) is not bool:
        raise ValueError("private MAP02 dry-run mode must be boolean")
    if dry_run and allow_local_completion:
        raise ValueError("MAP02 dry-run forbids local completion permission")
    if not dry_run and allow_local_completion is not True:
        raise ValueError("explicit private MAP02 CD witness and PNG completion permission required")

    enter("private-layout")
    captures = (source, native, scoped, handoff, cycle, preview, rgb)
    sealed = _roots(captures, seal_directory)
    if tuple(sealed.iterdir()):
        raise ValueError("private MAP02 seal directory must be empty before execution")
    original_seal_directory_identity = _dir_identity(sealed.stat())
    # The readiness verifier protects its own seven roots, but the caller
    # must also guard the interval between its last check and the decision
    # to report a successful dry-run or start the real PC process.
    original_capture_directory_identities = tuple(
        _directory_identity(Path(folder).absolute(), "prelaunch")
        for folder in captures)

    def require_original_capture_directories():
        if tuple(
            _directory_identity(Path(folder).absolute(), "prelaunch")
            for folder in captures
        ) != original_capture_directory_identities:
            raise ValueError("private MAP02 capture folders changed during one-shot preflight")

    def require_original_seal_directory(*, must_be_empty):
        current = _roots(captures, seal_directory)
        if _dir_identity(current.stat()) != original_seal_directory_identity:
            raise ValueError("private MAP02 seal directory changed during one-shot session")
        if must_be_empty and tuple(current.iterdir()):
            raise ValueError("private MAP02 seal directory unexpectedly populated")

    enter("capture-plan")
    # The original plan's GPU DrawOTag must be the *requested* frame.
    # No original PC process has been started at this point.
    plan_raw, plan_identity = private_file(
        Path(handoff).absolute(), PLAN, max_bytes=4096, _with_identity=True)
    plan = _validate_plan(plan_raw)
    if plan["target_gpu_draw_frame"] != frame:
        raise ValueError("MAP02 requested frame differs from prepared private plan")

    enter("full-preflight")
    ready = verify_private_cycle_readiness(
        *captures, pc_binary=binary, owned_game_image=owned_game,
        upstream_checkout=upstream, build_receipt_dir=build_receipt,
        build_bundle_dir=build_bundle, krom_source=krom_source)
    _require_full_readiness_report(ready)
    if private_file(Path(handoff).absolute(), PLAN, max_bytes=4096,
                    _with_identity=True) != (plan_raw, plan_identity):
        raise ValueError("MAP02 private launch plan changed before execution")
    require_original_capture_directories()
    require_original_seal_directory(must_be_empty=True)
    # A second independent structural scan closes the gap after the
    # readiness verifier returns: metadata equality alone must not let an
    # unexpected capture file or changed handoff inventory pass.
    final_layout = inspect_private_launch_layout(*captures)
    if (type(final_layout) is not dict or
            final_layout.get("prelaunch_layout_ready") is not True or
            final_layout.get("private_directory_roles_checked") != 7 or
            final_layout.get("capture_output_directories_empty") != 5 or
            final_layout.get("single_private_handoff_plan_present") is not True):
        raise ValueError("private MAP02 one-shot layout recheck was not confirmed")
    # The final structural scan checks the plan's existence, ownership and
    # mode, but not its bytes. Re-bind both contents and inode AFTER the
    # scan, including same-size in-place edits that leave directory metadata
    # unchanged. The native launcher will independently verify it again.
    if private_file(Path(handoff).absolute(), PLAN, max_bytes=4096,
                    _with_identity=True) != (plan_raw, plan_identity):
        raise ValueError("MAP02 private launch plan changed after final layout scan")
    require_original_capture_directories()
    require_original_seal_directory(must_be_empty=True)
    if dry_run:
        # Exactly the pre-execution checks used by the real one-shot path:
        # no subprocess, no output witness, no finalizer, no seal.
        enter("complete")
        return {
            "schema": "vh.map02.private-one-shot-dry-run.v1",
            "gpu_draw_frame": frame,
            "private_layout_and_capture_plan_checked": True,
            "full_private_original_elf_disc_preflight_checked": True,
            "ready_for_controlled_local_launch": True,
            "gameplay_process_started": False,
            "private_witnesses_written": False,
            "private_final_seal_published": False,
            "original_map02_rendering_proven": False,
            "physical_ps1_equivalence_proven": False,
            "private_game_files_uploaded": False,
        }

    enter("observed-process")
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

    # The destination cannot be replaced or populated while the original
    # child runs; refuse rather than redirecting a later exclusive seal.
    require_original_seal_directory(must_be_empty=True)
    # Only these two original-CD/GPU witness and PNG names may be created
    # locally, and only after successful observed process exit.
    enter("capture-finalization")
    finalized = finalize_private_capture(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, frame=frame, compiler=compiler,
        complete_missing=True)
    if (finalized["independently_verified_cd_gpu_process_and_rgb24_png"]
            is not True or finalized["gpu_draw_frame"] != frame or
            finalized["original_map02_rendering_proven"] is not False):
        raise ValueError("MAP02 original CD/GPU/PC RGB24/PNG final join not verified")

    require_original_seal_directory(must_be_empty=True)
    enter("seal-publication")
    sealed_report = seal_final_capture(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory,
        frame=frame, compiler=compiler)
    if (sealed_report["two_independent_readonly_final_audits"] is not True or
            sealed_report["postpublication_independent_verification_completed"]
            is not True or sealed_report["gpu_draw_frame"] != frame):
        raise ValueError("MAP02 private completion seal not independently verified")

    require_original_seal_directory(must_be_empty=False)
    enter("seal-verification")
    verified = verify_final_seal(
        source, native, scoped, handoff, cycle, preview, rgb,
        owned_game, upstream, binary, seal_directory,
        frame=frame, compiler=compiler)
    require_original_seal_directory(must_be_empty=False)
    if (verified["sealed_evidence_independently_reverified"] is not True or
            verified["gpu_draw_frame"] != frame or
            verified["private_final_seal_sha256"] !=
            sealed_report["private_final_seal_sha256"] or
            verified["original_map02_rendering_proven"] is not False):
        raise ValueError("MAP02 final seal changed after source-bound execution")
    enter("complete")
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
    p.add_argument("--dry-run", action="store_true",
                   help="verify identical private inputs and clean seal destination without starting the PC binary or writing evidence")
    args = p.parse_args()
    last_stage = ["argument-validation"]

    def remember_stage(stage):
        # Caller-controlled paths/exception strings must never become a
        # terminal diagnostic. Only exact, compile-time stage IDs qualify.
        if stage in SAFE_STAGES:
            last_stage[0] = stage

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
            allow_local_completion=args.allow_local_completion,
            dry_run=args.dry_run, stage_callback=remember_stage)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Exceptions from the original ELF/CD/asset verifiers may contain
        # user-owned source paths; do not copy those into terminal/CI logs.
        p.error("private MAP02 one-shot execution/finalization unavailable"
                " (stage=" + last_stage[0] + ")")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
