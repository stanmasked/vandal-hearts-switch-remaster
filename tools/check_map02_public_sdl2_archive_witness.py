#!/usr/bin/env python3
"""Measure public-code MAP02 strong imports against a real system SDL2 .a.

Runs only on the Linux host holding the source-pinned asset-free PC ET_REL.
Original game assets and individual symbol names are never exported.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_incremental_link import (
    MAX_BYTES, _confirm_owned, _open_owned, _private_output_dir,
    probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    audit_provider_coverage, read_private_manifest,
)

SCHEMA = "vh.map02.public-pc-sdl2-static-provider-witness.v1"
CHUNK = 1024 * 1024


def _copy_system_archive(source_path, target):
    """Copy one unchanged normal system library to an owner-private inode."""
    file_fd = None
    destination_fd = None
    try:
        file_fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
        before = os.fstat(file_fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 < before.st_size <= MAX_BYTES):
            raise ValueError("MAP02 SDL2 candidate source metadata invalid")
        if os.pread(file_fd, 8, 0) != b"!<arch>\n":
            raise ValueError("MAP02 SDL2 source is not an ordinary static archive")
        destination_fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(destination_fd, 0o600)
        digest = hashlib.sha256()
        for offset in range(0, before.st_size, CHUNK):
            block = os.pread(
                file_fd, min(CHUNK, before.st_size - offset), offset)
            if len(block) != min(CHUNK, before.st_size - offset):
                raise ValueError("MAP02 SDL2 source archive changed while copying")
            digest.update(block)
            view = memoryview(block)
            while view:
                n = os.write(destination_fd, view)
                if n <= 0:
                    raise ValueError("MAP02 SDL2 local copy incomplete")
                view = view[n:]
        os.fsync(destination_fd)
        after = os.fstat(file_fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mode,
                before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mode,
                after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("MAP02 SDL2 source archive changed while copying")
        source_name = os.stat(source_path, follow_symlinks=False)
        if (not stat.S_ISREG(source_name.st_mode)
                or (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns) !=
                   (source_name.st_dev, source_name.st_ino, source_name.st_size,
                    source_name.st_mtime_ns, source_name.st_ctime_ns)):
            raise ValueError("MAP02 SDL2 source archive pathname changed")
        copied = os.fstat(destination_fd)
        if (not stat.S_ISREG(copied.st_mode)
                or copied.st_uid != os.geteuid() or copied.st_nlink != 1
                or stat.S_IMODE(copied.st_mode) != 0o600
                or copied.st_size != before.st_size):
            raise ValueError("MAP02 SDL2 copied archive metadata invalid")
        return digest.hexdigest()
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
        if file_fd is not None:
            os.close(file_fd)


def probe_public_sdl2_archive(manifest, partial, system_sdl2_archive, output_dir,
                              *, expected_initial_strong_imports=520):
    """Actual GNU ld-r measurement; source assets remain absent."""
    original = read_private_manifest(manifest)
    if (type(expected_initial_strong_imports) is not int
            or expected_initial_strong_imports < 0
            or len(original["strong_symbols"]) !=
               expected_initial_strong_imports):
        raise ValueError("MAP02 original public-code strong baseline mismatch")
    parent, _ = _private_output_dir(output_dir)
    local_archive = parent / "sdl2-system-candidate.a"
    copied_digest = _copy_system_archive(system_sdl2_archive, local_archive)
    copied_entry = _open_owned(local_archive, require_private=True)
    try:
        if copied_entry[3] != copied_digest:
            raise ValueError("MAP02 SDL2 local copy SHA-256 mismatch")
        coverage = audit_provider_coverage(manifest, [local_archive])
        _confirm_owned(copied_entry)
        result = probe_private_incremental_link(
            manifest, partial, [local_archive], parent / "linked",
            expected_initial_strong_imports=expected_initial_strong_imports)
        _confirm_owned(copied_entry)
    finally:
        os.close(copied_entry[0])
    if (coverage["original_strong_unresolved_count"] !=
            expected_initial_strong_imports
            or result["original_strong_import_count"] !=
               expected_initial_strong_imports
            or result["source_partial_elf_sha256"] !=
               original["relocatable_elf_sha256"]
            or result["candidate_count"] != 1
            or result["candidate_archive_count"] != 1
            or result["archive_selection_strategy"] != "single_pass_user_order"
            or coverage["strong_symbols_with_candidate_provider"]
               + coverage["strong_symbols_without_candidate_provider"]
               != expected_initial_strong_imports
            or result["original_strong_imports_remaining_after_ld_r"]
               + result["new_strong_imports_introduced_by_candidates"]
               != result["final_strong_import_count"]):
        raise ValueError("MAP02 SDL2 public archive evidence inconsistent")
    return {
        "schema": SCHEMA,
        "public_source_elf_sha256": result["source_partial_elf_sha256"],
        "sdl2_candidate_archive_sha256": copied_digest,
        "initial_strong_undefined": result["original_strong_import_count"],
        "sdl2_candidate_strong_exports_matching_initial":
            coverage["strong_symbols_with_candidate_provider"],
        "initial_without_sdl2_candidate_export":
            coverage["strong_symbols_without_candidate_provider"],
        "original_imports_resolved_by_actual_ld_r":
            result["original_strong_imports_resolved_by_ld_r"],
        "original_imports_still_unresolved":
            result["original_strong_imports_remaining_after_ld_r"],
        "new_undefined_imports_introduced_by_sdl2":
            result["new_strong_imports_introduced_by_candidates"],
        "final_undefined_strong_count": result["final_strong_import_count"],
        "linked_partial_elf_sha256": result["linked_candidate_elf_sha256"],
        "ordinary_native_static_archive_tested": True,
        "system_archive_package_origin_independently_attested": False,
        "asset_free_public_pc_code_only": True,
        "fully_linked_game_executable": False,
        "original_map02_execution_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_public_undefined_manifest", type=Path)
    parser.add_argument("owner_private_public_partial_elf", type=Path)
    parser.add_argument("system_sdl2_static_archive", type=Path)
    parser.add_argument("new_owner_private_output_directory", type=Path)
    args = parser.parse_args()
    try:
        report = probe_public_sdl2_archive(
            args.owner_private_public_undefined_manifest,
            args.owner_private_public_partial_elf,
            args.system_sdl2_static_archive,
            args.new_owner_private_output_directory)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("MAP02 SDL2 static archive public-code probe failed")
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
