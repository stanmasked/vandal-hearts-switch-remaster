#!/usr/bin/env python3
"""Link actual Ubuntu libxcb.a after real X11.a on asset-free public PC ELF.

Strictly check the x86-64 ELF's 996 known strong undefined names and
ordinary native archive. Return ONLY aggregate counts and SHA-256.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _private_output_dir,
    _unresolved, probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import audit_provider_coverage
from tools.check_map02_public_sdl2_archive_witness import _copy_system_archive
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest

SCHEMA = "vh.map02.public-after-x11-xcb-static-witness.v1"
COPY_NAME = "xcb-system-candidate.a"
LOCAL_MANIFEST = "after-x11-unresolved.private.json"


def measure_xcb_after_x11(x11_linked_public_elf, system_xcb_archive, output_root,
                          *, expected_x11_undefined=996):
    """One genuine GNU ld-r, pinned original X11-stage ELF + system XCB.a."""
    if type(expected_x11_undefined) is not int or expected_x11_undefined < 0:
        raise ValueError("MAP02 XCB expected strong baseline invalid")
    original = _open_owned(x11_linked_public_elf, require_private=True)
    try:
        if Path(x11_linked_public_elf).suffix != ".o":
            raise ValueError("MAP02 XCB stage requires native ELF relocatable")
        _check_abi(original)
        strong, weak = _unresolved(original)
        if len(strong) != expected_x11_undefined:
            raise ValueError("MAP02 XCB baseline strong import count differs")
        _confirm_owned(original)
        folder, _ = _private_output_dir(output_root)
        # Reuse the verified O_EXCL, owner-only 0600 manifest writer.
        old_manifest = _save_local_undefined_manifest(
            folder, original, strong, weak)
        manifest = folder / LOCAL_MANIFEST
        old_manifest.rename(manifest)
        copied = folder / COPY_NAME
        copy_digest = _copy_system_archive(system_xcb_archive, copied)
        archive = _open_owned(copied, require_private=True)
        try:
            if archive[3] != copy_digest:
                raise ValueError("MAP02 XCB copied static archive hash changed")
            coverage = audit_provider_coverage(manifest, [copied])
            _confirm_owned(archive)
            actual = probe_private_incremental_link(
                manifest, x11_linked_public_elf, [copied], folder / "linked",
                expected_initial_strong_imports=expected_x11_undefined)
            _confirm_owned(archive)
            _confirm_owned(original)
        finally:
            os.close(archive[0])
        if (coverage["original_strong_unresolved_count"] != expected_x11_undefined
                or coverage["candidate_provider_file_count"] != 1
                or coverage["strong_symbols_with_candidate_provider"] +
                   coverage["strong_symbols_without_candidate_provider"] !=
                   expected_x11_undefined
                or actual["source_partial_elf_sha256"] != original[3]
                or actual["original_strong_import_count"] !=
                   expected_x11_undefined
                or actual["candidate_count"] != 1
                or actual["candidate_archive_count"] != 1
                or actual["archive_selection_strategy"] !=
                   "single_pass_user_order"
                or actual["original_strong_imports_resolved_by_ld_r"] +
                   actual["original_strong_imports_remaining_after_ld_r"] !=
                   expected_x11_undefined
                or actual["original_strong_imports_remaining_after_ld_r"] +
                   actual["new_strong_imports_introduced_by_candidates"] !=
                   actual["final_strong_import_count"]):
            raise ValueError("MAP02 real XCB partial link witness inconsistent")
        return {
            "schema": SCHEMA,
            "input_x11_partial_sha256": original[3],
            "copied_xcb_archive_sha256": copy_digest,
            "output_xcb_partial_sha256": actual["linked_candidate_elf_sha256"],
            "initial_after_x11_strong_undefined": expected_x11_undefined,
            "xcb_strong_export_matches": coverage[
                "strong_symbols_with_candidate_provider"],
            "input_symbols_without_xcb_strong_export": coverage[
                "strong_symbols_without_candidate_provider"],
            "original_after_x11_imports_resolved": actual[
                "original_strong_imports_resolved_by_ld_r"],
            "original_after_x11_imports_remaining": actual[
                "original_strong_imports_remaining_after_ld_r"],
            "new_imports_introduced_by_xcb": actual[
                "new_strong_imports_introduced_by_candidates"],
            "final_strong_undefined_after_xcb": actual[
                "final_strong_import_count"],
            "ordinary_native_static_archive_tested": True,
            "system_archive_package_origin_independently_attested": False,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        os.close(original[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_x11_linked_public_pc_elf", type=Path)
    parser.add_argument("system_xcb_static_archive", type=Path)
    parser.add_argument("new_owner_private_output_dir", type=Path)
    args = parser.parse_args()
    try:
        report = measure_xcb_after_x11(
            args.owner_private_x11_linked_public_pc_elf,
            args.system_xcb_static_archive, args.new_owner_private_output_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 real XCB after-X11 system archive probe failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
