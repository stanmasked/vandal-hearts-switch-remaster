#!/usr/bin/env python3
"""Audit the object files from an asset-free full original PC code compile.

This audits the explicit `map02-public-code` target, NOT `make link`:
it compiles asset-free original game and PC-backend source but never invokes
retail-data-segment generation. No original retail EXE, game BIN, compiled
game executable or rendered MAP02 scene is needed or certified.
"""
import argparse
import json
import os
import re
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, preflight
from tools.prepare_map02_cycle_build import SUPPORT_FILES

MIN_GAME = 80
# Known public source blockers are mandatory; any extra skip requires
# an actual direct assets/ include in the *original* pinned source file.
ASSET_INCLUDES = re.compile(r'^\s*#\s*include\s*"assets/[^"]+"', re.M)
KNOWN_ASSET_IMPORTS = {
    "src/core/text.o": '#include "assets/801012e4.inc"',
    "src/maps/map_32.o": '#include "assets/801009bc.inc"',
    "src/maps/map_35.o": '#include "assets/80100e9c.inc"',
}
MIN_BACKEND = 30
BIOS_FONT_OBJECT = 'pc_kanji_font.o'
REQUIRED = {
    "src/core/cd.o", "libcd.o", "libgpu.o", "pc_raster.o",
    "pc_gpu_window.o", "map02_cycle_order.o", "map02_cd_read_probe.o",
    "map02_capture_session.o", "map02_pc_preoverlay_capture.o",
    "map02_scoped_blend_sink.o",
    "map02_scoped_blend_stage.o", "map02_vram_edges.o",
}
SUPPORT_OBJS = {
    f[:-2] + ".o" for f in SUPPORT_FILES if f.endswith(".c")
}


def audit_objects(upstream, bundle, *, make="make"):
    upstream = Path(upstream).absolute()
    bundle = Path(bundle).absolute()
    preflight(upstream, bundle)
    pc = upstream / "platform/pc"
    obj_root = pc / BUILD
    # This target only expands GNU Make's own *complete* object variable
    # inventories. It does not compile, read retail content, or invoke link.
    listing_target = (
        "map02-private-object-inventory:;@printf '%s\\n' "
        "'$(VH_MAP02_PUBLIC_CODE_OBJS)' '$(VH_MAP02_PUBLIC_BACKEND_OBJS)'"
    )
    result = subprocess.run(
        [make, "-s", "-f", "Makefile", "-f",
         str(bundle / "map02_cycle.mk"), "--eval", listing_target,
         "map02-private-object-inventory", "BUILD_DIR=" + BUILD,
         "REGION=us", "NO_WEBP=1", "NO_HDVIDEO=1"],
        cwd=pc, capture_output=True, text=True, timeout=60, check=False)
    if result.returncode:
        raise ValueError("MAP02 original full-code object inventory failed")
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise ValueError("MAP02 make object inventory is not two lists")
    groups = [line.split() for line in lines]
    game, backend = groups
    if len(game) < MIN_GAME or len(backend) < MIN_BACKEND:
        raise ValueError("original public game/backend object inventory truncated")
    all_items = game + backend
    if len(set(all_items)) != len(all_items):
        raise ValueError("duplicated original PC object in complete Make inventory")
    names = []
    for value in all_items:
        prefix = BUILD + "/"
        if not value.startswith(prefix) or not value.endswith(".o"):
            raise ValueError("original PC object escaped dedicated build directory")
        relative = value[len(prefix):]
        if (not relative or any(part in ("", ".", "..") for part in
                                 relative.split("/"))):
            raise ValueError("invalid original PC object path")
        file = obj_root / relative
        if file.is_symlink() or not file.is_file():
            raise ValueError("missing or linked original PC compiled object: " + relative)
        info = file.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_size < 256):
            raise ValueError("invalid original PC compiled object: " + relative)
        with file.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ValueError("compiled PC object is not an ELF: " + relative)
        names.append(relative)
    sources = [
        source
        for pattern in ("*.c", "*/*.c")
        for source in (upstream / "src").glob(pattern)
    ]
    expected_source_objects = set()
    excluded = {}
    for source in sources:
        if source.is_symlink() or not source.is_file():
            raise ValueError("original public source is linked or missing")
        object_name = ("src/" + source.relative_to(
            upstream / "src").with_suffix(".o").as_posix())
        expected_source_objects.add(object_name)
        content = source.read_text(encoding="utf-8")
        if ASSET_INCLUDES.search(content):
            excluded[object_name] = content
    for name, exact_include in KNOWN_ASSET_IMPORTS.items():
        if exact_include not in excluded.get(name, ""):
            raise ValueError("known original retail asset dependency changed: " + name)
    if set(names[:len(game)]) != expected_source_objects - excluded.keys():
        raise ValueError("public original asset-free game sources were not all compiled")
    for asset_object in excluded:
        if asset_object in names or (obj_root / asset_object).exists():
            raise ValueError("retail-asset-dependent original source must remain uncompiled")
    bios_source = pc / "src/pc_kanji_font.c"
    bios_object = obj_root / BIOS_FONT_OBJECT
    original_make = (pc / "Makefile").read_text(encoding="utf-8")
    if ("src/pc_kanji_font.c:" not in original_make or
            "tools/gen_kanji_font.py" not in original_make):
        raise ValueError("original KROMDAT BIOS font generator dependency changed")
    if (bios_source.exists() or bios_source.is_symlink() or
            bios_object.exists() or bios_object.is_symlink() or
            BIOS_FONT_OBJECT in names):
        raise ValueError("private KROMDAT-derived backend cannot be compiled in public mode")
    if not REQUIRED.issubset(names) or not SUPPORT_OBJS.issubset(names):
        raise ValueError("original CD/GPU/VRAM capture objects missing from full compile")
    actual = {
        file.relative_to(obj_root).as_posix()
        for file in obj_root.rglob("*.o")
    }
    if actual != set(names):
        raise ValueError("full original PC object tree has unlisted or missing objects")
    for forbidden in ("generated_data.c", "generated_data.o",
                      "vandalhearts_pc"):
        if (obj_root / forbidden).exists() or (
                obj_root / forbidden).is_symlink():
            raise ValueError("retail game data or ELF unexpectedly built")
    # Check the *same* upstream and source overlay inputs AFTER inspecting
    # all compiled objects, not only before GNU Make's inventory expansion.
    preflight(upstream, bundle)
    return {
        "schema": "vh.map02.public-pc-asset-free-code-objects.v1",
        "original_asset_bound_translation_units_excluded": sorted(excluded),
        "private_bios_derived_backend_objects_excluded": [BIOS_FONT_OBJECT],
        "original_game_translation_units_compiled": len(game),
        "native_backend_and_observer_objects_compiled": len(backend),
        "source_pinned_build_inputs_rechecked": True,
        "retail_game_data_generated": False,
        "full_game_elf_linked": False,
        "actual_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_pc_checkout", type=Path)
    parser.add_argument("private_overlay_bundle", type=Path)
    args = parser.parse_args()
    try:
        report = audit_objects(args.pinned_pc_checkout,
                               args.private_overlay_bundle)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
