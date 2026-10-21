#!/usr/bin/env python3
"""Owner-private attribution of 380 surviving original-PC imports to compiled TUs.

Read actual GNU nm -u from exactly the 85 game + 33 backend/observer objects
in the pinned asset-free Make inventory. Public JSON contains *only* counts
and SHA-256, never source paths, import names, or retail assets.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_object_inventory import audit_objects
from tools.check_map02_public_reloc_link import (
    make_inventory, sealed_input_fd, stable_object_input,
    _undefined_symbol_names,
)
from tools.check_map02_private_incremental_link import (
    _check_abi, _confirm_owned, _open_owned, _unresolved,
)
from tools.check_map02_private_provider_coverage import read_private_manifest

SCHEMA = "vh.map02.public-pc-original-remaining-module-owners.v1"
LINK_SCHEMA = "vh.map02.public-glibc-grouped-actual-ld-r-origin.v1"
EXPECTED_GAME = 85
EXPECTED_BACKEND = 33


def summarize_owner_groups(remaining, game_refs, backend_refs):
    """Disjoint name buckets, unlike source-reference edge counts."""
    remaining = set(remaining)
    game_refs = [set(x) & remaining for x in game_refs]
    backend_refs = [set(x) & remaining for x in backend_refs]
    game = set().union(*game_refs) if game_refs else set()
    backend = set().union(*backend_refs) if backend_refs else set()
    both = game & backend
    only_game = game - backend
    only_backend = backend - game
    neither = remaining - game - backend
    if len(only_game) + len(only_backend) + len(both) + len(neither) != len(remaining):
        raise ValueError("MAP02 module-owner partition inconsistent")
    return {
        "remaining_pc_total": len(remaining),
        "original_game_only_imports": len(only_game),
        "backend_only_imports": len(only_backend),
        "shared_game_backend_imports": len(both),
        "missing_object_owner_imports": len(neither),
        "game_objects_with_remaining_imports": sum(bool(x) for x in game_refs),
        "backend_objects_with_remaining_imports": sum(bool(x) for x in backend_refs),
        "game_object_symbol_reference_pairs": sum(map(len, game_refs)),
        "backend_object_symbol_reference_pairs": sum(map(len, backend_refs)),
    }


def read_link_report(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("MAP02 glibc link report symlink rejected")
    st = path.stat()
    if not stat.S_ISREG(st.st_mode) or not 0 < st.st_size < 65536:
        raise ValueError("MAP02 glibc link report invalid")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("MAP02 glibc link report invalid") from None
    if not isinstance(doc, dict) or doc.get("schema") != LINK_SCHEMA:
        raise ValueError("MAP02 glibc link report schema invalid")
    return doc


def audit_owners(upstream, overlay_bundle,
                 original_manifest, original_elf,
                 after_sdl_manifest, after_sdl_elf,
                 four_archive_elf, linked_glibc_elf,
                 linked_glibc_report,
                 *, expected_remaining=380):
    if type(expected_remaining) is not int or expected_remaining < 0:
        raise ValueError("MAP02 expected remaining count invalid")
    orig = read_private_manifest(original_manifest)
    sdl = read_private_manifest(after_sdl_manifest)
    report = read_link_report(linked_glibc_report)
    opened = []
    try:
        for path in (original_elf, after_sdl_elf,
                     four_archive_elf, linked_glibc_elf):
            if Path(path).suffix != ".o":
                raise ValueError("MAP02 origin link files must be .o")
            e = _open_owned(path, require_private=True)
            opened.append(e)
            _check_abi(e)
        first, second, four, final = opened
        if len({(e[2][0], e[2][1]) for e in opened}) != 4:
            raise ValueError("MAP02 original link files reused")
        if (first[3] != orig["relocatable_elf_sha256"]
                or second[3] != sdl["relocatable_elf_sha256"]
                or four[3] != report.get("input_four_elf_sha256")
                or final[3] != report.get("linked_partial_elf_sha256")):
            raise ValueError("MAP02 module attribution ELF hash disagreement")
        original_strong, original_weak = _unresolved(first)
        sdl_strong, sdl_weak = _unresolved(second)
        four_strong, _ = _unresolved(four)
        final_strong, final_weak = _unresolved(final)
        if (original_strong != orig["strong_symbols"]
                or original_weak != orig["weak_symbols"]
                or sdl_strong != sdl["strong_symbols"]
                or sdl_weak != sdl["weak_symbols"]):
            raise ValueError("MAP02 module original manifests differ")
        original = set(original_strong)
        sdl_names = set(sdl_strong)
        four_names = set(four_strong)
        final_names = set(final_strong)
        remaining = original & sdl_names & four_names & final_names
        if (len(original) != 520 or len(sdl_names) != 1085
                or len(four_names) != 983 or len(final_names) != 701
                or len(remaining) != expected_remaining
                or report.get("initial_original_pc_undefined") != 493
                or report.get("original_pc_remaining_after_real_glibc_ld_r")
                   != expected_remaining
                or report.get("final_strong_undefined") != len(final_names)
                or remaining & set(final_weak)):
            raise ValueError("MAP02 module surviving PC import baseline differs")
        for e in opened:
            _confirm_owned(e)

        inventory = audit_objects(upstream, overlay_bundle)
        groups = make_inventory(upstream, overlay_bundle)
        if (len(groups) != 2 or len(groups[0]) != EXPECTED_GAME
                or len(groups[1]) != EXPECTED_BACKEND
                or (inventory["original_game_translation_units_compiled"],
                    inventory["native_backend_and_observer_objects_compiled"])
                   != (EXPECTED_GAME, EXPECTED_BACKEND)):
            raise ValueError("MAP02 actual Make module inventory drifted")
        all_paths = groups[0] + groups[1]
        if len(set(all_paths)) != EXPECTED_GAME + EXPECTED_BACKEND:
            raise ValueError("MAP02 duplicate Make module owner")
        root = Path(upstream).absolute() / "platform" / "pc"
        refs = []
        for index, relative in enumerate(all_paths):
            if (not relative.startswith("build-map02-cycle/")
                    or not relative.endswith(".o")
                    or any(part in (".", "..", "") for part in relative.split("/"))):
                raise ValueError("MAP02 invalid Make module object path")
            path = root / relative
            witness = stable_object_input(path)
            fd = sealed_input_fd(path, witness, index=index)
            try:
                res = subprocess.run(
                    ["nm", "-u", f"/proc/self/fd/{fd}"],
                    capture_output=True, text=True, check=False,
                    timeout=30, pass_fds=(fd,), umask=0o077,
                    env={k: v for k, v in os.environ.items()
                         if not k.startswith(("LD_", "DYLD_", "PYTHON", "VH_"))})
                if res.returncode:
                    raise ValueError("MAP02 private module undefined-symbol inspection failed")
                strong, _ = _undefined_symbol_names(res.stdout)
                refs.append(strong)
            finally:
                os.close(fd)
            if stable_object_input(path) != witness:
                raise ValueError("MAP02 module object changed during symbol census")
        for e in opened:
            _confirm_owned(e)
        output = summarize_owner_groups(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:])
        if (output["missing_object_owner_imports"] != 0
                or output["remaining_pc_total"] != expected_remaining
                or output["game_objects_with_remaining_imports"] > EXPECTED_GAME
                or output["backend_objects_with_remaining_imports"] > EXPECTED_BACKEND):
            raise ValueError("MAP02 unresolved import lacks source object provenance")
        return {
            "schema": SCHEMA,
            "original_public_elf_sha256": first[3],
            "after_sdl2_public_elf_sha256": second[3],
            "four_archive_elf_sha256": four[3],
            "linked_glibc_partial_elf_sha256": final[3],
            "original_game_objects_checked": EXPECTED_GAME,
            "backend_and_observer_objects_checked": EXPECTED_BACKEND,
            **output,
            "only_counts_and_hashes_published": True,
            "retail_asset_content_accessed": False,
            "executable_game_proven": False,
            "authentic_map02_execution_proven": False,
        }
    finally:
        for e in opened:
            os.close(e[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in (
        "pinned_public_pc_checkout", "private_overlay_bundle",
        "original_manifest", "original_public_elf",
        "after_sdl2_manifest", "after_sdl2_public_elf",
        "four_archive_public_elf", "linked_glibc_private_elf",
        "completed_glibc_link_numeric_report",
    ):
        ap.add_argument(name, type=Path)
    args = ap.parse_args()
    try:
        result = audit_owners(
            args.pinned_public_pc_checkout, args.private_overlay_bundle,
            args.original_manifest, args.original_public_elf,
            args.after_sdl2_manifest, args.after_sdl2_public_elf,
            args.four_archive_public_elf, args.linked_glibc_private_elf,
            args.completed_glibc_link_numeric_report)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        ap.error("MAP02 private original module import attribution failed")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
