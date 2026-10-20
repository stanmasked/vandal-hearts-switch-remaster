#!/usr/bin/env python3
"""Local-only GNU ld -r proof for candidate MAP02 native symbol providers.

This verifies an ACTUAL incremental relocation link, not merely identical
names exported by a file. The result is still ET_REL, not a playable game.
Original retail inputs, native object files, and raw symbol names are never
printed or uploaded. All output remains in a fresh owner-only directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_provider_coverage import (
    _require_native_pc_elf_headers, read_private_manifest,
)
from tools.check_map02_public_reloc_link import _undefined_symbol_names

SCHEMA = "vh.map02.private-incremental-ld-r.v1"
OUTPUT = "map02-private-candidate-linked.o"
MAX_BYTES = 256 * 1024 * 1024
CHUNK = 1024 * 1024


def _digest_fd(fd, size):
    digest = hashlib.sha256()
    for offset in range(0, size, CHUNK):
        block = os.pread(fd, min(CHUNK, size - offset), offset)
        if len(block) != min(CHUNK, size - offset):
            raise ValueError("private MAP02 source object incomplete")
        digest.update(block)
    return digest.hexdigest()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_uid, info.st_mode, info.st_nlink,
            info.st_mtime_ns, info.st_ctime_ns)


def _open_owned(path, *, require_private=False):
    path = Path(path).absolute()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("private MAP02 link object inaccessible") from None
    try:
        st = os.fstat(fd)
        mode = stat.S_IMODE(st.st_mode)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or not 0 < st.st_size <= MAX_BYTES
                or not mode & stat.S_IRUSR or mode & 0o022
                or (require_private and mode != 0o600)):
            raise ValueError("private MAP02 link object metadata unsafe")
        before = _identity(st)
        hashed = _digest_fd(fd, st.st_size)
        if _identity(os.fstat(fd)) != before:
            raise ValueError("private MAP02 link object mutated during hash")
        return fd, path, before, hashed
    except BaseException:
        os.close(fd)
        raise


def _confirm_owned(entry):
    fd, path, ident, hashed = entry
    if _identity(os.fstat(fd)) != ident or _digest_fd(fd, ident[2]) != hashed:
        raise ValueError("private MAP02 link object changed during link")
    try:
        fresh = path.lstat()
    except OSError:
        raise ValueError("private MAP02 link object path unavailable") from None
    if stat.S_ISLNK(fresh.st_mode) or _identity(fresh) != ident:
        raise ValueError("private MAP02 link object path replaced during link")


def _run_native_tool(args, descriptors, *, timeout=60):
    try:
        response = subprocess.run(
            args, pass_fds=tuple(descriptors), capture_output=True,
            text=True, timeout=timeout, check=False,
            umask=0o077,
            env={k: v for k, v in os.environ.items()
                 if not k.startswith(("LD_", "DYLD_", "PYTHON", "VH_"))})
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("private MAP02 native linker tool unavailable") from None
    if response.returncode:
        raise ValueError("private MAP02 native linker tool failed")
    return response.stdout


def _check_abi(entry):
    fd, path = entry[:2]
    # Thin GNU archives refer to external member paths. Passing the archive
    # through /proc/self/fd would not pin those external object bytes.
    # Reject them before readelf or the linker can follow any members.
    header = os.pread(fd, 8, 0)
    if path.suffix == ".a" and header != b"!<arch>\n":
        raise ValueError("private MAP02 thin or invalid archive rejected")
    if path.suffix == ".o" and header[:4] != b"\x7fELF":
        raise ValueError("private MAP02 candidate is not ELF")
    report = _run_native_tool(
        ["readelf", "-hW", f"/proc/self/fd/{fd}"], (fd,))
    _require_native_pc_elf_headers(report)


def _unresolved(entry):
    fd = entry[0]
    result = _run_native_tool(
        ["nm", "-u", f"/proc/self/fd/{fd}"], (fd,))
    return _undefined_symbol_names(result)


def _private_output_dir(path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise ValueError("private MAP02 link output directory must not exist")
    try:
        path.mkdir(mode=0o700)
    except OSError:
        raise ValueError("private MAP02 link output directory unavailable") from None
    metadata = path.lstat()
    if (not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise ValueError("private MAP02 link directory not owner-only")
    return path, (metadata.st_dev, metadata.st_ino, metadata.st_uid,
                  stat.S_IMODE(metadata.st_mode))


def probe_private_incremental_link(manifest, partial, candidates, out_dir,
                                   *, group_archives=False):
    """Return aggregate counts from an actual non-executing GNU partial link."""
    doc = read_private_manifest(manifest)
    if not 1 <= len(candidates) <= 64:
        raise ValueError("private MAP02 candidate count must be 1..64")
    archive_count = sum(Path(candidate).suffix == ".a"
                        for candidate in candidates)
    if group_archives and (
            archive_count < 2 or any(
                Path(candidate).suffix not in (".a", ".o")
                for candidate in candidates)):
        raise ValueError(
            "private MAP02 grouped link requires at least two archive candidates")
    inputs = []
    seen_inodes = set()
    try:
        sources = [(partial, True), *((path, False) for path in candidates)]
        for path, is_partial in sources:
            suffix = Path(path).suffix
            if ((is_partial and suffix != ".o") or
                    (not is_partial and suffix not in (".o", ".a"))):
                raise ValueError("private MAP02 candidate must be native .o/.a")
            item = _open_owned(path, require_private=is_partial)
            inputs.append(item)
            identity = item[2]
            inode_key = (identity[0], identity[1])
            if inode_key in seen_inodes:
                raise ValueError("private MAP02 linker input repeated")
            seen_inodes.add(inode_key)
            _check_abi(item)
        if inputs[0][3] != doc["relocatable_elf_sha256"]:
            raise ValueError("private MAP02 source ELF hash differs from manifest")
        initial_strong, initial_weak = _unresolved(inputs[0])
        if (initial_strong != doc["strong_symbols"]
                or initial_weak != doc["weak_symbols"]):
            raise ValueError("private MAP02 source ELF imports differ from manifest")

        output_dir, dir_ident = _private_output_dir(out_dir)
        output = output_dir / OUTPUT
        fds = [item[0] for item in inputs]
        if group_archives:
            # Direct .o files are unconditional linker inputs. Passing them
            # inside an archive group can repeat their definitions on rescans.
            # Preserve .o order and .a order separately, with all .o first.
            direct = [f"/proc/self/fd/{entry[0]}"
                      for entry in inputs[1:] if entry[1].suffix == ".o"]
            archived = [f"/proc/self/fd/{entry[0]}"
                        for entry in inputs[1:] if entry[1].suffix == ".a"]
            linker_inputs = [
                f"/proc/self/fd/{fds[0]}", *direct,
                "--start-group", *archived, "--end-group"]
        else:
            linker_inputs = [f"/proc/self/fd/{fd}" for fd in fds]
        _run_native_tool(
            ["ld", "-r", "-o", str(output), *linker_inputs],
            fds, timeout=120)
        info = output.lstat()
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise ValueError("private MAP02 linked object metadata unsafe")
        linked = _open_owned(output, require_private=True)
        try:
            _check_abi(linked)
            after_strong, after_weak = _unresolved(linked)
            for entry in inputs:
                _confirm_owned(entry)
            _confirm_owned(linked)
            after_dir = output_dir.lstat()
            if (after_dir.st_dev, after_dir.st_ino, after_dir.st_uid,
                    stat.S_IMODE(after_dir.st_mode)) != dir_ident:
                raise ValueError("private MAP02 output directory changed during link")
            original = set(initial_strong)
            updated = set(after_strong)
            return {
                "schema": SCHEMA,
                "source_partial_elf_sha256": inputs[0][3],
                "candidate_count": len(candidates),
                "candidate_archive_count": archive_count,
                "archive_selection_strategy": (
                    ("direct_objects_before_archive_group"
                     if archive_count < len(candidates)
                     else "repeated_archive_group")
                    if group_archives else "single_pass_user_order"),
                "original_strong_import_count": len(original),
                "original_strong_imports_resolved_by_ld_r":
                    len(original - updated),
                "original_strong_imports_remaining_after_ld_r":
                    len(original & updated),
                "new_strong_imports_introduced_by_candidates":
                    len(updated - original),
                "final_strong_import_count": len(updated),
                "final_weak_import_count": len(after_weak),
                "linked_candidate_elf_sha256": linked[3],
                "fully_linked_game_executable": False,
                "original_map02_execution_proven": False,
            }
        finally:
            os.close(linked[0])
    finally:
        for item in inputs:
            os.close(item[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("private_original_partial_elf", type=Path)
    parser.add_argument("new_private_output_dir", type=Path)
    parser.add_argument("native_candidate", type=Path, nargs="+")
    parser.add_argument(
        "--group-archives", action="store_true",
        help="repeat resolution over two or more .a inputs; direct .o inputs precede the archive group")
    args = parser.parse_args()
    try:
        result = probe_private_incremental_link(
            args.private_undefined_manifest, args.private_original_partial_elf,
            args.native_candidate, args.new_private_output_dir,
            group_archives=args.group_archives)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("private MAP02 incremental link probe failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
