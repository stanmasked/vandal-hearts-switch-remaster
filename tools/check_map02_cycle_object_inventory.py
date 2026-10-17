#!/usr/bin/env python3
"""Audit the object files from an asset-free full original PC code compile.

This intentionally verifies `make default`, NOT `make link`: the former
compiles all original public game and PC-backend source but does not invoke
retail-data-segment generation. No original retail EXE, game BIN, compiled
game executable or rendered MAP02 scene is needed or certified.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

from tools.check_map02_cycle_make_plan import BUILD, preflight
from tools.prepare_map02_cycle_build import SUPPORT_FILES

MIN_GAME = 80
MIN_BACKEND = 30
REQUIRED = {
    "src/core/cd.o", "libcd.o", "libgpu.o", "pc_raster.o",
    "map02_cycle_order.o", "map02_cd_read_probe.o",
    "map02_capture_session.o", "map02_scoped_blend_sink.o",
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
        "'$(GAME_O_FILES)' '$(BACKEND_OBJS)'"
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
            if stream.read(4) != b"\\x7fELF":
                raise ValueError("compiled PC object is not an ELF: " + relative)
        names.append(relative)
    expected_source_objects = {
        "src/" + source.relative_to(upstream / "src").with_suffix(".o").as_posix()
        for pattern in ("*.c", "*/*.c")
        for source in (upstream / "src").glob(pattern)
    }
    if set(names[:len(game)]) != expected_source_objects:
        raise ValueError("original public game C sources were not all compiled")
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
        "schema": "vh.map02.public-pc-all-original-code-objects.v1",
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
