#!/usr/bin/env python3
"""Independently audit saved private MAP02 paired ld-r counts and both ELF files.

This does NOT reconstruct the original linker command or prove gameplay.
No original symbol names, owned game bytes or filesystem paths are printed.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_provider_coverage import read_private_manifest
from tools.check_map02_private_incremental_link import (
    OUTPUT, _check_abi, _confirm_owned, _open_owned, _unresolved,
)
from tools.check_map02_private_archive_strategy_compare import SCHEMA as REPORT_SCHEMA

VERIFY_SCHEMA = "vh.map02.private-archive-strategy-independent-verifier.v1"
COUNT_FIELDS = (
    "candidate_archive_count",
    "single_pass_original_imports_resolved",
    "grouped_original_imports_resolved",
    "single_pass_new_imports",
    "grouped_new_imports",
    "single_pass_final_strong_import_count",
    "grouped_final_strong_import_count",
    "group_minus_single_final_strong_imports",
)
SHA_FIELDS = (
    "source_partial_elf_sha256",
    "single_pass_partial_elf_sha256",
    "grouped_partial_elf_sha256",
)
BOOL_FIELDS = (
    "inputs_verified_unchanged_after_both_links",
    "outputs_verified_unchanged_after_both_links",
    "fully_linked_game_executable",
    "original_map02_execution_proven",
)
EXPECTED_KEYS = frozenset(("schema",) + COUNT_FIELDS + SHA_FIELDS + BOOL_FIELDS)


def _owner_private_directory(path):
    path = Path(path).absolute()
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("private MAP02 verification folder unavailable") from None
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("private MAP02 verification folder metadata unsafe")
    return path, (info.st_dev, info.st_ino, info.st_uid, info.st_mode)


def _verify_directory_identity(pinned):
    path, before = pinned
    try:
        info = path.lstat()
    except OSError:
        raise ValueError("private MAP02 verification folder changed") from None
    if (info.st_dev, info.st_ino, info.st_uid, info.st_mode) != before:
        raise ValueError("private MAP02 verification folder changed")


def _reject_duplicate_keys(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("private MAP02 report contains repeated JSON key")
        result[name] = value
    return result


def _read_private_report(entry):
    fd, _, info, _ = entry
    if not 0 < info[2] <= 16384:
        raise ValueError("private MAP02 report size invalid")
    payload = os.pread(fd, info[2] + 1, 0)
    if len(payload) != info[2]:
        raise ValueError("private MAP02 report changed while reading")
    try:
        doc = json.loads(payload.decode("utf-8"),
                         object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, ValueError):
        raise ValueError("private MAP02 report JSON invalid") from None
    if not isinstance(doc, dict) or set(doc) != EXPECTED_KEYS:
        raise ValueError("private MAP02 report fields invalid")
    if doc["schema"] != REPORT_SCHEMA:
        raise ValueError("private MAP02 report schema invalid")
    if (any(type(doc[name]) is not int or doc[name] < 0
            for name in COUNT_FIELDS if name != "group_minus_single_final_strong_imports")
            or type(doc["group_minus_single_final_strong_imports"]) is not int
            or not 2 <= doc["candidate_archive_count"] <= 64):
        raise ValueError("private MAP02 report count invalid")
    if (any(type(doc[name]) is not str or len(doc[name]) != 64
            or any(ch not in "0123456789abcdef" for ch in doc[name])
            for name in SHA_FIELDS)):
        raise ValueError("private MAP02 report hash invalid")
    if (doc["inputs_verified_unchanged_after_both_links"] is not True
            or doc["outputs_verified_unchanged_after_both_links"] is not True
            or doc["fully_linked_game_executable"] is not False
            or doc["original_map02_execution_proven"] is not False):
        raise ValueError("private MAP02 report evidence flags invalid")
    return doc


def verify_private_archive_comparison(manifest, partial, saved_report, output_root):
    """Independently recalculate strong-undefined counts from saved ET_REL outputs."""
    manifest_data = read_private_manifest(manifest)
    paths = [_owner_private_directory(Path(saved_report).absolute().parent),
             _owner_private_directory(output_root),
             _owner_private_directory(Path(output_root) / "single-pass"),
             _owner_private_directory(Path(output_root) / "grouped")]
    inputs = []
    try:
        for name in (saved_report, partial,
                     Path(output_root) / "single-pass" / OUTPUT,
                     Path(output_root) / "grouped" / OUTPUT):
            inputs.append(_open_owned(name, require_private=True))
        doc = _read_private_report(inputs[0])
        original = inputs[1]
        if (original[3] != doc["source_partial_elf_sha256"]
                or original[3] != manifest_data["relocatable_elf_sha256"]):
            raise ValueError("private MAP02 source ELF provenance mismatch")
        _check_abi(original)
        old_strong, old_weak = _unresolved(original)
        if (old_strong != manifest_data["strong_symbols"]
                or old_weak != manifest_data["weak_symbols"]):
            raise ValueError("private MAP02 source imports mismatch")
        initially_missing = set(old_strong)
        observed = []
        for entry, prefix in zip(inputs[2:], ("single_pass", "grouped")):
            _check_abi(entry)
            strong, _ = _unresolved(entry)
            now_missing = set(strong)
            if (doc[prefix + "_partial_elf_sha256"] != entry[3]
                    or doc[prefix + "_original_imports_resolved"] !=
                       len(initially_missing - now_missing)
                    or doc[prefix + "_new_imports"] !=
                       len(now_missing - initially_missing)
                    or doc[prefix + "_final_strong_import_count"] !=
                       len(now_missing)):
                raise ValueError("private MAP02 independent link evidence mismatch")
            observed.append(len(now_missing))
        if (doc["group_minus_single_final_strong_imports"] !=
                observed[1] - observed[0]):
            raise ValueError("private MAP02 paired delta inconsistent")
        for entry in inputs:
            _confirm_owned(entry)
        for pinned in paths:
            _verify_directory_identity(pinned)
        return {
            "schema": VERIFY_SCHEMA,
            "source_partial_elf_sha256": original[3],
            "candidate_archive_count": doc["candidate_archive_count"],
            "single_pass_remaining_strong_imports": observed[0],
            "grouped_remaining_strong_imports": observed[1],
            "verified_both_output_elf_files": True,
            "verified_report_arithmetic": True,
            "link_invocation_independently_attested": False,
            "fully_linked_game_executable": False,
            "original_map02_execution_proven": False,
        }
    finally:
        for entry in inputs:
            os.close(entry[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("owner_saved_report_json", type=Path)
    parser.add_argument("private_paired_output_directory", type=Path)
    args = parser.parse_args()
    try:
        result = verify_private_archive_comparison(
            args.private_undefined_manifest, args.private_original_partial_elf,
            args.owner_saved_report_json, args.private_paired_output_directory)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("private MAP02 independent archive comparison audit failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
