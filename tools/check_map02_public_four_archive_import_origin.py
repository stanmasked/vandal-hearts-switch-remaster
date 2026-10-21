#!/usr/bin/env python3
"""Attribute actual four-system-archive MAP02 imports to original PC vs SDL2.

Reread the original 520-import ELF, the SDL2 1085-import ELF and actual
four-group X11/XCB/Xau/Xdmcp ELF; publish counts and hashes only.
All imports remain owner-private; no retail game assets required.
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

SCHEMA = "vh.map02.public-original-sdl2-four-archive-import-origin.v1"


def partition_four_archive_origin(original_manifest, original_elf,
                                  after_sdl2_manifest, after_sdl2_elf,
                                  after_four_group_elf,
                                  *, expected_original=520,
                                  expected_sdl2=1085,
                                  expected_original_after_sdl2=493,
                                  expected_new_sdl2=592,
                                  expected_four_resolved=150,
                                  expected_four_new=48,
                                  expected_four_final=983):
    """Independently pin/check all original/SDL2/four-stage native ELF imports."""
    known = (
        expected_original, expected_sdl2, expected_original_after_sdl2,
        expected_new_sdl2, expected_four_resolved, expected_four_new,
        expected_four_final,
    )
    if any(type(n) is not int or n < 0 for n in known):
        raise ValueError("MAP02 four-origin expected import totals invalid")
    original_doc = read_private_manifest(original_manifest)
    sdl_doc = read_private_manifest(after_sdl2_manifest)
    opened = []
    try:
        for path in (original_elf, after_sdl2_elf, after_four_group_elf):
            if Path(path).suffix != ".o":
                raise ValueError("MAP02 four-origin inputs must be native .o")
            entry = _open_owned(path, require_private=True)
            opened.append(entry)
            _check_abi(entry)
        original, sdl, four = opened
        if len({(x[2][0], x[2][1]) for x in opened}) != 3:
            raise ValueError("MAP02 four-origin native objects alias")
        if (original[3] != original_doc["relocatable_elf_sha256"]
                or sdl[3] != sdl_doc["relocatable_elf_sha256"]):
            raise ValueError("MAP02 four-origin manifest ELF SHA differs")
        original_strong, original_weak = _unresolved(original)
        sdl_strong, sdl_weak = _unresolved(sdl)
        four_strong, _ = _unresolved(four)
        if (original_strong != original_doc["strong_symbols"]
                or original_weak != original_doc["weak_symbols"]
                or sdl_strong != sdl_doc["strong_symbols"]
                or sdl_weak != sdl_doc["weak_symbols"]):
            raise ValueError("MAP02 four-origin native ELF import manifest differs")
        original_names, sdl_names, four_names = (
            set(original_strong), set(sdl_strong), set(four_strong)
        )
        original_after_sdl = original_names & sdl_names
        introduced_by_sdl = sdl_names - original_names
        original_after_four = original_after_sdl & four_names
        sdl_after_four = introduced_by_sdl & four_names
        newly_introduced_by_four = four_names - sdl_names
        original_resolved_by_four = original_after_sdl - four_names
        sdl_resolved_by_four = introduced_by_sdl - four_names
        measured = (
            len(original_names), len(sdl_names), len(original_after_sdl),
            len(introduced_by_sdl),
            len(original_resolved_by_four) + len(sdl_resolved_by_four),
            len(newly_introduced_by_four), len(four_names),
        )
        if measured != known:
            raise ValueError("MAP02 four-origin actual GNU link counts differ")
        if (len(original_after_four) + len(sdl_after_four)
                + len(newly_introduced_by_four) != len(four_names)
                or len(original_after_four) + len(original_resolved_by_four)
                   != len(original_after_sdl)
                or len(sdl_after_four) + len(sdl_resolved_by_four)
                   != len(introduced_by_sdl)):
            raise ValueError("MAP02 four-origin buckets inconsistent")
        for entry in opened:
            _confirm_owned(entry)
        return {
            "schema": SCHEMA,
            "public_original_elf_sha256": original[3],
            "public_after_sdl2_elf_sha256": sdl[3],
            "public_four_group_elf_sha256": four[3],
            "initial_original_strong": len(original_names),
            "original_strong_still_after_sdl2": len(original_after_sdl),
            "sdl2_new_strong_imports": len(introduced_by_sdl),
            "sdl2_stage_strong_total": len(sdl_names),
            "original_pc_strong_resolved_by_four_archives":
                len(original_resolved_by_four),
            "original_pc_strong_still_after_four_archives":
                len(original_after_four),
            "sdl2_introduced_strong_resolved_by_four_archives":
                len(sdl_resolved_by_four),
            "sdl2_introduced_strong_still_after_four_archives":
                len(sdl_after_four),
            "four_archives_new_strong_imports":
                len(newly_introduced_by_four),
            "four_archives_final_strong_total": len(four_names),
            "every_surviving_import_accounted_for": True,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for entry in opened:
            os.close(entry[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_private_undefined_manifest", type=Path)
    parser.add_argument("original_private_et_rel", type=Path)
    parser.add_argument("after_sdl2_private_undefined_manifest", type=Path)
    parser.add_argument("after_sdl2_private_et_rel", type=Path)
    parser.add_argument("after_four_archives_private_et_rel", type=Path)
    args = parser.parse_args()
    try:
        output = partition_four_archive_origin(
            args.original_private_undefined_manifest,
            args.original_private_et_rel,
            args.after_sdl2_private_undefined_manifest,
            args.after_sdl2_private_et_rel,
            args.after_four_archives_private_et_rel,
        )
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("MAP02 four-archive original-PC import origin audit failed")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
