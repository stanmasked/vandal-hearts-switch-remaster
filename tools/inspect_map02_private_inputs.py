#!/usr/bin/env python3
"""Read-only, metadata-only inventory of private original MAP02 inputs.

This is deliberately NOT an original-data verifier or an execution gate.
No original file is opened, hashed, read or copied. Only safe flags and counts
are reported; caller-controlled paths and file bytes never reach stdout.
"""
import argparse
import json
import os
from pathlib import Path
import stat

from tools.check_map02_private_pc_inputs import ASSETS, EXE, FONT_GENERATOR
from tools.check_map02_cycle_make_plan import BUILD
from tools.map02_cycle_build_provenance import NAME as BUILD_RECEIPT
from tools.map02_local_capture_handoff import PLAN


def _regular(path, *, owner_only=False, executable=False):
    """Reject symlinks and non-owned or multiply-linked candidates."""
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or info.st_size == 0):
        return False
    permissions = stat.S_IMODE(info.st_mode)
    if owner_only and permissions != 0o600:
        return False
    if executable and not permissions & stat.S_IXUSR:
        return False
    return True


def _folder(path, *, private=False):
    try:
        info = Path(path).lstat()
    except OSError:
        return False
    return (stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and (not private or stat.S_IMODE(info.st_mode) == 0o700))


def inspect_private_map02_inputs(upstream, owned_image, build_bundle,
                                 build_receipt_dir, handoff_dir,
                                 *, krom_source=None):
    """Discover absent prerequisites, never confer permission to start a game."""
    root = Path(upstream).absolute()
    image = Path(owned_image).absolute()
    bundle = Path(build_bundle).absolute()
    receipt_dir = Path(build_receipt_dir).absolute()
    handoff = Path(handoff_dir).absolute()
    krom = (Path(krom_source).absolute() if krom_source is not None else
            root / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN")
    upstream_ok = _folder(root)
    bundle_ok = _folder(bundle, private=True)
    receipt_ok = _folder(receipt_dir, private=True)
    handoff_ok = _folder(handoff, private=True)
    includes_count = sum(
        _regular(root / "assets" / name) for name in ASSETS)
    statuses = {
        "pinned_upstream_checkout_directory_present": upstream_ok,
        "original_us_psx_executable_path_present": _regular(root / EXE),
        "extracted_original_mips_elf_path_present":
            _regular(root / "build" / (EXE + ".elf")),
        "original_asset_include_paths_present": includes_count,
        "original_asset_include_paths_expected": len(ASSETS),
        "pinned_font_generator_path_present":
            _regular(root / FONT_GENERATOR),
        "owned_krom_or_ps1_bios_path_present": _regular(krom),
        "owned_disc_image_private_path_present":
            _regular(image, owner_only=True),
        "full_pc_elf_executable_path_present":
            _regular(root / "platform/pc" / BUILD / "vandalhearts_pc",
                     executable=True),
        "prepared_private_build_bundle_directory_present": bundle_ok,
        "build_bundle_manifest_path_present":
            bundle_ok and _regular(bundle / "map02_cycle_build_inputs.json",
                                   owner_only=True),
        "build_bundle_make_overlay_path_present":
            bundle_ok and _regular(bundle / "map02_cycle.mk",
                                   owner_only=True),
        "private_build_receipt_directory_present": receipt_ok,
        "private_build_receipt_path_present":
            receipt_ok and _regular(receipt_dir / BUILD_RECEIPT,
                                    owner_only=True),
        "private_handoff_directory_present": handoff_ok,
        "private_capture_plan_path_present":
            handoff_ok and _regular(handoff / PLAN, owner_only=True),
    }
    present = all(
        value == len(ASSETS) if name == "original_asset_include_paths_present"
        else value is True
        for name, value in statuses.items()
        if name != "original_asset_include_paths_expected")
    return {
        "schema": "vh.map02.private-input-presence-inventory.v1",
        **statuses,
        "all_prerequisite_paths_present": present,
        "original_file_bytes_verified": False,
        "build_provenance_authenticated": False,
        "ready_for_controlled_local_launch": False,
        "gameplay_process_started": False,
        "original_map02_rendering_proven": False,
        "private_game_files_uploaded": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_original_pc_checkout", type=Path)
    parser.add_argument("private_owned_disc_image", type=Path)
    parser.add_argument("private_build_bundle_directory", type=Path)
    parser.add_argument("private_build_receipt_directory", type=Path)
    parser.add_argument("private_handoff_directory", type=Path)
    parser.add_argument("--krom-source", type=Path)
    args = parser.parse_args()
    try:
        report = inspect_private_map02_inputs(
            args.pinned_original_pc_checkout,
            args.private_owned_disc_image,
            args.private_build_bundle_directory,
            args.private_build_receipt_directory,
            args.private_handoff_directory,
            krom_source=args.krom_source)
    except (OSError, ValueError):
        parser.error("MAP02 private prerequisite inventory unavailable")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
