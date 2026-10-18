#!/usr/bin/env python3
"""Read-only strict prelaunch readiness check for the private MAP02 PC cycle.

Reuses the actual source-pinned ELF/build, original image and capture layout
verifiers without executing or modifying a game. A passing result is only a
preflight: it does not attest the next process or a retail MAP02 frame.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from tools.check_map02_private_launch_layout import inspect_private_launch_layout
from tools.check_map02_cycle_elf import audit_cycle_elf
from tools.check_map02_linked_font_elf import stable_owned_elf_sha256
from tools.map02_cycle_build_provenance import verify_build_receipt
from tools.map02_local_capture_handoff import PLAN, _validate_plan, verify_pinned_upstream
from tools.map02_verified_process_launch import _stable_owned_cycle_image
from tools.verify_map02_native_gpu_capture import private_file


def verify_private_cycle_readiness(source, native, scoped, handoff, cycle,
                                   preview, preoverlay, *, pc_binary,
                                   owned_game_image, upstream_checkout,
                                   build_receipt_dir, build_bundle_dir,
                                   krom_source=None):
    """Read and compare exact private evidence; never execute a subprocess.

    The source/private/build verifiers may invoke their existing read-only
    metadata tools (for example readelf or make -n), but not the game itself.
    """
    if not sys.platform.startswith("linux") or not Path("/proc/self/exe").exists():
        raise ValueError("strict MAP02 cycle process observation requires Linux procfs")
    layout_args = (source, native, scoped, handoff, cycle, preview, preoverlay)
    first_layout = inspect_private_launch_layout(*layout_args)
    if first_layout["prelaunch_layout_ready"] is not True:
        raise ValueError("private MAP02 directory layout is not ready")

    handoff = Path(handoff).absolute()
    binary = Path(pc_binary).absolute()
    image = Path(owned_game_image).absolute()
    upstream = Path(upstream_checkout).absolute()
    plan_raw = private_file(handoff, PLAN, max_bytes=4096)
    plan = _validate_plan(plan_raw)

    pinned_source = verify_pinned_upstream(upstream)
    if plan["pinned_upstream_source_identity_sha256"] != pinned_source:
        raise ValueError("private MAP02 source identity differs from capture plan")
    executable_sha = stable_owned_elf_sha256(binary)
    if plan["pc_executable_sha256"] != executable_sha:
        raise ValueError("source-bound MAP02 executable differs from capture plan")
    elf_report = audit_cycle_elf(binary)
    if elf_report["required_symbols_present"] <= 0:
        raise ValueError("required MAP02 native cycle symbols not verified")
    image_proof = _stable_owned_cycle_image(image)
    if plan["owned_game_image_sha256"] != image_proof[1]:
        raise ValueError("private MAP02 game image differs from capture plan")
    receipt = verify_build_receipt(
        build_receipt_dir, binary, upstream, build_bundle_dir,
        krom_source=krom_source)
    if receipt["source_pinned_full_elf_bytes_checked"] is not True:
        raise ValueError("full original PC ELF build provenance not verified")

    # Expensive independent checks above must refer to one coherent set.
    # No claim about a future process is issued if anything changed meanwhile.
    if (private_file(handoff, PLAN, max_bytes=4096) != plan_raw or
            verify_pinned_upstream(upstream) != pinned_source or
            stable_owned_elf_sha256(binary) != executable_sha or
            _stable_owned_cycle_image(image) != image_proof):
        raise ValueError("source-bound MAP02 launch inputs changed during preflight")
    second_layout = inspect_private_launch_layout(*layout_args)
    if second_layout != first_layout:
        raise ValueError("private MAP02 launch layout changed during preflight")

    return {
        "schema": "vh.map02.private-pc-cycle-readiness.v1",
        "private_directories_checked": first_layout["private_directory_roles_checked"],
        "capture_folders_empty": first_layout["capture_output_directories_empty"],
        "source_bound_plan_checked": True,
        "original_pc_source_identity_checked": True,
        "complete_pc_elf_symbols_checked": True,
        "complete_pc_elf_bytes_checked": True,
        "private_original_image_bytes_checked": True,
        "pinned_full_elf_build_receipt_checked": True,
        "prelaunch_inputs_stable_across_checks": True,
        "ready_for_controlled_local_launch": True,
        "gameplay_process_started": False,
        "original_map02_rendering_proven": False,
        "hardware_ps1_equivalence_proven": False,
        "game_content_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ("source", "native", "scoped", "handoff",
                 "cycle", "preview", "preoverlay"):
        parser.add_argument("private_" + role + "_directory", type=Path)
    parser.add_argument("--pc-binary", type=Path, required=True)
    parser.add_argument("--owned-game-image", type=Path, required=True)
    parser.add_argument("--upstream-checkout", type=Path, required=True)
    parser.add_argument("--build-receipt-dir", type=Path, required=True)
    parser.add_argument("--build-bundle-dir", type=Path, required=True)
    parser.add_argument("--krom-source", type=Path)
    options = parser.parse_args()
    try:
        report = verify_private_cycle_readiness(
            *(getattr(options, "private_" + role + "_directory")
              for role in ("source", "native", "scoped", "handoff",
                           "cycle", "preview", "preoverlay")),
            pc_binary=options.pc_binary,
            owned_game_image=options.owned_game_image,
            upstream_checkout=options.upstream_checkout,
            build_receipt_dir=options.build_receipt_dir,
            build_bundle_dir=options.build_bundle_dir,
            krom_source=options.krom_source)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Never expose private EXE, disc, asset paths, subprocess output,
        # or source-file excerpts via the terminal or CI logs.
        parser.error("private source-bound MAP02 cycle readiness unavailable")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
