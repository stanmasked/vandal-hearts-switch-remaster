#!/usr/bin/env python3
"""Replay actual Ubuntu X11.a against SDL2-linked public MAP02 ELF byte-for-byte.

Reread only saved private native inputs and a numeric witness. No original
symbol names, retail bytes, filesystem paths or subprocess diagnostics logged.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _unresolved,
    probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)
from tools.check_map02_public_x11_after_sdl2 import SCHEMA as X11_SCHEMA

SCHEMA = "vh.map02.public-after-sdl2-x11-byte-replay.v1"
COUNT_KEYS = (
    "initial_after_sdl2_undefined",
    "x11_strong_export_matches",
    "initial_imports_without_x11_candidate",
    "original_after_sdl2_imports_resolved",
    "original_after_sdl2_imports_remaining",
    "new_imports_introduced_by_x11",
    "final_strong_undefined_after_x11",
)
HASH_KEYS = (
    "input_sdl2_partial_sha256",
    "copied_x11_archive_sha256",
    "output_x11_partial_sha256",
)
TRUE_KEYS = ("ordinary_native_static_archive_tested",)
FALSE_KEYS = (
    "system_package_origin_independently_attested",
    "retail_assets_linked",
    "fully_linked_game_executable",
    "authentic_map02_execution_proven",
)
REPORT_KEYS = frozenset(("schema",) + COUNT_KEYS + HASH_KEYS +
                        TRUE_KEYS + FALSE_KEYS)


def _read_x11_aggregate(path):
    """No symlink/oversize/changed read and no raw path in errors."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("MAP02 X11 witness report inaccessible") from None
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid() or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) & 0o022
                or not 0 < before.st_size <= 16384):
            raise ValueError("MAP02 X11 witness report unsafe")
        payload = os.pread(fd, before.st_size + 1, 0)
        after = os.fstat(fd)
        if (len(payload) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns) !=
                   (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("MAP02 X11 witness changed during read")
    finally:
        os.close(fd)
    try:
        report = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError("MAP02 X11 witness JSON invalid") from None
    if (not isinstance(report, dict)
            or set(report) != REPORT_KEYS
            or report["schema"] != X11_SCHEMA
            or any(type(report[k]) is not int or report[k] < 0
                   for k in COUNT_KEYS)
            or any(type(report[k]) is not str or len(report[k]) != 64
                   or any(ch not in "0123456789abcdef" for ch in report[k])
                   for k in HASH_KEYS)
            or any(report[k] is not True for k in TRUE_KEYS)
            or any(report[k] is not False for k in FALSE_KEYS)):
        raise ValueError("MAP02 X11 witness report schema invalid")
    return report


def verify_x11_native_replay(private_sdl2_manifest, sdl2_elf, copied_x11_archive,
                             saved_x11_elf, saved_x11_aggregate,
                             replay_output_dir, *,
                             expected_sdl2_strong=1085,
                             expected_final_strong=996):
    """Require identical strong-import sets and byte-identical fresh GNU ld-r."""
    if any(type(x) is not int or x < 0 for x in
           (expected_sdl2_strong, expected_final_strong)):
        raise ValueError("MAP02 X11 expected import totals invalid")
    report = _read_x11_aggregate(saved_x11_aggregate)
    manifest = read_private_manifest(private_sdl2_manifest)
    entries = []
    try:
        for path in (sdl2_elf, copied_x11_archive, saved_x11_elf):
            item = _open_owned(path, require_private=True)
            entries.append(item)
            _check_abi(item)
        original, archive, linked = entries
        if (Path(sdl2_elf).suffix != ".o"
                or Path(copied_x11_archive).suffix != ".a"
                or Path(saved_x11_elf).suffix != ".o"
                or len({(x[2][0], x[2][1]) for x in entries}) != 3):
            raise ValueError("MAP02 X11 replay input identity invalid")
        if (original[3] != manifest["relocatable_elf_sha256"]
                or original[3] != report["input_sdl2_partial_sha256"]
                or archive[3] != report["copied_x11_archive_sha256"]
                or linked[3] != report["output_x11_partial_sha256"]):
            raise ValueError("MAP02 X11 saved source/archive/linked hashes differ")
        before_strong, before_weak = _unresolved(original)
        after_strong, _ = _unresolved(linked)
        if (before_strong != manifest["strong_symbols"]
                or before_weak != manifest["weak_symbols"]):
            raise ValueError("MAP02 X11 source import manifest differs")
        before = set(before_strong)
        after = set(after_strong)
        coverage = audit_provider_coverage(private_sdl2_manifest,
                                           [copied_x11_archive])
        if (report["initial_after_sdl2_undefined"] != expected_sdl2_strong
                or len(before) != expected_sdl2_strong
                or report["final_strong_undefined_after_x11"] !=
                   expected_final_strong
                or len(after) != expected_final_strong
                or report["x11_strong_export_matches"] !=
                   coverage["strong_symbols_with_candidate_provider"]
                or report["initial_imports_without_x11_candidate"] !=
                   coverage["strong_symbols_without_candidate_provider"]
                or coverage["candidate_provider_file_count"] != 1
                or report["original_after_sdl2_imports_resolved"] !=
                   len(before - after)
                or report["original_after_sdl2_imports_remaining"] !=
                   len(before & after)
                or report["new_imports_introduced_by_x11"] !=
                   len(after - before)):
            raise ValueError("MAP02 X11 saved report native import recount differs")
        for item in entries:
            _confirm_owned(item)
        # Two real native GNU ld -r executions, with exactly the SAME archive.
        # The replay destination must not exist and has its own 0700 dir.
        again = probe_private_incremental_link(
            private_sdl2_manifest, sdl2_elf, [copied_x11_archive],
            replay_output_dir,
            expected_initial_strong_imports=expected_sdl2_strong)
        if (again["source_partial_elf_sha256"] != original[3]
                or again["linked_candidate_elf_sha256"] != linked[3]
                or again["candidate_count"] != 1
                or again["candidate_archive_count"] != 1
                or again["archive_selection_strategy"] !=
                   "single_pass_user_order"
                or again["original_strong_imports_resolved_by_ld_r"] !=
                   report["original_after_sdl2_imports_resolved"]
                or again["original_strong_imports_remaining_after_ld_r"] !=
                   report["original_after_sdl2_imports_remaining"]
                or again["new_strong_imports_introduced_by_candidates"] !=
                   report["new_imports_introduced_by_x11"]
                or again["final_strong_import_count"] !=
                   expected_final_strong):
            raise ValueError("MAP02 X11 independent GNU relink differs")
        for item in entries:
            _confirm_owned(item)
        return {
            "schema": SCHEMA,
            "input_sdl2_partial_sha256": original[3],
            "x11_static_archive_sha256": archive[3],
            "identical_output_partial_sha256": linked[3],
            "sdl2_stage_initial_strong_undefined": len(before),
            "x11_resolved_original_stage_imports": len(before - after),
            "x11_new_imports": len(after - before),
            "final_strong_undefined": len(after),
            "saved_x11_recount_verified": True,
            "independent_native_x11_relink_executed": True,
            "byte_identical_x11_relink_verified": True,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for item in entries:
            os.close(item[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdl2_stage_private_manifest", type=Path)
    parser.add_argument("private_sdl2_stage_elf", type=Path)
    parser.add_argument("private_copied_x11_archive", type=Path)
    parser.add_argument("private_x11_stage_elf", type=Path)
    parser.add_argument("saved_x11_numeric_aggregate", type=Path)
    parser.add_argument("new_private_replay_dir", type=Path)
    args = parser.parse_args()
    try:
        result = verify_x11_native_replay(
            args.sdl2_stage_private_manifest,
            args.private_sdl2_stage_elf,
            args.private_copied_x11_archive,
            args.private_x11_stage_elf,
            args.saved_x11_numeric_aggregate,
            args.new_private_replay_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 independent X11 ELF byte replay failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
