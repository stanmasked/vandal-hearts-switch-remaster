#!/usr/bin/env python3
"""Reread original and linked asset-free MAP02 ELF evidence, without publishing names.

This verifies a saved aggregate JSON report against actual pinned ELF files and
an explicitly identified static candidate archive. It does not prove that GNU
ld used this archive, a package provenance, or any retail gameplay.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_public_sdl2_archive_witness import SCHEMA as REPORT_SCHEMA
from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)
from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _unresolved,
)

SCHEMA = "vh.map02.public-sdl2-saved-elf-recount.v1"
MAX_REPORT_BYTES = 16384

COUNT_KEYS = (
    "initial_strong_undefined",
    "sdl2_candidate_strong_exports_matching_initial",
    "initial_without_sdl2_candidate_export",
    "original_imports_resolved_by_actual_ld_r",
    "original_imports_still_unresolved",
    "new_undefined_imports_introduced_by_sdl2",
    "final_undefined_strong_count",
)
HASH_KEYS = (
    "public_source_elf_sha256",
    "linked_partial_elf_sha256",
    "sdl2_candidate_archive_sha256",
)
TRUE_KEYS = ("ordinary_native_static_archive_tested",
             "asset_free_public_pc_code_only")
FALSE_KEYS = (
    "system_archive_package_origin_independently_attested",
    "fully_linked_game_executable",
    "original_map02_execution_proven",
)
EXPECTED_KEYS = frozenset(("schema",) + COUNT_KEYS + HASH_KEYS +
                          TRUE_KEYS + FALSE_KEYS)


def _read_aggregate(path):
    """Bounded symlink-proof read; this JSON is numbers/hashes only."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("MAP02 saved aggregate unavailable") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= MAX_REPORT_BYTES):
            raise ValueError("MAP02 saved aggregate metadata unsafe")
        payload = os.pread(fd, info.st_size + 1, 0)
        if len(payload) != info.st_size:
            raise ValueError("MAP02 saved aggregate read incomplete")
    finally:
        os.close(fd)
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError("MAP02 saved aggregate JSON invalid") from None
    if (not isinstance(obj, dict) or set(obj) != EXPECTED_KEYS
            or obj["schema"] != REPORT_SCHEMA):
        raise ValueError("MAP02 saved aggregate schema invalid")
    if any(type(obj[k]) is not int or obj[k] < 0 for k in COUNT_KEYS):
        raise ValueError("MAP02 saved aggregate counts invalid")
    if any(not isinstance(obj[k], str) or len(obj[k]) != 64 or
           any(ch not in "0123456789abcdef" for ch in obj[k])
           for k in HASH_KEYS):
        raise ValueError("MAP02 saved aggregate hashes invalid")
    if (any(obj[k] is not True for k in TRUE_KEYS)
            or any(obj[k] is not False for k in FALSE_KEYS)):
        raise ValueError("MAP02 saved aggregate evidence claims invalid")
    return obj


def verify_saved_sdl2_recount(manifest, original_partial, copied_archive,
                              linked_partial, saved_aggregate):
    """Re-read both ET_REL files, archive export coverage and saved totals."""
    doc = read_private_manifest(manifest)
    report = _read_aggregate(saved_aggregate)
    entries = []
    try:
        for path in (original_partial, copied_archive, linked_partial):
            entry = _open_owned(path, require_private=True)
            entries.append(entry)
            _check_abi(entry)
        source, archive, linked = entries
        if (source[3] != doc["relocatable_elf_sha256"]
                or report["public_source_elf_sha256"] != source[3]
                or report["linked_partial_elf_sha256"] != linked[3]
                or report["sdl2_candidate_archive_sha256"] != archive[3]):
            raise ValueError("MAP02 saved SDL2 ELF/archive identity mismatch")
        if not Path(copied_archive).name.endswith(".a"):
            raise ValueError("MAP02 saved candidate is not a static archive")
        original_strong, original_weak = _unresolved(source)
        linked_strong, _ = _unresolved(linked)
        if (original_strong != doc["strong_symbols"]
                or original_weak != doc["weak_symbols"]):
            raise ValueError("MAP02 saved source import manifest mismatch")
        original_names = set(original_strong)
        linked_names = set(linked_strong)
        coverage = audit_provider_coverage(manifest, [copied_archive])
        counted = {
            "initial_strong_undefined": len(original_names),
            "sdl2_candidate_strong_exports_matching_initial":
                coverage["strong_symbols_with_candidate_provider"],
            "initial_without_sdl2_candidate_export":
                coverage["strong_symbols_without_candidate_provider"],
            "original_imports_resolved_by_actual_ld_r":
                len(original_names - linked_names),
            "original_imports_still_unresolved":
                len(original_names & linked_names),
            "new_undefined_imports_introduced_by_sdl2":
                len(linked_names - original_names),
            "final_undefined_strong_count": len(linked_names),
        }
        if (any(counted[k] != report[k] for k in COUNT_KEYS)
                or report["initial_strong_undefined"] != 520
                or coverage["candidate_provider_file_count"] != 1):
            raise ValueError("MAP02 saved SDL2 import recount differs")
        for entry in entries:
            _confirm_owned(entry)
        return {
            "schema": SCHEMA,
            "baseline_strong_imports": counted["initial_strong_undefined"],
            "candidate_strong_export_matches":
                counted["sdl2_candidate_strong_exports_matching_initial"],
            "original_imports_resolved":
                counted["original_imports_resolved_by_actual_ld_r"],
            "new_imports": counted["new_undefined_imports_introduced_by_sdl2"],
            "final_strong_imports": counted["final_undefined_strong_count"],
            "saved_report_recount_verified": True,
            "copied_candidate_archive_identity_verified": True,
            "source_and_linked_elf_identity_verified": True,
            "full_game_executable_proven": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for entry in entries:
            os.close(entry[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_original_import_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("private_copied_system_archive", type=Path)
    parser.add_argument("private_linked_partial_elf", type=Path)
    parser.add_argument("saved_aggregate_json", type=Path)
    args = parser.parse_args()
    try:
        report = verify_saved_sdl2_recount(
            args.private_original_import_manifest,
            args.private_original_partial_elf,
            args.private_copied_system_archive,
            args.private_linked_partial_elf,
            args.saved_aggregate_json)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("MAP02 saved SDL2 evidence recount failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
