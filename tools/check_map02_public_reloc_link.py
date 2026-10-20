#!/usr/bin/env python3
"""Relocatable-link all verified asset-free original PC code and MAP02 observers.

This is intentionally *not* a complete executable: the pinned public port
requires user-owned retail assets and PsyQ KROMDAT for four omitted objects.
Only the 85 public game modules and 32 backend/diagnostic objects are linked
by ld -r. Undefined ordinary original-game symbols are expected; unresolved
vh_map02_ observer symbols, missing original API exports, source drift or a
linked executable fail closed. No original image or private journal is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, preflight, clean_make_environment
from tools.check_map02_cycle_object_inventory import audit_objects

OUTPUT = "map02-public-original-cd-gpu-reloc.o"
REQUIRED_SYMBOLS = (
    "LoadCdFile", "ContinueLoadingCdFile", "CdRead", "DrawOTag",
    "vh_map02_cycle_load", "vh_map02_cycle_draw_start",
    "vh_map02_cd_read_finish", "vh_map02_stage_private_pair",
    "vh_map02_scope_begin_frame", "vh_map02_edges_begin_frame",
    "vh_map02_pc_capture_preoverlay",
)


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def make_inventory(upstream, bundle, *, make="make"):
    pc = Path(upstream).absolute() / "platform/pc"
    overlay = Path(bundle).absolute() / "map02_cycle.mk"
    eval_target = (
        "map02-public-reloc-inventory:;@printf '%s\\n' "
        "'$(VH_MAP02_PUBLIC_CODE_OBJS)' "
        "'$(VH_MAP02_PUBLIC_BACKEND_OBJS)'"
    )
    result = subprocess.run(
        [make, "-s", "-f", "Makefile", "-f", str(overlay),
         "--eval", eval_target, "map02-public-reloc-inventory",
         "BUILD_DIR=" + BUILD, "REGION=us", "NO_WEBP=1",
         "NO_HDVIDEO=1"],
        cwd=pc, env=clean_make_environment(), capture_output=True,
        text=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError("original public code Make inventory unavailable")
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise ValueError("original game/backend GNU Make inventories incomplete")
    return [line.split() for line in lines]


def inspect_relocatable(path):
    header = subprocess.run(
        ["readelf", "-h", str(path)], capture_output=True,
        text=True, timeout=30, check=False)
    if header.returncode or not re.search(
            r"^\s*Type:\s+REL\s", header.stdout, re.M):
        raise ValueError("public code proof must be a relocatable ELF, not a game")
    exports = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    undefined = subprocess.run(
        ["nm", "-u", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    if exports.returncode or undefined.returncode:
        raise ValueError("cannot examine linked original code symbols")
    defined = [
        line.split()[-1] for line in exports.stdout.splitlines()
        if len(line.split()) >= 2
    ]
    if any(defined.count(name) != 1 for name in REQUIRED_SYMBOLS):
        raise ValueError("original CD/GPU or in-process observer export absent/duplicated")
    if any(re.search(r"\bU\s+vh_map02_\w+", line)
           for line in undefined.stdout.splitlines()):
        raise ValueError("combined original PC code has unresolved MAP02 observer hooks")
    return {
        "original_cd_gpu_and_vram_exports_verified": len(REQUIRED_SYMBOLS),
        "ordinary_game_or_private_asset_symbols_may_be_unresolved": True,
    }


def audit_public_link(upstream, bundle, out_dir, *, make="make", linker="ld"):
    upstream = Path(upstream).absolute()
    bundle = Path(bundle).absolute()
    out_dir = Path(out_dir).absolute()
    preflight(upstream, bundle)
    before = audit_objects(upstream, bundle, make=make)
    objects = make_inventory(upstream, bundle, make=make)
    if len(objects[0]) != before["original_game_translation_units_compiled"] or (
            len(objects[1]) != before["native_backend_and_observer_objects_compiled"]):
        raise ValueError("expanded original code inventory differs from audited objects")
    names = objects[0] + objects[1]
    if len(set(names)) != len(names):
        raise ValueError("duplicate original object in relocatable input list")
    root = upstream / "platform/pc"
    root_build = root / BUILD
    sources = []
    for name in names:
        candidate = root / name
        if (not name.startswith(BUILD + "/") or not name.endswith(".o")
                or any(x in ("", ".", "..") for x in name.split("/"))
                or candidate.is_symlink() or not candidate.is_file()
                or root_build not in candidate.parents):
            raise ValueError("invalid original object passed to partial linker")
        sources.append(candidate)
    initial = [digest(path) for path in sources]
    if (out_dir == upstream or upstream in out_dir.parents
            or out_dir.exists() or out_dir.is_symlink()):
        raise ValueError("original partial link requires a NEW private external directory")
    out_dir.mkdir(mode=0o700)
    if (out_dir.stat().st_uid != os.geteuid()
            or stat.S_IMODE(out_dir.stat().st_mode) != 0o700):
        raise ValueError("relocatable output directory not owner-only 0700")
    output = out_dir / OUTPUT
    combined = subprocess.run(
        [linker, "-r", "-o", str(output), *map(str, sources)],
        cwd=root, capture_output=True, text=True, timeout=150,
        check=False)
    if combined.returncode:
        # This is an intentionally incomplete original code link; any
        # failure is a genuine issue, not proof of game correctness.
        # Linker diagnostics can include private checkout locations and
        # arguments. Keep stderr out of the public audit/CLI output.
        raise ValueError("original public CD/GPU combined ld -r link failed")
    if output.is_symlink() or not output.is_file():
        raise ValueError("missing original public relocatable output")
    output.chmod(0o600)
    if output.stat().st_size < 1024:
        raise ValueError("original public relocatable ELF was unexpectedly short")
    checked = inspect_relocatable(output)
    if [digest(path) for path in sources] != initial:
        raise ValueError("original PC objects changed during public partial link")
    if audit_objects(upstream, bundle, make=make) != before:
        raise ValueError("pinned original public source/code inventory changed")
    preflight(upstream, bundle)
    return {
        "schema": "vh.map02.public-source-partial-elf-link.v1",
        "public_game_object_count": len(objects[0]),
        "backend_and_observer_object_count": len(objects[1]),
        "relocatable_elf_sha256": digest(output),
        **checked,
        "fully_linked_game_executable": False,
        "retail_game_assets_linked": False,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_original_pc_checkout", type=Path)
    parser.add_argument("private_prepared_bundle", type=Path)
    parser.add_argument("new_private_output_directory", type=Path)
    args = parser.parse_args()
    try:
        result = audit_public_link(
            args.pinned_original_pc_checkout, args.private_prepared_bundle,
            args.new_private_output_directory)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Avoid exposing private paths via tool or filesystem exceptions.
        parser.error("MAP02 public relocatable audit failed")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
