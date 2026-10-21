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



def summarize_high_fanout_relocation_provenance(
        remaining, game_refs, backend_refs, game_relocation_maps,
        *, minimum_callers=8):
    """Count exact known relocation classes and source sections, not semantics.

    A relocation being inside '.rela.text' proves an ELF code-section patch,
    NOT that the target symbol itself is a function. All private names stay
    in process only; the returned dictionary has fixed numeric field names.
    """
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_relocation_maps)):
        raise ValueError("MAP02 relocation provenance object inventory invalid")
    remaining = set(remaining)
    game = [set(refs) & remaining for refs in game_refs]
    backend = set().union(*(set(refs) & remaining for refs in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    type_names = ("pc32", "plt32", "abs32", "abs32s", "abs64",
                  "gotpcrel", "other")
    section_names = ("text", "rodata", "data", "unwind", "other")
    type_counts = {name: 0 for name in type_names}
    section_counts = {name: 0 for name in section_names}
    with_other = 0
    mixed_text = 0
    nontext_only = 0
    no_record = 0
    selected = 0
    for symbol in game_only:
        users = [i for i, refs in enumerate(game) if symbol in refs]
        if len(users) < minimum_callers:
            continue
        selected += 1
        rows = [row for i in users
                for row in game_relocation_maps[i].get(symbol, ())]
        if not rows:
            no_record += 1
            continue
        saw_text = False
        saw_nontext = False
        saw_non_pc32 = False
        for kind, section in rows:
            if kind == "R_X86_64_PC32":
                ty = "pc32"
            elif kind == "R_X86_64_PLT32":
                ty = "plt32"
            elif kind == "R_X86_64_32":
                ty = "abs32"
            elif kind == "R_X86_64_32S":
                ty = "abs32s"
            elif kind == "R_X86_64_64":
                ty = "abs64"
            elif kind in (
                    "R_X86_64_GOTPCREL", "R_X86_64_GOTPCRELX",
                    "R_X86_64_REX_GOTPCRELX"):
                ty = "gotpcrel"
            else:
                ty = "other"
            type_counts[ty] += 1
            if ty not in ("pc32", "plt32"):
                saw_non_pc32 = True

            if section.startswith((".rela.text", ".rel.text")):
                sec = "text"
                saw_text = True
            elif section.startswith((".rela.rodata", ".rel.rodata")):
                sec = "rodata"
                saw_nontext = True
            elif section.startswith((".rela.data", ".rel.data",
                                    ".rela.bss", ".rel.bss")):
                sec = "data"
                saw_nontext = True
            elif section.startswith((".rela.eh_frame", ".rel.eh_frame",
                                    ".rela.gcc_except_table",
                                    ".rel.gcc_except_table")):
                sec = "unwind"
                saw_nontext = True
            else:
                sec = "other"
                saw_nontext = True
            section_counts[sec] += 1
        with_other += saw_non_pc32
        mixed_text += saw_text and saw_nontext
        nontext_only += saw_nontext and not saw_text
    records = sum(type_counts.values())
    if (records != sum(section_counts.values())
            or with_other > selected - no_record
            or mixed_text + nontext_only > selected - no_record
            or not 0 <= no_record <= selected):
        raise ValueError("MAP02 relocation provenance category totals inconsistent")
    return {
        "high_fanout_provenance_imports": selected,
        **{"high_fanout_provenance_" + name + "_records": value
           for name, value in type_counts.items()},
        **{"high_fanout_provenance_section_" + name + "_records": value
           for name, value in section_counts.items()},
        "high_fanout_provenance_any_non_pc32_plt32_imports": with_other,
        "high_fanout_provenance_both_text_nontext_imports": mixed_text,
        "high_fanout_provenance_nontext_only_imports": nontext_only,
        "high_fanout_provenance_without_relocation_records": no_record,
        "high_fanout_provenance_total_records": records,
        "source_section_and_relocation_type_do_not_prove_runtime_abi": True,
    }



def parse_readelf_abs64_data_patch_offsets(readelf_output):
    """Exact absolute 64-bit relocation patch offsets inside data sections.

    Keys remain owner-private. Offsets are *source-object-relative* and never
    become public, even when the originating ELF is entirely asset-free.
    """
    found = {}
    section = None
    for line in readelf_output.splitlines():
        entry = line.strip()
        if entry.startswith("Relocation section '"):
            bits = entry.split("'")
            if len(bits) < 3:
                raise ValueError("MAP02 ABS64 native relocation header invalid")
            section = bits[1]
            continue
        fields = entry.split()
        if (section and len(fields) >= 5 and fields[2] == "R_X86_64_64"):
            if not section.startswith((".rela.data", ".rel.data")):
                continue
            if (not fields[0]
                    or any(char not in "0123456789abcdefABCDEF"
                           for char in fields[0])):
                raise ValueError("MAP02 ABS64 patch offset malformed")
            symbol, offset = fields[4], int(fields[0], 16)
            found.setdefault(symbol, []).append((section, offset))
    return found


def summarize_high_fanout_abs64_patch_layout(
        remaining, game_refs, backend_refs, game_abs64_offsets,
        *, minimum_callers=8):
    """Summarize pointer-width patch locality; not pointer/function semantics."""
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_abs64_offsets)):
        raise ValueError("MAP02 ABS64 patch origin inventory invalid")
    remaining = set(remaining)
    game = [set(names) & remaining for names in game_refs]
    backend = set().union(*(set(names) & remaining for names in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    wide = {symbol for symbol in game_only
            if sum(symbol in refs for refs in game) >= minimum_callers}

    relevant_names = set()
    object_indices = set()
    data_sections = set()
    total = 0
    aligned = 0
    contiguous_pairs = 0
    longest_run = 0
    maximum_in_one_object = 0
    # Each object/section has independent offsets. They cannot be pooled
    # without creating fake 8-byte adjacency across unrelated data segments.
    for index, per_symbol in enumerate(game_abs64_offsets):
        in_this_object = 0
        for name, patches in per_symbol.items():
            if name not in wide:
                continue
            if not name in game[index]:
                raise ValueError("MAP02 ABS64 patch has no matching original game import")
            relevant_names.add(name)
            groups = {}
            for section, offset in patches:
                if (not section.startswith((".rela.data", ".rel.data"))
                        or type(offset) is not int or offset < 0):
                    raise ValueError("MAP02 ABS64 patch section or offset invalid")
                groups.setdefault(section, []).append(offset)
                data_sections.add((index, section))
                total += 1
                in_this_object += 1
                aligned += (offset % 8 == 0)
            for locations in groups.values():
                if len(locations) != len(set(locations)):
                    raise ValueError("MAP02 duplicate ABS64 patch offset within source section")
                points = sorted(locations)
                run = 1
                longest_run = max(longest_run, run)
                for pos in range(1, len(points)):
                    if points[pos] - points[pos - 1] == 8:
                        contiguous_pairs += 1
                        run += 1
                    else:
                        run = 1
                    longest_run = max(longest_run, run)
        if in_this_object:
            object_indices.add(index)
            maximum_in_one_object = max(maximum_in_one_object, in_this_object)
    if (total < len(relevant_names)
            or not 0 <= contiguous_pairs <= max(0, total - 1)
            or not 0 <= aligned <= total
            or not 0 <= longest_run <= total
            or (total == 0 and (relevant_names or object_indices
                                or maximum_in_one_object or longest_run))):
        raise ValueError("MAP02 ABS64 patch layout arithmetic inconsistent")
    return {
        "high_fanout_abs64_data_records": total,
        "high_fanout_abs64_data_symbol_names": len(relevant_names),
        "high_fanout_abs64_data_source_objects": len(object_indices),
        "high_fanout_abs64_data_source_sections": len(data_sections),
        "high_fanout_abs64_data_aligned_eight_byte_records": aligned,
        "high_fanout_abs64_data_adjacent_eight_byte_pairs": contiguous_pairs,
        "high_fanout_abs64_data_longest_eight_byte_run": longest_run,
        "high_fanout_abs64_data_max_records_in_one_source_object":
            maximum_in_one_object,
        "patch_offset_adjacency_does_not_prove_runtime_pointer_table": True,
    }



def summarize_high_fanout_abs64_patch_gaps(
        remaining, game_refs, backend_refs, game_abs64_offsets,
        *, minimum_callers=8):
    """Numeric gap histogram for source-sealed ABS64 data patches only.

    Never join relocation offsets from different original ELF objects,
    different data sections, or different names. Numeric histogram does not
    identify a C structure layout or prove runtime use.
    """
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_abs64_offsets)):
        raise ValueError("MAP02 ABS64 gap input object count invalid")
    remaining = set(remaining)
    game = [set(names) & remaining for names in game_refs]
    backend = set().union(*(set(names) & remaining for names in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    wide = {name for name in game_only
            if sum(name in refs for refs in game) >= minimum_callers}
    bins = {"8": 0, "16": 0, "24": 0, "32": 0, "40_to_64": 0,
            "over_64": 0, "non_multiple_8": 0}
    counts_per_object = []
    total = 0
    sections = 0
    smallest_positive_gap = None
    singleton_sections = 0
    for index, symbols in enumerate(game_abs64_offsets):
        owned_count = 0
        for name, patches in symbols.items():
            if name not in wide:
                continue
            if name not in game[index]:
                raise ValueError("MAP02 ABS64 gap name has no source import")
            groups = {}
            for section, offset in patches:
                if (not section.startswith((".rela.data", ".rel.data"))
                        or type(offset) is not int or offset < 0):
                    raise ValueError("MAP02 ABS64 gap relocation invalid")
                groups.setdefault(section, []).append(offset)
                owned_count += 1
                total += 1
            for locations in groups.values():
                if len(locations) != len(set(locations)):
                    raise ValueError("MAP02 duplicate ABS64 gap offset in data section")
                sections += 1
                singleton_sections += len(locations) == 1
                sorted_offsets = sorted(locations)
                for left, right in zip(sorted_offsets, sorted_offsets[1:]):
                    delta = right - left
                    if delta <= 0:
                        raise ValueError("MAP02 nonpositive ABS64 relocation gap")
                    if smallest_positive_gap is None:
                        smallest_positive_gap = delta
                    else:
                        smallest_positive_gap = min(smallest_positive_gap, delta)
                    if delta % 8:
                        bins["non_multiple_8"] += 1
                    elif delta in (8, 16, 24, 32):
                        bins[str(delta)] += 1
                    elif delta <= 64:
                        bins["40_to_64"] += 1
                    else:
                        bins["over_64"] += 1
        if owned_count:
            counts_per_object.append(owned_count)
    ordered = sorted(counts_per_object, reverse=True)
    gap_total = sum(bins.values())
    if (gap_total != total - sections
            or (not total and (sections or ordered or smallest_positive_gap is not None))
            or (total > 0 and not ordered)
            or sum(ordered) != total
            or not 0 <= singleton_sections <= sections):
        raise ValueError("MAP02 ABS64 gap histogram consistency failed")
    return {
        "high_fanout_abs64_gap_total_records": total,
        "high_fanout_abs64_gap_source_objects": len(ordered),
        "high_fanout_abs64_gap_source_sections": sections,
        "high_fanout_abs64_gap_adjacent_site_pairs": gap_total,
        **{"high_fanout_abs64_gap_" + key: value for key, value in bins.items()},
        "high_fanout_abs64_gap_singleton_sections": singleton_sections,
        "high_fanout_abs64_gap_largest_source_object_records":
            ordered[0] if ordered else 0,
        "high_fanout_abs64_gap_second_largest_source_object_records":
            ordered[1] if len(ordered) > 1 else 0,
        "high_fanout_abs64_gap_smallest_positive_distance_bytes":
            smallest_positive_gap or 0,
        "offset_gaps_do_not_identify_c_struct_or_executed_game": True,
    }



def parse_readelf_abs64_data_patch_addends(readelf_output):
    """Read actual ELF RELA addends without disclosing any values publicly.

    GNU readelf -rW renders addends as hexadecimal without a 0x prefix.
    They are signed by the separate '+' or '-' column. For a specific symbol
    this patch-site record is source-file metadata, not a runtime target.
    """
    records = {}
    section = None
    for line in readelf_output.splitlines():
        raw = line.strip()
        if raw.startswith("Relocation section '"):
            parts = raw.split("'")
            if len(parts) < 3:
                raise ValueError("MAP02 native ABS64 addend section header invalid")
            section = parts[1]
            continue
        fields = raw.split()
        if (section and len(fields) >= 3
                and fields[2] == "R_X86_64_64"
                and section.startswith((".rela.data", ".rel.data"))):
            if (len(fields) != 7 or fields[5] not in ("+", "-")
                    or not fields[0]
                    or any(c not in "0123456789abcdefABCDEF" for c in fields[0])
                    or not fields[6]
                    or any(c not in "0123456789abcdefABCDEF" for c in fields[6])):
                raise ValueError("MAP02 native ABS64 addend encoding invalid")
            sign = 1 if fields[5] == "+" else -1
            records.setdefault(fields[4], []).append(
                (section, int(fields[0], 16), sign * int(fields[6], 16)))
    return records


def summarize_high_fanout_abs64_target_addends(
        remaining, game_refs, backend_refs, game_addends, game_patch_offsets,
        *, minimum_callers=8):
    """Global addend multiplicity among only independently proven wide imports."""
    if (type(minimum_callers) is not int or minimum_callers < 2
            or len(game_refs) != len(game_addends)
            or len(game_refs) != len(game_patch_offsets)):
        raise ValueError("MAP02 ABS64 target addend source inventory invalid")
    remaining = set(remaining)
    game = [set(x) & remaining for x in game_refs]
    backend = set().union(*(set(x) & remaining for x in backend_refs))
    game_only = (set().union(*game) if game else set()) - backend
    wide = {name for name in game_only
            if sum(name in refs for refs in game) >= minimum_callers}
    values = {}
    records = 0
    zero = 0
    negative = 0
    aligned = 0
    objects = set()
    selected_symbols = set()
    per_object_values = []
    for i, mapping in enumerate(game_addends):
        object_values = {}
        for name, rows in mapping.items():
            if name not in wide:
                continue
            if name not in game[i]:
                raise ValueError("MAP02 ABS64 addend has no original caller")
            expected = sorted(game_patch_offsets[i].get(name, ()))
            actual = sorted((section, pos) for section, pos, _ in rows)
            if actual != expected:
                raise ValueError("MAP02 ABS64 addend patch-offset evidence differs")
            if rows:
                objects.add(i)
                selected_symbols.add(name)
            for section, offset, addend in rows:
                if (not section.startswith((".rela.data", ".rel.data"))
                        or type(offset) is not int or offset < 0
                        or type(addend) is not int):
                    raise ValueError("MAP02 ABS64 addend patch metadata invalid")
                records += 1
                zero += addend == 0
                negative += addend < 0
                aligned += addend % 8 == 0
                values[addend] = values.get(addend, 0) + 1
                object_values[addend] = object_values.get(addend, 0) + 1
        if object_values:
            per_object_values.append(object_values)
    # A missing addend witness in an object holding source patch offsets
    # must not silently pass merely because other objects include that name.
    for i, mapping in enumerate(game_patch_offsets):
        for name, patches in mapping.items():
            if name in wide and patches and name not in game_addends[i]:
                raise ValueError("MAP02 missing ABS64 addend witness in original object")
    repeated_values = [n for n in values.values() if n >= 2]
    duplicate_records = sum(repeated_values)
    object_frequency = {}
    within_object_repeated_values = set()
    within_object_reused_records = 0
    maximum_same_value_in_one_object = 0
    distinct_values_per_object = []
    for object_values in per_object_values:
        distinct_values_per_object.append(len(object_values))
        maximum_same_value_in_one_object = max(
            maximum_same_value_in_one_object,
            max(object_values.values(), default=0))
        for value, count in object_values.items():
            object_frequency[value] = object_frequency.get(value, 0) + 1
            if count >= 2:
                within_object_repeated_values.add(value)
                within_object_reused_records += count
    cross_object_values = {
        value for value, count in object_frequency.items() if count > 1}
    cross_object_records = sum(values[value] for value in cross_object_values)
    if (sum(values.values()) != records or not 0 <= zero <= records
            or not 0 <= negative <= records or not 0 <= aligned <= records
            or not 0 <= duplicate_records <= records
            or not 0 <= within_object_reused_records <= records
            or not 0 <= cross_object_records <= records
            or len(per_object_values) != len(objects)
            or (per_object_values and
                not 1 <= min(distinct_values_per_object)
                <= max(distinct_values_per_object) <= records)):
        raise ValueError("MAP02 ABS64 target addend arithmetic inconsistent")
    return {
        "high_fanout_abs64_addend_total_records": records,
        "high_fanout_abs64_addend_source_objects": len(objects),
        "high_fanout_abs64_addend_symbol_names": len(selected_symbols),
        "high_fanout_abs64_addend_distinct_values": len(values),
        "high_fanout_abs64_addend_zero_records": zero,
        "high_fanout_abs64_addend_negative_records": negative,
        "high_fanout_abs64_addend_eight_aligned_records": aligned,
        "high_fanout_abs64_addend_distinct_repeated_values":
            len(repeated_values),
        "high_fanout_abs64_addend_records_with_reused_values":
            duplicate_records,
        "high_fanout_abs64_addend_max_records_sharing_one_value":
            max(values.values(), default=0),
        "high_fanout_abs64_addend_values_repeated_within_source_object":
            len(within_object_repeated_values),
        "high_fanout_abs64_addend_records_reused_within_source_object":
            within_object_reused_records,
        "high_fanout_abs64_addend_values_shared_across_source_objects":
            len(cross_object_values),
        "high_fanout_abs64_addend_records_with_cross_object_shared_values":
            cross_object_records,
        "high_fanout_abs64_addend_max_records_same_value_in_one_object":
            maximum_same_value_in_one_object,
        "high_fanout_abs64_addend_min_distinct_values_per_source_object":
            min(distinct_values_per_object, default=0),
        "high_fanout_abs64_addend_max_distinct_values_per_source_object":
            max(distinct_values_per_object, default=0),
        "addend_multiplicity_does_not_prove_game_data_structure": True,
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
        game_abs64_patch_maps = []
        game_abs64_addend_maps = []
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
                    game_abs64_patch_maps.append(
                        parse_readelf_abs64_data_patch_offsets(relocation.stdout))
                    game_abs64_addend_maps.append(
                        parse_readelf_abs64_data_patch_addends(relocation.stdout))
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
        relocation_provenance = summarize_high_fanout_relocation_provenance(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_reloc_maps)
        abs64_layout = summarize_high_fanout_abs64_patch_layout(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_abs64_patch_maps)
        abs64_gaps = summarize_high_fanout_abs64_patch_gaps(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_abs64_patch_maps)
        abs64_addends = summarize_high_fanout_abs64_target_addends(
            remaining, refs[:EXPECTED_GAME], refs[EXPECTED_GAME:],
            game_abs64_addend_maps, game_abs64_patch_maps)
        if (abs64_addends["high_fanout_abs64_addend_total_records"] !=
                abs64_layout["high_fanout_abs64_data_records"]
                or abs64_addends["high_fanout_abs64_addend_source_objects"] !=
                   abs64_layout["high_fanout_abs64_data_source_objects"]
                or abs64_addends["high_fanout_abs64_addend_symbol_names"] !=
                   abs64_layout["high_fanout_abs64_data_symbol_names"]):
            raise ValueError("MAP02 addend evidence disagrees with proven data relocation layout")
        if (abs64_gaps["high_fanout_abs64_gap_total_records"] !=
                abs64_layout["high_fanout_abs64_data_records"]
                or abs64_gaps["high_fanout_abs64_gap_source_objects"] !=
                   abs64_layout["high_fanout_abs64_data_source_objects"]
                or abs64_gaps["high_fanout_abs64_gap_source_sections"] !=
                   abs64_layout["high_fanout_abs64_data_source_sections"]
                or abs64_gaps["high_fanout_abs64_gap_8"] !=
                   abs64_layout["high_fanout_abs64_data_adjacent_eight_byte_pairs"]
                or abs64_gaps["high_fanout_abs64_gap_largest_source_object_records"] !=
                   abs64_layout["high_fanout_abs64_data_max_records_in_one_source_object"]):
            raise ValueError("MAP02 ABS64 spacing differs from native source patch audit")
        if (abs64_layout["high_fanout_abs64_data_records"] !=
                relocation_provenance["high_fanout_provenance_abs64_records"]
                or abs64_layout["high_fanout_abs64_data_symbol_names"] >
                   relocation_provenance["high_fanout_provenance_any_non_pc32_plt32_imports"]
                or abs64_layout["high_fanout_abs64_data_source_objects"] >
                   EXPECTED_GAME):
            raise ValueError("MAP02 ABS64 native data patch provenance differs")
        if (relocation_provenance["high_fanout_provenance_imports"]
                != reloc_types["high_fanout_game_only_imports_with_relocation_check"]
                or relocation_provenance["high_fanout_provenance_total_records"]
                   != (reloc_types["high_fanout_reloc_plt32_records"] +
                       reloc_types["high_fanout_reloc_pc32_records"] +
                       reloc_types["high_fanout_reloc_other_records"])
                or relocation_provenance["high_fanout_provenance_pc32_records"]
                   != reloc_types["high_fanout_reloc_pc32_records"]
                or relocation_provenance["high_fanout_provenance_plt32_records"]
                   != reloc_types["high_fanout_reloc_plt32_records"]
                or relocation_provenance["high_fanout_provenance_nontext_only_imports"]
                   != reloc_types["high_fanout_only_nontext_relocation_names"]
                or relocation_provenance["high_fanout_provenance_without_relocation_records"]
                   != reloc_types["high_fanout_reloc_no_relocation_record"]):
            raise ValueError("MAP02 native relocation class provenance disagrees")
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
            **relocation_provenance,
            **abs64_layout,
            **abs64_gaps,
            **abs64_addends,
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
