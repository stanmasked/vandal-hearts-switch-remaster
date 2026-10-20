#!/usr/bin/env python3
"""Compare two real private GNU ld -r strategies on unchanged local archives.

No original retail assets or symbol names belong in the public repository.
Both output objects remain private ET_REL files, not runnable game binaries.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_provider_coverage import read_private_manifest
from tools.check_map02_private_incremental_link import (
    OUTPUT, _confirm_owned, _open_owned, _private_output_dir,
    probe_private_incremental_link,
)

SCHEMA = "vh.map02.private-archive-strategy-comparison.v1"


def _pin_link_output(parent, name, expected_sha):
    """Hold actual linked ET_REL descriptors open across both passes."""
    folder = parent / name
    try:
        info = folder.lstat()
    except OSError:
        raise ValueError("private MAP02 paired output directory inaccessible") from None
    if (not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("private MAP02 paired output directory unsafe")
    ident = (info.st_dev, info.st_ino, info.st_uid, info.st_mode)
    entry = _open_owned(folder / OUTPUT, require_private=True)
    if entry[3] != expected_sha:
        os.close(entry[0])
        raise ValueError("private MAP02 paired output ELF digest mismatch")
    return entry, folder, ident


def _confirm_link_output(pinned):
    entry, folder, ident = pinned
    _confirm_owned(entry)
    try:
        current = folder.lstat()
    except OSError:
        raise ValueError("private MAP02 paired output directory inaccessible") from None
    if (current.st_dev, current.st_ino, current.st_uid,
            current.st_mode) != ident:
        raise ValueError("private MAP02 paired output directory replaced")


def compare_private_archive_strategies(manifest, partial, archives, out_dir):
    """Return aggregate evidence only; pin inputs across both actual links."""
    archives = [Path(item) for item in archives]
    if not 2 <= len(archives) <= 64 or any(
            item.suffix != ".a" for item in archives):
        raise ValueError(
            "private MAP02 comparison requires 2..64 native archive inputs")
    manifest_doc = read_private_manifest(manifest)
    entries = []
    outputs = []
    try:
        # Hold descriptors across both invocations so an inode, a same-size
        # write, or an altered archive cannot silently change the comparison.
        sources = [(manifest, True), (partial, True)] + [
            (item, False) for item in archives]
        seen = set()
        for path, private in sources:
            entry = _open_owned(path, require_private=private)
            entries.append(entry)
            key = (entry[2][0], entry[2][1])
            if key in seen:
                raise ValueError("private MAP02 paired link input repeated")
            seen.add(key)
        if entries[1][3] != manifest_doc["relocatable_elf_sha256"]:
            raise ValueError("private MAP02 paired source digest mismatch")
        parent, parent_identity = _private_output_dir(out_dir)
        single = probe_private_incremental_link(
            manifest, partial, archives, parent / "single-pass")
        outputs.append(_pin_link_output(
            parent, "single-pass", single["linked_candidate_elf_sha256"]))
        for entry in entries:
            _confirm_owned(entry)
        grouped = probe_private_incremental_link(
            manifest, partial, archives, parent / "grouped",
            group_archives=True)
        outputs.append(_pin_link_output(
            parent, "grouped", grouped["linked_candidate_elf_sha256"]))
        for entry in entries:
            _confirm_owned(entry)
        for pinned in outputs:
            _confirm_link_output(pinned)
        info = parent.lstat()
        if (info.st_dev, info.st_ino, info.st_uid,
                info.st_mode & 0o777) != parent_identity:
            raise ValueError("private MAP02 paired output directory replaced")
        if (single["archive_selection_strategy"] != "single_pass_user_order"
                or grouped["archive_selection_strategy"] != "repeated_archive_group"
                or single["source_partial_elf_sha256"] != entries[1][3]
                or grouped["source_partial_elf_sha256"] != entries[1][3]
                or single["candidate_count"] != len(archives)
                or grouped["candidate_count"] != len(archives)
                or single["candidate_archive_count"] != len(archives)
                or grouped["candidate_archive_count"] != len(archives)
                or single["original_strong_import_count"] !=
                   grouped["original_strong_import_count"]):
            raise ValueError("private MAP02 paired native link reports inconsistent")
        return {
            "schema": SCHEMA,
            "source_partial_elf_sha256": entries[1][3],
            "candidate_archive_count": len(archives),
            "single_pass_original_imports_resolved":
                single["original_strong_imports_resolved_by_ld_r"],
            "grouped_original_imports_resolved":
                grouped["original_strong_imports_resolved_by_ld_r"],
            "single_pass_new_imports":
                single["new_strong_imports_introduced_by_candidates"],
            "grouped_new_imports":
                grouped["new_strong_imports_introduced_by_candidates"],
            "single_pass_final_strong_import_count":
                single["final_strong_import_count"],
            "grouped_final_strong_import_count":
                grouped["final_strong_import_count"],
            "group_minus_single_final_strong_imports":
                (grouped["final_strong_import_count"] -
                 single["final_strong_import_count"]),
            "single_pass_partial_elf_sha256":
                single["linked_candidate_elf_sha256"],
            "grouped_partial_elf_sha256":
                grouped["linked_candidate_elf_sha256"],
            "inputs_verified_unchanged_after_both_links": True,
            "outputs_verified_unchanged_after_both_links": True,
            "fully_linked_game_executable": False,
            "original_map02_execution_proven": False,
        }
    finally:
        for pinned in outputs:
            os.close(pinned[0][0])
        for entry in entries:
            os.close(entry[0])


def write_private_archive_receipt(report, destination):
    """Create a private report once; never overwrite or follow symlinks."""
    destination = Path(destination).absolute()
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode(
        "utf-8")
    if (report.get("schema") != SCHEMA or not 0 < len(payload) <= 16384):
        raise ValueError("private MAP02 paired report invalid")
    directory_fd = None
    report_fd = None
    committed = False
    try:
        directory_fd = os.open(
            destination.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        directory = os.fstat(directory_fd)
        named = destination.parent.lstat()
        if (not stat.S_ISDIR(directory.st_mode)
                or directory.st_uid != os.geteuid()
                or stat.S_IMODE(directory.st_mode) != 0o700
                or (directory.st_dev, directory.st_ino) !=
                   (named.st_dev, named.st_ino)):
            raise ValueError("private MAP02 receipt directory unsafe")
        report_fd = os.open(
            destination.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
        os.fchmod(report_fd, 0o600)
        for offset in range(0, len(payload), 4096):
            block = memoryview(payload)[offset:offset + 4096]
            while block:
                n = os.write(report_fd, block)
                if n <= 0:
                    raise ValueError("private MAP02 receipt write incomplete")
                block = block[n:]
        os.fsync(report_fd)
        written = os.fstat(report_fd)
        named_output = os.stat(
            destination.name, dir_fd=directory_fd, follow_symlinks=False)
        if (not stat.S_ISREG(written.st_mode)
                or written.st_uid != os.geteuid()
                or stat.S_IMODE(written.st_mode) != 0o600
                or written.st_nlink != 1 or written.st_size != len(payload)
                or (written.st_dev, written.st_ino, written.st_mode) !=
                   (named_output.st_dev, named_output.st_ino,
                    named_output.st_mode)):
            raise ValueError("private MAP02 receipt metadata unsafe")
        os.fsync(directory_fd)
        committed = True
    except OSError:
        raise ValueError("private MAP02 receipt write unavailable") from None
    finally:
        if not committed and report_fd is not None and directory_fd is not None:
            # An interrupted/failed new receipt must not be left behind as
            # plausible evidence. Unlink only the inode opened with O_EXCL;
            # never remove an unrelated file substituted at the same name.
            try:
                opened = os.fstat(report_fd)
                named_failed = os.stat(
                    destination.name, dir_fd=directory_fd,
                    follow_symlinks=False)
                if (stat.S_ISREG(named_failed.st_mode)
                        and opened.st_dev == named_failed.st_dev
                        and opened.st_ino == named_failed.st_ino
                        and opened.st_uid == named_failed.st_uid
                        and opened.st_nlink == 1):
                    os.unlink(destination.name, dir_fd=directory_fd)
                    try:
                        os.fsync(directory_fd)
                    except OSError:
                        pass
            except OSError:
                pass
        if report_fd is not None:
            os.close(report_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("new_private_comparison_dir", type=Path)
    parser.add_argument("native_candidate_archive", type=Path, nargs="+")
    parser.add_argument(
        "--report-file", type=Path,
        help="create a new private 0600 JSON file within an existing 0700 directory")
    args = parser.parse_args()
    try:
        result = compare_private_archive_strategies(
            args.private_undefined_manifest,
            args.private_original_partial_elf,
            args.native_candidate_archive,
            args.new_private_comparison_dir)
        if args.report_file is not None:
            write_private_archive_receipt(result, args.report_file)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("private MAP02 paired archive comparison failed")
    if args.report_file is None:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print("Private MAP02 paired audit report securely saved")


if __name__ == "__main__":
    main()
