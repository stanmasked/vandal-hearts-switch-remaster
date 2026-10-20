#!/usr/bin/env python3
"""Run and independently verify both private GNU ld-r strategies in one command.

Only aggregate numbers are printed. Retail inputs and raw symbol names stay
inside the owner's Linux machine and are never uploaded by this utility.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)
from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _private_output_dir, _unresolved,
)
from tools.check_map02_private_archive_strategy_compare import (
    compare_private_archive_strategies, write_private_archive_receipt,
)
from tools.verify_map02_private_archive_comparison import (
    verify_private_archive_comparison,
)

SCHEMA = "vh.map02.private-one-shot-link-gap-audit.v1"
REPORT = "paired.private.json"


@contextmanager
def _pin_private_link_gap_inputs(manifest, partial, candidates):
    """Pin each input through provider inspection, linking and verification."""
    entries = []
    known_inodes = set()
    try:
        for path, owner_private in [(manifest, True), (partial, True),
                                    *((candidate, False)
                                      for candidate in candidates)]:
            entry = _open_owned(path, require_private=owner_private)
            entries.append(entry)
            inode = entry[2][:2]
            if inode in known_inodes:
                raise ValueError("private MAP02 audit input inode repeated")
            known_inodes.add(inode)
        yield entries
    finally:
        for entry in entries:
            os.close(entry[0])


def _confirm_private_link_gap_inputs(entries):
    """Reject changed content, altered metadata or changed path identities."""
    for entry in entries:
        _confirm_owned(entry)


def run_private_link_gap_audit(manifest, partial, archives, output_root,
                               *, expected_initial_strong_imports=None,
                               audit_strong_providers=False):
    """Create sealed original-link comparison and recheck saved ELF evidence."""
    # Fail without side effects if there is no actionable provider set.
    candidates = [Path(value) for value in archives]
    archive_count = sum(item.suffix == ".a" for item in candidates)
    if (not 2 <= len(candidates) <= 64 or archive_count < 2
            or any(item.suffix not in (".o", ".a") for item in candidates)):
        raise ValueError(
            "private MAP02 link gap audit requires 2..64 inputs and two archives")
    with _pin_private_link_gap_inputs(manifest, partial, candidates) as entries:
        original = read_private_manifest(manifest)
        if entries[1][3] != original["relocatable_elf_sha256"]:
            raise ValueError("private MAP02 initial source digest mismatch")
        # Validate *all* pinned native inputs before creating even a
        # diagnostic output directory. Optional export coverage alone is
        # not sufficient, and is not enabled by default.
        for entry in entries[1:]:
            _check_abi(entry)
        source_strong, source_weak = _unresolved(entries[1])
        if (source_strong != original["strong_symbols"]
                or source_weak != original["weak_symbols"]):
            raise ValueError("private MAP02 initial source imports differ")
        _confirm_private_link_gap_inputs(entries)
        initial_count = len(original["strong_symbols"])
        if expected_initial_strong_imports is not None and (
                type(expected_initial_strong_imports) is not int
                or expected_initial_strong_imports < 0
                or initial_count != expected_initial_strong_imports):
            raise ValueError("private MAP02 expected original strong import count differs")
        provider_coverage = None
        if audit_strong_providers:
            # Aggregate symbol presence is not equivalent to successful GNU
            # archive-member extraction. Inspect BEFORE creating outputs.
            provider_coverage = audit_provider_coverage(manifest, candidates)
            if (provider_coverage["relocatable_elf_sha256"] !=
                    original["relocatable_elf_sha256"]
                    or provider_coverage["original_strong_unresolved_count"] !=
                       initial_count
                    or provider_coverage["candidate_provider_file_count"] !=
                       len(candidates)
                    or provider_coverage["strong_symbols_with_candidate_provider"]
                       + provider_coverage["strong_symbols_without_candidate_provider"]
                       != initial_count):
                raise ValueError("private MAP02 candidate provider coverage inconsistent")
        _confirm_private_link_gap_inputs(entries)
        parent, parent_identity = _private_output_dir(output_root)
        child = parent / "linked"
        receipt_dir = parent / "receipts"
        receipt_dir.mkdir(mode=0o700)
        info = receipt_dir.lstat()
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise ValueError("private MAP02 receipt directory unsafe")
        report = compare_private_archive_strategies(
            manifest, partial, candidates, child)
        _confirm_private_link_gap_inputs(entries)
        receipt = receipt_dir / REPORT
        write_private_archive_receipt(report, receipt)
        independently_verified = verify_private_archive_comparison(
            manifest, partial, receipt, child)
        _confirm_private_link_gap_inputs(entries)
        root_info = parent.lstat()
        if (root_info.st_dev, root_info.st_ino, root_info.st_uid,
                stat.S_IMODE(root_info.st_mode)) != parent_identity:
            raise ValueError("private MAP02 output root changed during audit")
        if (independently_verified["source_partial_elf_sha256"] !=
                original["relocatable_elf_sha256"]
                or independently_verified["candidate_archive_count"] !=
                   archive_count
                or independently_verified["single_pass_remaining_strong_imports"] !=
                   report["single_pass_final_strong_import_count"]
                or independently_verified["grouped_remaining_strong_imports"] !=
                   report["grouped_final_strong_import_count"]
                or independently_verified["verified_both_output_elf_files"] is not True
                or independently_verified["verified_report_arithmetic"] is not True):
            raise ValueError("private MAP02 final independent verification inconsistent")
        for prefix in ("single_pass", "grouped"):
            resolved = report[prefix + "_original_imports_resolved"]
            newly_introduced = report[prefix + "_new_imports"]
            total_unresolved = independently_verified[
                prefix + "_remaining_strong_imports"]
            if (type(resolved) is not int or type(newly_introduced) is not int
                    or not 0 <= resolved <= initial_count
                    or newly_introduced < 0
                    or total_unresolved != initial_count - resolved + newly_introduced):
                raise ValueError("private MAP02 import gap decomposition inconsistent")
        _confirm_private_link_gap_inputs(entries)
        return {
            "schema": SCHEMA,
            "initial_strong_import_count": initial_count,
            "candidate_archive_count": archive_count,
            "candidate_direct_object_count": len(candidates) - archive_count,
            "candidate_strong_provider_coverage_checked":
                provider_coverage is not None,
            "initial_imports_with_strong_provider_candidate": (
                provider_coverage["strong_symbols_with_candidate_provider"]
                if provider_coverage is not None else None),
            "initial_imports_without_strong_provider_candidate": (
                provider_coverage["strong_symbols_without_candidate_provider"]
                if provider_coverage is not None else None),
            "initial_imports_with_multiple_strong_provider_candidates": (
                provider_coverage["strong_symbols_with_multiple_candidates"]
                if provider_coverage is not None else None),
            "provider_presence_proves_actual_link_resolution": False,
            "group_strategy_reorders_direct_objects_before_archives":
                archive_count != len(candidates),
            "expected_initial_import_count_confirmed":
                expected_initial_strong_imports is not None,
            "single_pass_original_imports_resolved":
                report["single_pass_original_imports_resolved"],
            "grouped_original_imports_resolved":
                report["grouped_original_imports_resolved"],
            "single_pass_original_imports_remaining":
                initial_count - report["single_pass_original_imports_resolved"],
            "grouped_original_imports_remaining":
                initial_count - report["grouped_original_imports_resolved"],
            "single_pass_new_strong_imports":
                report["single_pass_new_imports"],
            "grouped_new_strong_imports":
                report["grouped_new_imports"],
            "single_pass_final_strong_import_count":
                independently_verified["single_pass_remaining_strong_imports"],
            "grouped_final_strong_import_count":
                independently_verified["grouped_remaining_strong_imports"],
            "group_minus_single_final_strong_imports":
                report["group_minus_single_final_strong_imports"],
            "owner_only_saved_report": True,
            "inputs_verified_unchanged_across_all_audit_stages": True,
            "independent_elf_and_count_audit_passed": True,
            "fully_linked_game_executable": False,
            "original_map02_execution_proven": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("new_private_output_root", type=Path)
    parser.add_argument("native_candidate", type=Path, nargs="+")
    parser.add_argument(
        "--audit-strong-provider-coverage", action="store_true",
        help="check aggregate strong provider presence before creating output")
    parser.add_argument(
        "--expect-initial-strong-imports", type=int, default=None,
        help="fail before creating output if the original strong-import count differs")
    args = parser.parse_args()
    try:
        summary = run_private_link_gap_audit(
            args.private_undefined_manifest, args.private_original_partial_elf,
            args.native_candidate, args.new_private_output_root,
            expected_initial_strong_imports=args.expect_initial_strong_imports,
            audit_strong_providers=args.audit_strong_provider_coverage)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("private MAP02 one-shot link gap audit failed")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
