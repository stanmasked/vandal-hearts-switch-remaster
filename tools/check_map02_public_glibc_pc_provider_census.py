#!/usr/bin/env python3
"""Read-only strong-export census of 493 original PC MAP02 imports against glibc.

The original 520 / SDL2 1085 / X11-XCB-Xau-Xdmcp 983 stage files must be
genuine owner-private x86_64 ELF ET_REL. Copy real ordinary libc.a and the
underlying ordinary versioned libm-*.a into a fresh private folder. Compare
strong exported names only: this does NOT try to link glibc or prove ABI,
provider-selection, completeness, a game executable or authentic MAP02.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _private_output_dir, _unresolved,
)
from tools.check_map02_private_provider_coverage import (
    _candidate_strong_exports, read_private_manifest,
)
from tools.check_map02_public_sdl2_archive_witness import _copy_system_archive

SCHEMA = "vh.map02.public-original-pc-glibc-static-strong-provider-census.v1"
COPY_LIBC = "glibc-system-libc-static.a"
COPY_LIBM = "glibc-system-libm-static.a"


def audit_glibc_static_coverage(original_manifest, original_elf,
                                after_sdl_manifest, after_sdl_elf,
                                four_group_elf, system_libc_archive,
                                system_actual_libm_archive, new_private_root,
                                *, expected_original=520,
                                expected_after_sdl=1085,
                                expected_original_survivors=493,
                                expected_final=983):
    expected = (expected_original, expected_after_sdl,
                expected_original_survivors, expected_final)
    if any(type(v) is not int or v < 0 for v in expected):
        raise ValueError("MAP02 static glibc coverage expected counts invalid")
    original_doc = read_private_manifest(original_manifest)
    after_doc = read_private_manifest(after_sdl_manifest)
    files = []
    try:
        for path in (original_elf, after_sdl_elf, four_group_elf):
            if Path(path).suffix != ".o":
                raise ValueError("MAP02 glibc source must be native PC .o")
            item = _open_owned(path, require_private=True)
            files.append(item)
            _check_abi(item)
        first, second, last = files
        if (len({(f[2][0], f[2][1]) for f in files}) != 3
                or first[3] != original_doc["relocatable_elf_sha256"]
                or second[3] != after_doc["relocatable_elf_sha256"]):
            raise ValueError("MAP02 glibc source identity or manifest differs")
        first_s, first_w = _unresolved(first)
        second_s, second_w = _unresolved(second)
        final_s, _ = _unresolved(last)
        if (first_s != original_doc["strong_symbols"]
                or first_w != original_doc["weak_symbols"]
                or second_s != after_doc["strong_symbols"]
                or second_w != after_doc["weak_symbols"]):
            raise ValueError("MAP02 glibc source strong/weak import names differ")
        originals, after, final = set(first_s), set(second_s), set(final_s)
        old_still_after_sdl = originals & after
        surviving_originals = old_still_after_sdl & final
        if (len(originals), len(after), len(surviving_originals),
                len(final)) != expected:
            raise ValueError("MAP02 glibc actual baseline and origin differ")
        for f in files:
            _confirm_owned(f)
        root, _ = _private_output_dir(new_private_root)
        copies = [root / COPY_LIBC, root / COPY_LIBM]
        origins = (system_libc_archive, system_actual_libm_archive)
        copy_digests = []
        for src, dst in zip(origins, copies):
            copy_digests.append(_copy_system_archive(src, dst))
        # Two paths to the same bytes are not independent libc/libm providers.
        if len(set(copy_digests)) != 2:
            raise ValueError("MAP02 glibc libc/libm provider archives must differ")
        providers = []
        try:
            for candidate in copies:
                p = _open_owned(candidate, require_private=True)
                providers.append(p)
                _check_abi(p)
            if len({(p[2][0], p[2][1]) for p in providers}) != 2:
                raise ValueError("MAP02 glibc candidate static inodes alias")
            if any(p[3] != copied for p, copied in zip(providers, copy_digests)):
                raise ValueError("MAP02 glibc system archive copy digest mismatch")
            libc_names = _candidate_strong_exports(copies[0])
            libm_names = _candidate_strong_exports(copies[1])
            for p in providers:
                _confirm_owned(p)
            for f in files:
                _confirm_owned(f)
            libc = surviving_originals & libc_names
            libm = surviving_originals & libm_names
            both = libc & libm
            c_only = libc - libm
            m_only = libm - libc
            missing = surviving_originals - libc - libm
            if (len(both) + len(c_only) + len(m_only) + len(missing)
                    != expected_original_survivors):
                raise ValueError("MAP02 glibc strong provider buckets disagree")
            return {
                "schema": SCHEMA,
                "original_public_elf_sha256": first[3],
                "after_sdl2_public_elf_sha256": second[3],
                "four_group_public_elf_sha256": last[3],
                "copied_native_libc_archive_sha256": providers[0][3],
                "copied_native_libm_archive_sha256": providers[1][3],
                "original_initial_strong_undefined": len(originals),
                "after_sdl2_strong_undefined": len(after),
                "four_archives_final_strong_undefined": len(final),
                "original_pc_still_strong_undefined": len(surviving_originals),
                "original_pc_with_libc_strong_export": len(libc),
                "original_pc_with_libm_strong_export": len(libm),
                "original_pc_libc_only_strong_export": len(c_only),
                "original_pc_libm_only_strong_export": len(m_only),
                "original_pc_both_strong_exports": len(both),
                "original_pc_without_either_strong_export": len(missing),
                "static_archive_bytes_from_system_not_executable": True,
                "only_export_name_presence_measured": True,
                "native_glibc_link_or_compatibility_proven": False,
                "retail_assets_linked": False,
                "fully_linked_game_executable": False,
                "authentic_map02_execution_proven": False,
            }
        finally:
            for p in providers:
                os.close(p[0])
    finally:
        for f in files:
            os.close(f[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("private_original_manifest", type=Path)
    ap.add_argument("private_original_elf", type=Path)
    ap.add_argument("private_after_sdl2_manifest", type=Path)
    ap.add_argument("private_after_sdl2_elf", type=Path)
    ap.add_argument("private_four_archive_elf", type=Path)
    ap.add_argument("ordinary_native_system_libc_a", type=Path)
    ap.add_argument("ordinary_native_versioned_system_libm_a", type=Path)
    ap.add_argument("new_owner_private_output_root", type=Path)
    args = ap.parse_args()
    try:
        result = audit_glibc_static_coverage(
            args.private_original_manifest, args.private_original_elf,
            args.private_after_sdl2_manifest, args.private_after_sdl2_elf,
            args.private_four_archive_elf,
            args.ordinary_native_system_libc_a,
            args.ordinary_native_versioned_system_libm_a,
            args.new_owner_private_output_root)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        ap.error("MAP02 glibc original-PC native static provider census failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
