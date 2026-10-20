#!/usr/bin/env python3
"""Audit a real single-pass GNU ld -r with one or more private .o/.a inputs.

This mode deliberately does NOT claim archive group rescanning or a final game
executable. Original symbol names, file paths and game bytes stay local.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)
from tools.check_map02_private_incremental_link import (
    OUTPUT, _check_abi, _confirm_owned, _open_owned, _unresolved,
    probe_private_incremental_link,
)
from tools.run_map02_private_link_gap_audit import (
    _confirm_private_link_gap_inputs, _pin_private_link_gap_inputs,
)

SCHEMA = "vh.map02.private-single-pass-gap-audit.v1"


def audit_private_single_pass_gap(manifest, partial, candidates, output_dir,
                                  *, expected_initial_strong_imports=None,
                                  audit_strong_providers=False):
    """Return aggregate counts after independently recounting a genuine ELF."""
    candidates = [Path(item) for item in candidates]
    if (not 1 <= len(candidates) <= 64
            or any(path.suffix not in (".o", ".a") for path in candidates)):
        raise ValueError("private MAP02 single-pass audit requires 1..64 .o/.a files")
    archive_count = sum(item.suffix == ".a" for item in candidates)
    with _pin_private_link_gap_inputs(manifest, partial, candidates) as inputs:
        original = read_private_manifest(manifest)
        if inputs[1][3] != original["relocatable_elf_sha256"]:
            raise ValueError("private MAP02 source ELF digest mismatches manifest")
        _confirm_private_link_gap_inputs(inputs)
        initial = set(original["strong_symbols"])
        if expected_initial_strong_imports is not None and (
                type(expected_initial_strong_imports) is not int
                or expected_initial_strong_imports < 0
                or expected_initial_strong_imports != len(initial)):
            raise ValueError("private MAP02 expected single-pass import count differs")

        coverage = None
        if audit_strong_providers:
            coverage = audit_provider_coverage(manifest, candidates)
            if (coverage["relocatable_elf_sha256"] != inputs[1][3]
                    or coverage["original_strong_unresolved_count"] != len(initial)
                    or coverage["candidate_provider_file_count"] != len(candidates)
                    or (coverage["strong_symbols_with_candidate_provider"]
                        + coverage["strong_symbols_without_candidate_provider"])
                    != len(initial)):
                raise ValueError("private MAP02 single-pass coverage inconsistent")
        _confirm_private_link_gap_inputs(inputs)

        report = probe_private_incremental_link(
            manifest, partial, candidates, output_dir, group_archives=False)
        _confirm_private_link_gap_inputs(inputs)

        output_dir = Path(output_dir).absolute()
        folder = output_dir.lstat()
        if (not stat.S_ISDIR(folder.st_mode)
                or folder.st_uid != os.geteuid()
                or stat.S_IMODE(folder.st_mode) != 0o700):
            raise ValueError("private MAP02 single-pass output folder unsafe")
        linked = _open_owned(output_dir / OUTPUT, require_private=True)
        try:
            _check_abi(linked)
            after_strong, after_weak = _unresolved(linked)
            after = set(after_strong)
            newly_introduced = after - initial
            old_remaining = initial & after
            resolved = initial - after
            if (report["archive_selection_strategy"] != "single_pass_user_order"
                    or report["source_partial_elf_sha256"] != inputs[1][3]
                    or report["linked_candidate_elf_sha256"] != linked[3]
                    or report["candidate_count"] != len(candidates)
                    or report["candidate_archive_count"] != archive_count
                    or report["original_strong_import_count"] != len(initial)
                    or report["original_strong_imports_resolved_by_ld_r"] != len(resolved)
                    or report["original_strong_imports_remaining_after_ld_r"] != len(old_remaining)
                    or report["new_strong_imports_introduced_by_candidates"] != len(newly_introduced)
                    or report["final_strong_import_count"] != len(after)
                    or report["final_weak_import_count"] != len(after_weak)
                    or len(old_remaining) + len(newly_introduced) != len(after)):
                raise ValueError("private MAP02 single-pass independent ELF audit differs")
            _confirm_owned(linked)
            _confirm_private_link_gap_inputs(inputs)
            current = output_dir.lstat()
            if (current.st_dev, current.st_ino, current.st_uid,
                    current.st_mode) != (
                    folder.st_dev, folder.st_ino, folder.st_uid,
                    folder.st_mode):
                raise ValueError("private MAP02 single-pass folder replaced")
            return {
                "schema": SCHEMA,
                "initial_strong_import_count": len(initial),
                "candidate_count": len(candidates),
                "candidate_archive_count": archive_count,
                "candidate_direct_object_count": len(candidates) - archive_count,
                "expected_initial_import_count_confirmed":
                    expected_initial_strong_imports is not None,
                "candidate_strong_provider_coverage_checked": coverage is not None,
                "initial_imports_without_strong_provider_candidate": (
                    coverage["strong_symbols_without_candidate_provider"]
                    if coverage is not None else None),
                "initial_imports_with_strong_provider_candidate": (
                    coverage["strong_symbols_with_candidate_provider"]
                    if coverage is not None else None),
                "provider_presence_proves_actual_link_resolution": False,
                "original_strong_imports_resolved": len(resolved),
                "original_strong_imports_remaining": len(old_remaining),
                "new_strong_imports_introduced": len(newly_introduced),
                "final_strong_import_count": len(after),
                "final_weak_import_count": len(after_weak),
                "source_partial_elf_sha256": inputs[1][3],
                "linked_partial_elf_sha256": linked[3],
                "independent_single_output_elf_recount_passed": True,
                "inputs_verified_unchanged_across_audit_stages": True,
                "grouped_archive_rescan_performed": False,
                "fully_linked_game_executable": False,
                "original_map02_execution_proven": False,
            }
        finally:
            os.close(linked[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("new_private_output_dir", type=Path)
    parser.add_argument("native_candidate", type=Path, nargs="+")
    parser.add_argument(
        "--expect-initial-strong-imports", type=int, default=None,
        help="require the expected source import count before any output")
    parser.add_argument(
        "--audit-strong-provider-coverage", action="store_true",
        help="check candidate strong export presence before actual linking")
    args = parser.parse_args()
    try:
        result = audit_private_single_pass_gap(
            args.private_undefined_manifest, args.private_original_partial_elf,
            args.native_candidate, args.new_private_output_dir,
            expected_initial_strong_imports=args.expect_initial_strong_imports,
            audit_strong_providers=args.audit_strong_provider_coverage)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("private MAP02 single-pass link gap audit failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
