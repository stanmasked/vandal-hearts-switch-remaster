#!/usr/bin/env python3
"""Experimental genuine GNU ld -r glibc archive provenance, not a game build.

Input files and symbol names stay private; JSON output contains counts and hashes.
A failed native linker is a failed experiment, NEVER a zero-resolution success.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_private_incremental_link import (
    OUTPUT, _check_abi, _confirm_owned, _open_owned,
    _private_output_dir, _unresolved, probe_private_incremental_link,
)
from tools.check_map02_private_provider_coverage import (
    STRONG_KINDS, _candidate_strong_exports, read_private_manifest,
)
from tools.check_map02_public_x11_after_sdl2 import _save_local_undefined_manifest

SCHEMA = "vh.map02.public-glibc-grouped-actual-ld-r-origin.v1"
CENSUS_SCHEMA = "vh.map02.public-original-pc-glibc-static-strong-provider-census.v1"


def _read_aggregate(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("MAP02 glibc census JSON symlink forbidden")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size < 65536:
        raise ValueError("MAP02 glibc census JSON invalid")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("MAP02 glibc census JSON invalid") from None
    if not isinstance(report, dict) or report.get("schema") != CENSUS_SCHEMA:
        raise ValueError("MAP02 glibc census schema invalid")
    return report



def _archive_binding_classes(path):
    """Classify actual GNU nm exported definitions; never return names to stdout."""
    opened = _open_owned(path, require_private=True)
    try:
        _check_abi(opened)
        fd = opened[0]
        safe_env = {
            k: v for k, v in os.environ.items()
            if not k.startswith(("LD_", "DYLD_", "PYTHON", "VH_"))
        }
        try:
            report = subprocess.run(
                ["nm", "-g", "-P", "--defined-only", f"/proc/self/fd/{fd}"],
                pass_fds=(fd,), capture_output=True, text=True,
                timeout=45, check=False, umask=0o077, env=safe_env)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("MAP02 glibc binding-class tool unavailable") from None
        if report.returncode:
            raise ValueError("MAP02 glibc binding-class nm failed")
        buckets = {"strong": set(), "weak": set(), "common": set()}
        for line in report.stdout.splitlines():
            fields = line.split()
            if not fields or (line.endswith(":") and len(fields) == 1):
                continue
            if len(fields) < 3 or len(fields[1]) != 1:
                raise ValueError("MAP02 glibc binding-class nm malformed")
            name, kind = fields[:2]
            if kind in STRONG_KINDS:
                buckets["strong"].add(name)
            elif kind in ("W", "V"):
                buckets["weak"].add(name)
            elif kind == "C":
                buckets["common"].add(name)
            else:
                raise ValueError("MAP02 glibc binding-class symbol type unsupported")
        _confirm_owned(opened)
        return buckets
    finally:
        os.close(opened[0])


def audit_glibc_real_link(original_manifest, original_elf,
                          after_sdl_manifest, after_sdl_elf, four_group_elf,
                          copied_native_libc, copied_native_libm,
                          completed_census_json, new_private_root, *,
                          expected_pc_survivors=493, expected_four_total=983):
    """Run the actual grouped ld -r and attribute final strong symbols by origin."""
    orig = read_private_manifest(original_manifest)
    sdl = read_private_manifest(after_sdl_manifest)
    prior = _read_aggregate(completed_census_json)
    if any(type(x) is not int or x < 0
           for x in (expected_pc_survivors, expected_four_total)):
        raise ValueError("MAP02 real-glibc link baseline invalid")

    entries = []
    try:
        for path in (original_elf, after_sdl_elf, four_group_elf,
                     copied_native_libc, copied_native_libm):
            item = _open_owned(path, require_private=True)
            entries.append(item)
            _check_abi(item)
        original_source, sdl_source, four, libc, libm = entries
        if (any(e[1].suffix != ".o" for e in entries[:3])
                or libc[1].suffix != ".a"
                or libm[1].suffix != ".a"
                or len({(e[2][0], e[2][1]) for e in entries}) != 5
                or libc[3] == libm[3]):
            raise ValueError("MAP02 real-glibc input identities invalid")
        witness = (
            ("four_group_public_elf_sha256", four[3]),
            ("copied_native_libc_archive_sha256", libc[3]),
            ("copied_native_libm_archive_sha256", libm[3]),
            ("original_public_elf_sha256", original_source[3]),
            ("after_sdl2_public_elf_sha256", sdl_source[3]),
        )
        if any(prior.get(field) != digest for field, digest in witness):
            raise ValueError("MAP02 real-glibc input census SHA mismatched")

        orig_strong, orig_weak = _unresolved(original_source)
        sdl_strong, sdl_weak = _unresolved(sdl_source)
        if (orig["relocatable_elf_sha256"] != original_source[3]
                or sdl["relocatable_elf_sha256"] != sdl_source[3]
                or orig["strong_symbols"] != orig_strong
                or orig["weak_symbols"] != orig_weak
                or sdl["strong_symbols"] != sdl_strong
                or sdl["weak_symbols"] != sdl_weak):
            raise ValueError("MAP02 real-glibc underlying ELF and manifest disagree")
        before_strong, before_weak = _unresolved(four)
        before = set(before_strong)
        original = set(orig_strong)
        after_sdl = set(sdl_strong)
        pc = original & after_sdl & before
        sdl_new = (after_sdl - original) & before
        system_new = before - after_sdl
        if (len(before) != expected_four_total
                or len(pc) != expected_pc_survivors
                or len(pc) + len(sdl_new) + len(system_new) != len(before)
                or prior.get("four_archives_final_strong_undefined") != len(before)
                or prior.get("original_pc_still_strong_undefined") != len(pc)):
            raise ValueError("MAP02 real-glibc original origin baseline invalid")

        libc_kinds = _archive_binding_classes(libc[1])
        libm_kinds = _archive_binding_classes(libm[1])
        libc_exports = libc_kinds["strong"]
        libm_exports = libm_kinds["strong"]
        # This must agree with the original strong-only provider implementation.
        if (libc_exports != _candidate_strong_exports(libc[1])
                or libm_exports != _candidate_strong_exports(libm[1])):
            raise ValueError("MAP02 glibc strong export parsers disagree")
        c, m = pc & libc_exports, pc & libm_exports
        predicted = (
            ("original_pc_libc_only_strong_export", len(c - m)),
            ("original_pc_libm_only_strong_export", len(m - c)),
            ("original_pc_both_strong_exports", len(c & m)),
            ("original_pc_without_either_strong_export", len(pc - c - m)),
        )
        if any(prior.get(key) != count for key, count in predicted):
            raise ValueError("MAP02 real-glibc candidate census changed")
        for e in entries:
            _confirm_owned(e)

        root, _ = _private_output_dir(new_private_root)
        manifest = _save_local_undefined_manifest(root, four, before_strong, before_weak)
        link = probe_private_incremental_link(
            manifest, four[1], [libc[1], libm[1]],
            root / "linked", group_archives=True,
            expected_initial_strong_imports=expected_four_total)
        linked = _open_owned(root / "linked" / OUTPUT, require_private=True)
        try:
            _check_abi(linked)
            final_strong, _ = _unresolved(linked)
            after = set(final_strong)
            _confirm_owned(linked)
        finally:
            os.close(linked[0])
        for e in entries:
            _confirm_owned(e)

        pc_left = pc & after
        sdl_left = sdl_new & after
        system_left = system_new & after
        introduced = after - before
        # Rank mutually exclusive name-provider categories: strong > weak >
        # common > no exported name. A successful ld-r result is measured
        # separately; an export name alone does not imply linker selection.
        strong = libc_kinds["strong"] | libm_kinds["strong"]
        weak_only = (libc_kinds["weak"] | libm_kinds["weak"]) - strong
        common_only = ((libc_kinds["common"] | libm_kinds["common"])
                       - strong - weak_only)
        strength = {
            "strong": pc & strong,
            "weak_only": pc & weak_only,
            "common_only": pc & common_only,
            "no_export": pc - strong - weak_only - common_only,
        }
        if (sum(map(len, strength.values())) != len(pc)
                or len(strength["strong"]) != len(c | m)):
            raise ValueError("MAP02 glibc binding-class buckets disagree")
        resolved_pc = pc - pc_left
        binding_counts = {}
        for name, matches in strength.items():
            binding_counts[f"original_pc_{name}_candidate"] = len(matches)
            binding_counts[f"original_pc_{name}_resolved_by_ld_r"] = (
                len(matches & resolved_pc))
            binding_counts[f"original_pc_{name}_still_undefined"] = (
                len(matches & pc_left))
        if (sum(binding_counts[f"original_pc_{x}_resolved_by_ld_r"]
                for x in strength) != len(resolved_pc)
                or sum(binding_counts[f"original_pc_{x}_still_undefined"]
                       for x in strength) != len(pc_left)):
            raise ValueError("MAP02 glibc actual resolution by binding differs")
        if (len(pc_left) + len(sdl_left) + len(system_left)
                + len(introduced) != len(after)
                or link["final_strong_import_count"] != len(after)
                or link["linked_candidate_elf_sha256"] is None
                or link["source_partial_elf_sha256"] != four[3]
                or link["candidate_archive_count"] != 2
                or link["archive_selection_strategy"] != "repeated_archive_group"
                or link["original_strong_imports_resolved_by_ld_r"]
                   != len(before - after)
                or link["new_strong_imports_introduced_by_candidates"]
                   != len(introduced)):
            raise ValueError("MAP02 real-glibc native link arithmetic differs")
        return {
            "schema": SCHEMA,
            "input_four_elf_sha256": four[3],
            "libc_archive_sha256": libc[3],
            "libm_archive_sha256": libm[3],
            "linked_partial_elf_sha256": link["linked_candidate_elf_sha256"],
            "initial_four_group_undefined": len(before),
            "initial_original_pc_undefined": len(pc),
            "original_pc_resolved_by_real_glibc_ld_r": len(pc - pc_left),
            "original_pc_remaining_after_real_glibc_ld_r": len(pc_left),
            **binding_counts,
            "name_provider_strength_does_not_prove_link_selection": True,
            "sdl2_survivors_resolved_by_real_glibc_ld_r": len(sdl_new - sdl_left),
            "sdl2_survivors_remaining_after_real_glibc_ld_r": len(sdl_left),
            "four_archive_new_resolved_by_real_glibc_ld_r": len(system_new - system_left),
            "four_archive_new_remaining_after_real_glibc_ld_r": len(system_left),
            "glibc_new_strong_undefined": len(introduced),
            "final_strong_undefined": len(after),
            "actual_native_grouped_ld_r_executed": True,
            "final_product_is_elf_rel_only": True,
            "fully_linked_game_executable": False,
            "authentic_map02_execution_proven": False,
            "switch_game_proven": False,
            "private_symbol_names_disclosed": False,
        }
    finally:
        for e in entries:
            os.close(e[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "private_original_manifest", "private_original_elf",
        "private_after_sdl2_manifest", "private_after_sdl2_elf",
        "private_four_group_elf", "private_copied_libc_archive",
        "private_copied_libm_archive", "completed_glibc_census_json",
        "new_owner_private_output_root",
    ):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        output = audit_glibc_real_link(
            args.private_original_manifest, args.private_original_elf,
            args.private_after_sdl2_manifest, args.private_after_sdl2_elf,
            args.private_four_group_elf, args.private_copied_libc_archive,
            args.private_copied_libm_archive, args.completed_glibc_census_json,
            args.new_owner_private_output_root)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        parser.error("MAP02 native glibc partial-link experiment failed; no result claimed")
    print(json.dumps(output, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
