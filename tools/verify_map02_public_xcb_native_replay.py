#!/usr/bin/env python3
"""Independent native GNU ld-r replay for the actual after-X11 libxcb.a stage.

Read the pinned owner-private saved ELF + system archive and re-run the *same*
partial link in a fresh 0700 directory. Publish aggregates and SHA-256 only.
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
from tools.check_map02_public_xcb_after_x11 import SCHEMA as XCB_SCHEMA

SCHEMA = "vh.map02.public-after-x11-xcb-native-byte-replay.v1"
NUMBER_FIELDS = (
    "initial_after_x11_strong_undefined",
    "xcb_strong_export_matches",
    "input_symbols_without_xcb_strong_export",
    "original_after_x11_imports_resolved",
    "original_after_x11_imports_remaining",
    "new_imports_introduced_by_xcb",
    "final_strong_undefined_after_xcb",
)
SHA_FIELDS = (
    "input_x11_partial_sha256", "copied_xcb_archive_sha256",
    "output_xcb_partial_sha256",
)
YES_FIELDS = ("ordinary_native_static_archive_tested",)
NO_FIELDS = (
    "system_archive_package_origin_independently_attested",
    "retail_assets_linked", "fully_linked_game_executable",
    "authentic_map02_execution_proven",
)
KNOWN_KEYS = frozenset(("schema",) + NUMBER_FIELDS + SHA_FIELDS +
                       YES_FIELDS + NO_FIELDS)


def _read_numeric_xcb_witness(path):
    """Read numeric-only JSON via owned, non-symlink, stable file descriptor."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("MAP02 XCB saved aggregate inaccessible") from None
    try:
        a = os.fstat(fd)
        if (not stat.S_ISREG(a.st_mode) or a.st_uid != os.geteuid()
                or a.st_nlink != 1 or stat.S_IMODE(a.st_mode) & 0o022
                or not 0 < a.st_size <= 16384):
            raise ValueError("MAP02 XCB aggregate file metadata unsafe")
        blob = os.pread(fd, a.st_size + 1, 0)
        b = os.fstat(fd)
        if (len(blob) != a.st_size
                or (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns)
                != (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns)):
            raise ValueError("MAP02 XCB aggregate changed during read")
    finally:
        os.close(fd)
    try:
        report = json.loads(blob)
    except (ValueError, UnicodeError):
        raise ValueError("MAP02 XCB aggregate malformed") from None
    if (not isinstance(report, dict) or set(report) != KNOWN_KEYS
            or report["schema"] != XCB_SCHEMA
            or any(type(report[k]) is not int or report[k] < 0
                   for k in NUMBER_FIELDS)
            or any(type(report[k]) is not str or len(report[k]) != 64
                   or any(c not in "0123456789abcdef" for c in report[k])
                   for k in SHA_FIELDS)
            or any(report[k] is not True for k in YES_FIELDS)
            or any(report[k] is not False for k in NO_FIELDS)):
        raise ValueError("MAP02 XCB aggregate invalid schema or claims")
    return report


def verify_xcb_relink(private_after_x11_manifest, after_x11_elf,
                      copied_xcb_archive, saved_xcb_elf,
                      saved_numeric_xcb_report, replay_output_dir,
                      *, expected_x11_strong=996):
    """Check real original/provider/output and byte-identical second GNU ld-r."""
    if type(expected_x11_strong) is not int or expected_x11_strong < 0:
        raise ValueError("MAP02 XCB replay expected baseline invalid")
    saved = _read_numeric_xcb_witness(saved_numeric_xcb_report)
    original_doc = read_private_manifest(private_after_x11_manifest)
    opened = []
    try:
        for file in (after_x11_elf, copied_xcb_archive, saved_xcb_elf):
            f = _open_owned(file, require_private=True)
            opened.append(f)
            _check_abi(f)
        source, archive, first_link = opened
        if (Path(after_x11_elf).suffix != ".o"
                or Path(copied_xcb_archive).suffix != ".a"
                or Path(saved_xcb_elf).suffix != ".o"
                or len({(f[2][0], f[2][1]) for f in opened}) != 3):
            raise ValueError("MAP02 XCB replay native inputs invalid")
        if (source[3] != original_doc["relocatable_elf_sha256"]
                or source[3] != saved["input_x11_partial_sha256"]
                or archive[3] != saved["copied_xcb_archive_sha256"]
                or first_link[3] != saved["output_xcb_partial_sha256"]):
            raise ValueError("MAP02 XCB source/archive/ELF hash mismatch")
        strong, weak = _unresolved(source)
        after_strong, _ = _unresolved(first_link)
        if (strong != original_doc["strong_symbols"]
                or weak != original_doc["weak_symbols"]):
            raise ValueError("MAP02 XCB private manifest disagrees with ELF")
        original_names, new_names = set(strong), set(after_strong)
        covers = audit_provider_coverage(private_after_x11_manifest,
                                         [copied_xcb_archive])
        if (len(original_names) != expected_x11_strong
                or saved["initial_after_x11_strong_undefined"] !=
                   expected_x11_strong
                or saved["xcb_strong_export_matches"] !=
                   covers["strong_symbols_with_candidate_provider"]
                or saved["input_symbols_without_xcb_strong_export"] !=
                   covers["strong_symbols_without_candidate_provider"]
                or covers["candidate_provider_file_count"] != 1
                or saved["original_after_x11_imports_resolved"] !=
                   len(original_names - new_names)
                or saved["original_after_x11_imports_remaining"] !=
                   len(original_names & new_names)
                or saved["new_imports_introduced_by_xcb"] !=
                   len(new_names - original_names)
                or saved["final_strong_undefined_after_xcb"] !=
                   len(new_names)):
            raise ValueError("MAP02 XCB saved native link report recount mismatch")
        for f in opened:
            _confirm_owned(f)
        # Output folder must be new; strict linker creates its own 0700,
        # preserving the exact input ELF and copied system archive descriptors.
        replay = probe_private_incremental_link(
            private_after_x11_manifest, after_x11_elf, [copied_xcb_archive],
            replay_output_dir, expected_initial_strong_imports=expected_x11_strong)
        if (replay["source_partial_elf_sha256"] != source[3]
                or replay["linked_candidate_elf_sha256"] != first_link[3]
                or replay["candidate_count"] != 1
                or replay["candidate_archive_count"] != 1
                or replay["archive_selection_strategy"] != "single_pass_user_order"
                or replay["original_strong_imports_resolved_by_ld_r"] !=
                   saved["original_after_x11_imports_resolved"]
                or replay["original_strong_imports_remaining_after_ld_r"] !=
                   saved["original_after_x11_imports_remaining"]
                or replay["new_strong_imports_introduced_by_candidates"] !=
                   saved["new_imports_introduced_by_xcb"]
                or replay["final_strong_import_count"] != len(new_names)):
            raise ValueError("MAP02 XCB independent GNU ld-r output differs")
        for f in opened:
            _confirm_owned(f)
        return {
            "schema": SCHEMA,
            "input_x11_partial_sha256": source[3],
            "copied_xcb_archive_sha256": archive[3],
            "byte_identical_xcb_elf_sha256": first_link[3],
            "input_x11_strong_undefined": expected_x11_strong,
            "xcb_original_strong_imports_resolved": len(original_names - new_names),
            "xcb_new_strong_imports": len(new_names - original_names),
            "output_xcb_strong_undefined": len(new_names),
            "saved_xcb_report_recount_verified": True,
            "second_native_xcb_ld_r_executed": True,
            "byte_identical_xcb_ld_r_verified": True,
            "retail_assets_linked": False,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for f in opened:
            os.close(f[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_after_x11_manifest", type=Path)
    parser.add_argument("private_x11_linked_elf", type=Path)
    parser.add_argument("private_copied_system_xcb_archive", type=Path)
    parser.add_argument("private_xcb_linked_elf", type=Path)
    parser.add_argument("saved_numeric_xcb_report", type=Path)
    parser.add_argument("new_private_replay_output_dir", type=Path)
    args = parser.parse_args()
    try:
        answer = verify_xcb_relink(
            args.private_after_x11_manifest, args.private_x11_linked_elf,
            args.private_copied_system_xcb_archive, args.private_xcb_linked_elf,
            args.saved_numeric_xcb_report, args.new_private_replay_output_dir)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("MAP02 independent XCB native replay failed")
    print(json.dumps(answer, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
