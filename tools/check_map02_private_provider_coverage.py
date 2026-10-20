#!/usr/bin/env python3
"""Owner-private, read-only candidate coverage audit for MAP02 ELF imports.

Given the optional 0600 unresolved-import manifest from the verified ET_REL
audit, inspect explicitly supplied local .o/.a files for strong definitions.
Report aggregate candidate coverage ONLY. This does not link or run a game,
prove compatibility or authenticity, or disclose retail source or names.
Linux /proc/self/fd is required to keep nm bound to the opened provider inode.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

SCHEMA = "vh.map02.private-link-provider-coverage.v1"
MANIFEST_SCHEMA = "vh.map02.private-undefined-symbol-manifest.v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_CANDIDATE_BYTES = 256 * 1024 * 1024
STRONG_KINDS = frozenset("TDBRGSAI")


def _sha_names(names):
    return hashlib.sha256(json.dumps(
        names, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def read_private_manifest(path):
    """Read one exact owner-only JSON manifest; never log its full path."""
    path = Path(path).absolute()
    folder = path.parent
    try:
        folder_info = folder.lstat()
        if (not stat.S_ISDIR(folder_info.st_mode)
                or folder_info.st_uid != os.geteuid()
                or stat.S_IMODE(folder_info.st_mode) != 0o700):
            raise ValueError("private MAP02 import manifest directory not owner-only")
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("private MAP02 import manifest directory unavailable") from None
    try:
        try:
            file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW,
                              dir_fd=fd)
        except OSError:
            raise ValueError("private MAP02 import manifest file unavailable") from None
        try:
            info = os.fstat(file_fd)
            if (not stat.S_ISREG(info.st_mode) or
                    info.st_uid != os.geteuid() or info.st_nlink != 1 or
                    stat.S_IMODE(info.st_mode) != 0o600 or
                    not 0 < info.st_size <= MAX_MANIFEST_BYTES):
                raise ValueError("private MAP02 import manifest metadata unsafe")
            payload = os.pread(file_fd, info.st_size + 1, 0)
            if len(payload) != info.st_size:
                raise ValueError("private MAP02 import manifest changed during read")
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)
    try:
        manifest = json.loads(payload)
    except (ValueError, UnicodeError):
        raise ValueError("private MAP02 import manifest JSON invalid") from None
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != MANIFEST_SCHEMA):
        raise ValueError("private MAP02 import manifest schema invalid")
    names = manifest.get("strong_symbols")
    weak = manifest.get("weak_symbols")
    def valid_names(values):
        return (isinstance(values, list) and len(values) <= 50000
                and all(isinstance(x, str) and x and
                        "\x00" not in x and "\n" not in x for x in values)
                and values == sorted(set(values)))
    if not valid_names(names) or not valid_names(weak):
        raise ValueError("private MAP02 import symbol names invalid")
    if (manifest.get("partial_elf_unresolved_strong_symbol_count") != len(names)
            or manifest.get("partial_elf_unresolved_weak_symbol_count") != len(weak)
            or manifest.get("partial_elf_unresolved_strong_symbols_sha256") !=
               _sha_names(names)):
        raise ValueError("private MAP02 import manifest digest/count mismatch")
    elf_hash = manifest.get("relocatable_elf_sha256")
    if (not isinstance(elf_hash, str) or len(elf_hash) != 64 or
            any(ch not in "0123456789abcdef" for ch in elf_hash)):
        raise ValueError("private MAP02 import manifest ELF identity invalid")
    return manifest


def _candidate_strong_exports(candidate):
    """GNU nm -P over the same opened inode; no symbol names in errors."""
    path = Path(candidate).absolute()
    if path.suffix not in (".o", ".a"):
        raise ValueError("private MAP02 provider input must be .o or .a")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise ValueError("private MAP02 provider input unavailable") from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid() or info.st_nlink != 1
                or not stat.S_IMODE(info.st_mode) & stat.S_IRUSR
                or stat.S_IMODE(info.st_mode) & 0o022
                or not 0 < info.st_size <= MAX_CANDIDATE_BYTES):
            raise ValueError("private MAP02 provider input metadata unsafe")
        before = (info.st_dev, info.st_ino, info.st_size,
                  info.st_mtime_ns, info.st_ctime_ns)
        try:
            res = subprocess.run(
                ["nm", "-g", "-P", "--defined-only",
                 f"/proc/self/fd/{fd}"],
                pass_fds=(fd,), capture_output=True, text=True,
                check=False, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("private MAP02 provider symbol inspector unavailable") from None
        if res.returncode:
            raise ValueError("private MAP02 provider symbol inspection failed")
        after = os.fstat(fd)
        identity = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        if identity != before:
            raise ValueError("private MAP02 provider changed during inspection")
        try:
            current = path.lstat()
        except OSError:
            raise ValueError("private MAP02 provider path replaced during inspection") from None
        if (stat.S_ISLNK(current.st_mode) or
                (current.st_dev, current.st_ino, current.st_size,
                 current.st_mtime_ns, current.st_ctime_ns) != before):
            raise ValueError("private MAP02 provider path replaced during inspection")
        strong = set()
        for line in res.stdout.splitlines():
            fields = line.split()
            if not fields:
                continue
            # GNU nm -P prefixes archive members with a "...[member]:" row.
            if line.endswith(":") and len(fields) == 1:
                continue
            if len(fields) < 3 or len(fields[1]) != 1:
                raise ValueError("private MAP02 provider nm output malformed")
            name, kind = fields[:2]
            if kind in STRONG_KINDS:
                strong.add(name)
            elif kind not in ("W", "V", "C"):
                raise ValueError("private MAP02 provider nm symbol type unknown")
        return strong
    finally:
        os.close(fd)


def audit_provider_coverage(manifest, candidates):
    """Only show numbers; weak/common definitions are not counted as strong."""
    doc = read_private_manifest(manifest)
    if not candidates:
        raise ValueError("private MAP02 provider candidate list is empty")
    if len(candidates) > 256:
        raise ValueError("too many private MAP02 provider candidates")
    needed = set(doc["strong_symbols"])
    hits = {}
    for path in candidates:
        for name in _candidate_strong_exports(path) & needed:
            hits[name] = hits.get(name, 0) + 1
    return {
        "schema": SCHEMA,
        "relocatable_elf_sha256": doc["relocatable_elf_sha256"],
        "original_strong_unresolved_count": len(needed),
        "candidate_provider_file_count": len(candidates),
        "strong_symbols_with_candidate_provider": len(hits),
        "strong_symbols_with_multiple_candidates":
            sum(n > 1 for n in hits.values()),
        "strong_symbols_without_candidate_provider": len(needed) - len(hits),
        "candidate_resolves_full_game_link": False,
        "original_map02_execution_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_undefined_manifest", type=Path)
    parser.add_argument("candidate_object_or_archive", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        result = audit_provider_coverage(
            args.private_undefined_manifest, args.candidate_object_or_archive)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Avoid printing user-owned paths, symbol names or subprocess stderr.
        parser.error("private MAP02 candidate provider audit failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
