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



def summarize_game_only_fanout(remaining, game_refs, backend_refs):
    """Real distinct caller-object fanout; never disclose symbol names.

    Import fanout measures breadth of references, *not* implementation location
    or runtime use. Repeated undefined relocations in one TU count only once.
    """
    remaining = set(remaining)
    game = [set(x) & remaining for x in game_refs]
    backend = [set(x) & remaining for x in backend_refs]
    game_names = set().union(*game) if game else set()
    backend_names = set().union(*backend) if backend else set()
    game_only = game_names - backend_names
    backend_only = backend_names - game_names
    shared = game_names & backend_names
    bins = {"one": 0, "two_to_three": 0, "four_to_seven": 0,
            "eight_or_more": 0}
    edge_total = 0
    maximum = 0
    for symbol in game_only:
        callers = sum(symbol in refs for refs in game)
        if callers == 0:
            raise ValueError("MAP02 game-only symbol has no actual caller")
        maximum = max(maximum, callers)
        edge_total += callers
        if callers == 1:
            bins["one"] += 1
        elif callers <= 3:
            bins["two_to_three"] += 1
        elif callers <= 7:
            bins["four_to_seven"] += 1
        else:
            bins["eight_or_more"] += 1
    game_shared_pairs = sum(len(refs & shared) for refs in game)
    backend_shared_pairs = sum(len(refs & shared) for refs in backend)
    backend_only_pairs = sum(len(refs & backend_only) for refs in backend)
    game_total_pairs = sum(map(len, game))
    backend_total_pairs = sum(map(len, backend))
    if (sum(bins.values()) != len(game_only)
            or edge_total + game_shared_pairs != game_total_pairs
            or backend_only_pairs + backend_shared_pairs != backend_total_pairs
            or (not game_only and maximum != 0)
            or (game_only and not 1 <= maximum <= len(game))
            or (len(game_only) + len(backend_only) + len(shared) >
                len(remaining))):
        raise ValueError("MAP02 game symbol fanout arithmetic inconsistent")
    return {
        **{"game_only_fanout_" + key: value for key, value in bins.items()},
        "game_only_reference_pairs": edge_total,
        "shared_game_reference_pairs": game_shared_pairs,
        "backend_only_reference_pairs": backend_only_pairs,
        "shared_backend_reference_pairs": backend_shared_pairs,
        "game_only_max_caller_objects_per_symbol": maximum,
        "fanout_counts_distinct_source_objects_not_runtime_calls": True,
    }



def parse_readelf_global_undefined_types(readelf_output):
    """Strictly parse genuine ELF symbol-table TYPE fields, never source syntax.

    NOTYPE is *not* evidence of a function or object. Raw names only exist in
    owner-private memory and must never enter the public JSON or error strings.
    """
    out = {}
    for line in readelf_output.splitlines():
        fields = line.split()
        if (len(fields) < 8 or not fields[0].endswith(":")
                or not fields[0][:-1].isdigit()
                or fields[6] != "UND" or fields[4] != "GLOBAL"):
            continue
        kind, name = fields[3], fields[7]
        if not name or name == "0":
            raise ValueError("MAP02 native readelf undefined name malformed")
        out.setdefault(name, set()).add(kind)
    return out


def summarize_high_fanout_elf_types(remaining, game_refs, backend_refs,
                                   game_type_maps, *, minimum_callers=8):
    """Group only the game-exclusive wide fanout names by recorded ELF type.

    One name can have varying declared types across objects; any FUNC+OBJECT
    conflict is reported as mixed rather than choosing a desired answer.
    """
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_type_maps)):
        raise ValueError("MAP02 high-fanout type input invalid")
    remaining = set(remaining)
    game = [set(refs) & remaining for refs in game_refs]
    backend = set().union(*(set(refs) & remaining for refs in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    bins = {
        "function_marker": 0,
        "object_marker": 0,
        "mixed_function_object": 0,
        "notype_only": 0,
        "other_or_unknown": 0,
    }
    untyped = 0
    selected = 0
    for symbol in game_only:
        users = [index for index, refs in enumerate(game) if symbol in refs]
        if len(users) < minimum_callers:
            continue
        selected += 1
        kinds = set()
        for index in users:
            per_object = game_type_maps[index]
            if symbol not in per_object or not per_object[symbol]:
                raise ValueError("MAP02 wide import has no native ELF type witness")
            kinds.update(per_object[symbol])
        if "FUNC" in kinds and "OBJECT" in kinds:
            bins["mixed_function_object"] += 1
        elif "FUNC" in kinds:
            bins["function_marker"] += 1
        elif "OBJECT" in kinds:
            bins["object_marker"] += 1
        elif kinds == {"NOTYPE"}:
            bins["notype_only"] += 1
        else:
            bins["other_or_unknown"] += 1
        if "NOTYPE" in kinds:
            untyped += 1
    if sum(bins.values()) != selected or untyped > selected:
        raise ValueError("MAP02 high-fanout ELF type arithmetic differs")
    return {
        "high_fanout_game_only_imports": selected,
        **{"high_fanout_elf_" + name: value for name, value in bins.items()},
        "high_fanout_with_any_notype_declaration": untyped,
        "elf_symbol_type_is_not_proof_of_abi_or_runtime_calls": True,
    }



def parse_readelf_relocation_types(readelf_output):
    """Internal only: native ELF relocation symbol -> [(kind, section), ...].

    The relocation *record* proves static reference metadata, not a function
    call or runtime use. Ignore local sections until matched to proven imports.
    """
    records = {}
    section = None
    saw_header = False
    for line in readelf_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Relocation section '"):
            parts = stripped.split("'")
            if len(parts) < 3 or not parts[1].startswith((".rela", ".rel")):
                raise ValueError("MAP02 native relocation section header invalid")
            section = parts[1]
            saw_header = True
            continue
        if not stripped or stripped.startswith(("Offset ", "Offset", "There are no relocations")):
            continue
        fields = stripped.split()
        if (section and len(fields) >= 5
                and all(c in "0123456789abcdefABCDEF" for c in fields[0])
                and fields[2].startswith("R_")):
            kind, name = fields[2], fields[4]
            records.setdefault(name, []).append((kind, section))
    if not saw_header and "There are no relocations" not in readelf_output:
        raise ValueError("MAP02 native relocation output lacked section metadata")
    return records


def summarize_high_fanout_relocations(remaining, game_refs, backend_refs,
                                      game_relocation_maps, *, minimum_callers=8):
    """Disjoint relocation-type presence buckets for game-exclusive imports."""
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_relocation_maps)):
        raise ValueError("MAP02 game relocation source inventory invalid")
    remaining = set(remaining)
    game = [set(x) & remaining for x in game_refs]
    backend = set().union(*(set(x) & remaining for x in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    bucket = {"plt32_only": 0, "pc32_only": 0, "plt32_and_pc32": 0,
              "other_or_mixed": 0, "no_relocation_record": 0}
    kinds_total = {"plt32_records": 0, "pc32_records": 0,
                   "other_records": 0}
    only_nontext = 0
    selected = 0
    for symbol in game_only:
        users = [i for i, refs in enumerate(game) if symbol in refs]
        if len(users) < minimum_callers:
            continue
        selected += 1
        rows = [
            row
            for i in users for row in game_relocation_maps[i].get(symbol, [])
        ]
        if not rows:
            bucket["no_relocation_record"] += 1
            continue
        categories = set()
        for kind, section in rows:
            if kind == "R_X86_64_PLT32":
                categories.add("plt32")
                kinds_total["plt32_records"] += 1
            elif kind == "R_X86_64_PC32":
                categories.add("pc32")
                kinds_total["pc32_records"] += 1
            else:
                categories.add("other")
                kinds_total["other_records"] += 1
        if all(not section.startswith((".rela.text", ".rel.text"))
               for kind, section in rows):
            only_nontext += 1
        if categories == {"plt32"}:
            bucket["plt32_only"] += 1
        elif categories == {"pc32"}:
            bucket["pc32_only"] += 1
        elif categories == {"plt32", "pc32"}:
            bucket["plt32_and_pc32"] += 1
        else:
            bucket["other_or_mixed"] += 1
    if (sum(bucket.values()) != selected
            or only_nontext > selected - bucket["no_relocation_record"]
            or sum(kinds_total.values()) < selected -
               bucket["no_relocation_record"]):
        raise ValueError("MAP02 high-fanout relocation counts inconsistent")
    return {
        "high_fanout_game_only_imports_with_relocation_check": selected,
        **{"high_fanout_reloc_" + k: v for k, v in bucket.items()},
        **{"high_fanout_reloc_" + k: v for k, v in kinds_total.items()},
        "high_fanout_only_nontext_relocation_names": only_nontext,
        "relocation_types_do_not_prove_function_or_data_semantics": True,
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
        game_type_maps = []
        game_reloc_maps = []
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
                if index < EXPECTED_GAME:
                    native = subprocess.run(
                        ["readelf", "-Ws", f"/proc/self/fd/{fd}"],
                        capture_output=True, text=True, check=False,
                        timeout=30, pass_fds=(fd,), umask=0o077,
                        env={k: v for k, v in os.environ.items()
                             if not k.startswith(("LD_", "DYLD_", "PYTHON", "VH_"))})
                    if native.returncode:
                        raise ValueError("MAP02 native object ELF symbol table unavailable")
                    table = parse_readelf_global_undefined_types(native.stdout)
                    required = set(strong) & remaining
                    if not required.issubset(table):
                        raise ValueError("MAP02 native ELF undefined symbol type witness incomplete")
                    game_type_maps.append(table)
                    relocation = subprocess.run(
                        ["readelf", "-rW", f"/proc/self/fd/{fd}"],
                        capture_output=True, text=True, check=False,
                        timeout=30, pass_fds=(fd,), umask=0o077,
                        env={k: v for k, v in os.environ.items()
                             if not k.startswith(("LD_", "DYLD_", "PYTHON", "VH_"))})
                    if relocation.returncode:
                        raise ValueError("MAP02 native object relocation metadata unavailable")
                    game_reloc_maps.append(
                        parse_readelf_relocation_types(relocation.stdout))
            finally:
                os.close(fd)
            if stable_object_input(path) != witness:
                raise ValueError("MAP02 module object changed during symbol census")
        for e in opened:
            _confirm_owned(e)
        output = summarize_owner_groups(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:])
        fanout = summarize_game_only_fanout(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:])
        elf_types = summarize_high_fanout_elf_types(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_type_maps)
        if (elf_types["high_fanout_game_only_imports"] !=
                fanout["game_only_fanout_eight_or_more"]):
            raise ValueError("MAP02 wide game import ELF types differ from actual fanout")
        reloc_types = summarize_high_fanout_relocations(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_reloc_maps)
        if (reloc_types["high_fanout_game_only_imports_with_relocation_check"]
                != elf_types["high_fanout_game_only_imports"]):
            raise ValueError("MAP02 native relocation fanout differs from ELF types")
        if (sum(fanout["game_only_fanout_" + name]
                for name in ("one", "two_to_three", "four_to_seven",
                             "eight_or_more")) != output["original_game_only_imports"]
                or (fanout["game_only_reference_pairs"] +
                    fanout["shared_game_reference_pairs"] !=
                    output["game_object_symbol_reference_pairs"])
                or (fanout["backend_only_reference_pairs"] +
                    fanout["shared_backend_reference_pairs"] !=
                    output["backend_object_symbol_reference_pairs"])):
            raise ValueError("MAP02 fanout and original owner counts diverge")
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
            **fanout,
            **elf_types,
            **reloc_types,
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
