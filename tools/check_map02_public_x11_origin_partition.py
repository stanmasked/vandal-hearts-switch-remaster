#!/usr/bin/env python3
"""Partition real MAP02 X11 ld-r results by original versus SDL2-added imports.

No private symbol names, object paths, or archive bytes appear in output.
Input must be the owner-only real asset-free original/SDL2/X11 ET_REL chain.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _unresolved,
)
from tools.check_map02_private_provider_coverage import read_private_manifest

SCHEMA = "vh.map02.public-sdl2-x11-import-origin-partition.v1"


def partition_x11_import_origin(original_manifest, original_partial,
                                sdl2_manifest, sdl2_partial, x11_partial,
                                *, expected_original=520,
                                expected_after_sdl2=1085,
                                expected_original_remaining=493,
                                expected_sdl2_introduced=592):
    """Reread all three ELF symbol sets; return only counts and SHA-256."""
    expected = (expected_original, expected_after_sdl2,
                expected_original_remaining, expected_sdl2_introduced)
    if any(type(n) is not int or n < 0 for n in expected):
        raise ValueError("MAP02 import origin expected counts invalid")
    old_doc = read_private_manifest(original_manifest)
    sdl_doc = read_private_manifest(sdl2_manifest)
    entries = []
    try:
        for candidate in (original_partial, sdl2_partial, x11_partial):
            if Path(candidate).suffix != ".o":
                raise ValueError("MAP02 imported stages must be relocatable objects")
            entry = _open_owned(candidate, require_private=True)
            entries.append(entry)
            _check_abi(entry)
        if len({(x[2][0], x[2][1]) for x in entries}) != 3:
            raise ValueError("MAP02 import origin ELF inputs alias each other")
        first, second, third = entries
        if (first[3] != old_doc["relocatable_elf_sha256"]
                or second[3] != sdl_doc["relocatable_elf_sha256"]):
            raise ValueError("MAP02 import origin source manifest hash differs")
        original, original_weak = _unresolved(first)
        sdl, sdl_weak = _unresolved(second)
        linked, _ = _unresolved(third)
        if (original != old_doc["strong_symbols"]
                or original_weak != old_doc["weak_symbols"]
                or sdl != sdl_doc["strong_symbols"]
                or sdl_weak != sdl_doc["weak_symbols"]):
            raise ValueError("MAP02 import origin manifest ELF names differ")
        orig = set(original)
        after_sdl = set(sdl)
        after_x11 = set(linked)
        original_remaining_after_sdl = orig & after_sdl
        new_sdl = after_sdl - orig
        original_still_after_x11 = original_remaining_after_sdl & after_x11
        sdl_new_still_after_x11 = new_sdl & after_x11
        x11_new = after_x11 - after_sdl
        measured = (len(orig), len(after_sdl),
                    len(original_remaining_after_sdl), len(new_sdl))
        if measured != expected:
            raise ValueError("MAP02 import origin known SDL2 baseline mismatch")
        # Three buckets are disjoint and exhaust the X11-linked undefined set.
        final_count = (len(original_still_after_x11)
                       + len(sdl_new_still_after_x11) + len(x11_new))
        if final_count != len(after_x11):
            raise ValueError("MAP02 import origin partition arithmetic inconsistent")
        for entry in entries:
            _confirm_owned(entry)
        return {
            "schema": SCHEMA,
            "public_original_partial_sha256": first[3],
            "public_sdl2_partial_sha256": second[3],
            "public_x11_partial_sha256": third[3],
            "original_initial_imports": len(orig),
            "original_remaining_after_sdl2": len(original_remaining_after_sdl),
            "original_remaining_after_x11": len(original_still_after_x11),
            "original_imports_newly_resolved_by_x11":
                len(original_remaining_after_sdl - after_x11),
            "sdl2_new_imports": len(new_sdl),
            "sdl2_new_imports_remaining_after_x11":
                len(sdl_new_still_after_x11),
            "sdl2_new_imports_resolved_by_x11":
                len(new_sdl - after_x11),
            "x11_new_imports_after_link": len(x11_new),
            "final_strong_undefined_after_x11": len(after_x11),
            "all_undefined_imports_partitioned": True,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for entry in entries:
            os.close(entry[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_private_manifest", type=Path)
    parser.add_argument("original_partial_elf", type=Path)
    parser.add_argument("sdl2_private_manifest", type=Path)
    parser.add_argument("sdl2_partial_elf", type=Path)
    parser.add_argument("x11_partial_elf", type=Path)
    args = parser.parse_args()
    try:
        result = partition_x11_import_origin(
            args.original_private_manifest, args.original_partial_elf,
            args.sdl2_private_manifest, args.sdl2_partial_elf,
            args.x11_partial_elf)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 X11 symbol origin partition failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
