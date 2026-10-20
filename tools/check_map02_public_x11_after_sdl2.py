#!/usr/bin/env python3
"""Measure real Ubuntu X11 static providers after SDL2 in public MAP02 ELF.

Input is the asset-free PC ELF from the real Ubuntu SDL2 ld -r stage.
Never print or upload original import names or user-owned retail content.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _private_output_dir,
    probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    _sha_names, audit_provider_coverage,
)
from tools.check_map02_public_sdl2_archive_witness import _copy_system_archive

SCHEMA = "vh.map02.public-after-sdl2-x11-static-witness.v1"
MANIFEST_SCHEMA = "vh.map02.private-undefined-symbol-manifest.v1"
MANIFEST = "after-sdl2-unresolved.private.json"
ARCHIVE = "x11-system-candidate.a"


def _save_local_undefined_manifest(folder, entry, strong, weak):
    """One O_EXCL 0600 private manifest, never stdout or CI artifacts."""
    report = {
        "schema": MANIFEST_SCHEMA,
        "relocatable_elf_sha256": entry[3],
        "partial_elf_unresolved_strong_symbol_count": len(strong),
        "partial_elf_unresolved_weak_symbol_count": len(weak),
        "partial_elf_unresolved_strong_symbols_sha256": _sha_names(strong),
        "strong_symbols": strong,
        "weak_symbols": weak,
    }
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    if not 0 < len(payload) <= 4 * 1024 * 1024:
        raise ValueError("MAP02 after-SDL2 private manifest size invalid")
    fd = None
    try:
        fd = os.open(
            folder / MANIFEST,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        remaining = memoryview(payload)
        while remaining:
            n = os.write(fd, remaining)
            if n <= 0:
                raise ValueError("MAP02 after-SDL2 manifest write incomplete")
            remaining = remaining[n:]
        os.fsync(fd)
    finally:
        if fd is not None:
            os.close(fd)
    return folder / MANIFEST


def measure_x11_after_sdl2(sdl2_linked_partial, system_x11_archive, output_root,
                           *, expected_sdl2_undefined=1085):
    """Run an actual one-archive GNU ld -r on the previously linked public ELF."""
    if (type(expected_sdl2_undefined) is not int
            or expected_sdl2_undefined < 0):
        raise ValueError("MAP02 after-SDL2 expected baseline invalid")
    source = _open_owned(sdl2_linked_partial, require_private=True)
    try:
        if Path(sdl2_linked_partial).suffix != ".o":
            raise ValueError("MAP02 after-SDL2 input must be an ELF object")
        _check_abi(source)
        from tools.check_map02_private_incremental_link import _unresolved
        strong, weak = _unresolved(source)
        if len(strong) != expected_sdl2_undefined:
            raise ValueError("MAP02 after-SDL2 source strong import count differs")
        _confirm_owned(source)
        root, _ = _private_output_dir(output_root)
        manifest = _save_local_undefined_manifest(root, source, strong, weak)
        archive_path = root / ARCHIVE
        digest = _copy_system_archive(system_x11_archive, archive_path)
        archived = _open_owned(archive_path, require_private=True)
        try:
            if archived[3] != digest:
                raise ValueError("MAP02 X11 copied archive SHA mismatch")
            coverage = audit_provider_coverage(manifest, [archive_path])
            _confirm_owned(archived)
            actual = probe_private_incremental_link(
                manifest, sdl2_linked_partial, [archive_path], root / "linked",
                expected_initial_strong_imports=expected_sdl2_undefined)
            _confirm_owned(archived)
            _confirm_owned(source)
        finally:
            os.close(archived[0])
        if (coverage["original_strong_unresolved_count"] !=
                expected_sdl2_undefined
                or coverage["candidate_provider_file_count"] != 1
                or coverage["strong_symbols_with_candidate_provider"] +
                   coverage["strong_symbols_without_candidate_provider"] !=
                   expected_sdl2_undefined
                or actual["source_partial_elf_sha256"] != source[3]
                or actual["original_strong_import_count"] !=
                   expected_sdl2_undefined
                or actual["candidate_archive_count"] != 1
                or actual["archive_selection_strategy"] !=
                   "single_pass_user_order"
                or actual["original_strong_imports_remaining_after_ld_r"] +
                   actual["new_strong_imports_introduced_by_candidates"] !=
                   actual["final_strong_import_count"]):
            raise ValueError("MAP02 X11 real archive witness inconsistent")
        return {
            "schema": SCHEMA,
            "input_sdl2_partial_sha256": source[3],
            "copied_x11_archive_sha256": digest,
            "output_x11_partial_sha256": actual["linked_candidate_elf_sha256"],
            "initial_after_sdl2_undefined": expected_sdl2_undefined,
            "x11_strong_export_matches": coverage[
                "strong_symbols_with_candidate_provider"],
            "initial_imports_without_x11_candidate": coverage[
                "strong_symbols_without_candidate_provider"],
            "original_after_sdl2_imports_resolved": actual[
                "original_strong_imports_resolved_by_ld_r"],
            "original_after_sdl2_imports_remaining": actual[
                "original_strong_imports_remaining_after_ld_r"],
            "new_imports_introduced_by_x11": actual[
                "new_strong_imports_introduced_by_candidates"],
            "final_strong_undefined_after_x11": actual[
                "final_strong_import_count"],
            "ordinary_native_static_archive_tested": True,
            "system_package_origin_independently_attested": False,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        os.close(source[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_linked_sdl2_public_elf", type=Path)
    parser.add_argument("system_x11_static_archive", type=Path)
    parser.add_argument("new_owner_private_output_root", type=Path)
    args = parser.parse_args()
    try:
        result = measure_x11_after_sdl2(
            args.owner_private_linked_sdl2_public_elf,
            args.system_x11_static_archive,
            args.new_owner_private_output_root)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 real X11 after-SDL2 archive probe failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
