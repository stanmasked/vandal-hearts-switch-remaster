#!/usr/bin/env python3
"""Test real X11.a + XCB.a repeated archive resolution on public MAP02 ELF.

This is an independent GNU ld -r --start-group/--end-group experiment on the
asset-free, SDL2-linked public PC ELF. It publishes numeric counts and hashes
only, never symbol names, retail files, or user paths.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _unresolved,
    probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)

SCHEMA = "vh.map02.public-sdl2-x11-xcb-grouped-archive-link.v1"


def measure_grouped_x11_xcb(private_after_sdl2_manifest, sdl2_linked_elf,
                            private_copied_x11_archive,
                            private_copied_xcb_archive,
                            new_private_output_dir, *,
                            expected_sdl2_strong_imports=1085):
    """Measure grouped two-archive GNU ld-r, not sequentially guessed counts."""
    if (type(expected_sdl2_strong_imports) is not int
            or expected_sdl2_strong_imports < 0):
        raise ValueError("MAP02 grouped public expected strong baseline invalid")
    if (Path(sdl2_linked_elf).suffix != ".o"
            or Path(private_copied_x11_archive).suffix != ".a"
            or Path(private_copied_xcb_archive).suffix != ".a"):
        raise ValueError("MAP02 grouped public native input types invalid")
    manifest = read_private_manifest(private_after_sdl2_manifest)
    entries = []
    try:
        for path in (sdl2_linked_elf, private_copied_x11_archive,
                     private_copied_xcb_archive):
            entry = _open_owned(path, require_private=True)
            entries.append(entry)
            _check_abi(entry)
        source, x11, xcb = entries
        if len({(e[2][0], e[2][1]) for e in entries}) != 3:
            raise ValueError("MAP02 grouped public repeated candidate inode")
        if source[3] != manifest["relocatable_elf_sha256"]:
            raise ValueError("MAP02 grouped public source hash differs")
        originals, weak = _unresolved(source)
        if (originals != manifest["strong_symbols"]
                or weak != manifest["weak_symbols"]
                or len(originals) != expected_sdl2_strong_imports):
            raise ValueError("MAP02 grouped public original symbol set differs")
        for e in entries:
            _confirm_owned(e)
        providers = audit_provider_coverage(
            private_after_sdl2_manifest,
            [private_copied_x11_archive, private_copied_xcb_archive])
        if (providers["original_strong_unresolved_count"] !=
                expected_sdl2_strong_imports
                or providers["candidate_provider_file_count"] != 2
                or (providers["strong_symbols_with_candidate_provider"] +
                    providers["strong_symbols_without_candidate_provider"] !=
                    expected_sdl2_strong_imports)):
            raise ValueError("MAP02 grouped public archive coverage inconsistent")
        linked = probe_private_incremental_link(
            private_after_sdl2_manifest, sdl2_linked_elf,
            [private_copied_x11_archive, private_copied_xcb_archive],
            new_private_output_dir, group_archives=True,
            expected_initial_strong_imports=expected_sdl2_strong_imports)
        for e in entries:
            _confirm_owned(e)
        if (linked["source_partial_elf_sha256"] != source[3]
                or linked["candidate_count"] != 2
                or linked["candidate_archive_count"] != 2
                or linked["archive_selection_strategy"] !=
                   "repeated_archive_group"
                or linked["original_strong_import_count"] !=
                   expected_sdl2_strong_imports
                or linked["original_strong_imports_resolved_by_ld_r"] +
                   linked["original_strong_imports_remaining_after_ld_r"] !=
                   expected_sdl2_strong_imports
                or linked["original_strong_imports_remaining_after_ld_r"] +
                   linked["new_strong_imports_introduced_by_candidates"] !=
                   linked["final_strong_import_count"]):
            raise ValueError("MAP02 grouped public genuine native link inconsistent")
        return {
            "schema": SCHEMA,
            "input_sdl2_partial_sha256": source[3],
            "copied_x11_archive_sha256": x11[3],
            "copied_xcb_archive_sha256": xcb[3],
            "grouped_output_partial_sha256": linked["linked_candidate_elf_sha256"],
            "initial_strong_undefined_after_sdl2": expected_sdl2_strong_imports,
            "original_inputs_with_any_x11_xcb_strong_provider":
                providers["strong_symbols_with_candidate_provider"],
            "original_inputs_with_multiple_x11_xcb_providers":
                providers["strong_symbols_with_multiple_candidates"],
            "original_inputs_without_x11_xcb_strong_provider":
                providers["strong_symbols_without_candidate_provider"],
            "original_imports_resolved_by_grouped_ld_r":
                linked["original_strong_imports_resolved_by_ld_r"],
            "original_imports_remaining_after_grouped_ld_r":
                linked["original_strong_imports_remaining_after_ld_r"],
            "new_imports_introduced_by_grouped_x11_xcb":
                linked["new_strong_imports_introduced_by_candidates"],
            "final_strong_undefined_after_grouped_x11_xcb":
                linked["final_strong_import_count"],
            "real_gnu_archive_group_executed": True,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for entry in entries:
            os.close(entry[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("after_sdl2_private_manifest", type=Path)
    parser.add_argument("after_sdl2_private_elf", type=Path)
    parser.add_argument("private_copied_x11_archive", type=Path)
    parser.add_argument("private_copied_xcb_archive", type=Path)
    parser.add_argument("new_private_grouped_output_dir", type=Path)
    args = parser.parse_args()
    try:
        result = measure_grouped_x11_xcb(
            args.after_sdl2_private_manifest, args.after_sdl2_private_elf,
            args.private_copied_x11_archive, args.private_copied_xcb_archive,
            args.new_private_grouped_output_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 grouped X11/XCB GNU ld-r experiment failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
