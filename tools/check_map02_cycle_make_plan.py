#!/usr/bin/env python3
"""Audit the COMPLETE pinned PC-port Make link graph without running it.

Requires an already prepared private map02_cycle.mk bundle. Executes only
GNU Make dry-run (-n): no retail executable/image, generated game data, or
game binary is read/produced. Validates the final link includes original
game modules, generated data and every CD/GPU/VRAM observer, not just an
isolated `ld -r` group. Does NOT attest full-game link success or gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import shlex
import stat
import subprocess

from tools.prepare_map02_pcport import (
    PINNED_BLOB_SHA1, git_blob_sha1,
)
from tools.prepare_map02_cycle_build import (SOURCE_MAP, SUPPORT_FILES,
    FONT_GENERATOR, FONT_GENERATOR_BLOB_SHA1, FONT_GENERATOR_SNAPSHOT)

SCHEMA = "vh.map02.private-single-elf-build-inputs.v1"
OUTPUT_NAME = "vandalhearts_pc"
BUILD = "build-map02-cycle"
REQUIRED_OBJECTS = (
    "src/core/cd.o", "src/core/graphics.o",
    "libcd.o", "libgpu.o", "pc_raster.o",
    "generated_data.o", "pc_battle_data.o", "pc_string_table.o",
    "map02_cycle_order.o", "map02_cd_read_probe.o",
    "map02_capture_session.o", "map02_scoped_blend_sink.o",
    "map02_scoped_blend_stage.o", "map02_vram_edges.o",
)
REQUIRED_COPY_OBJECTS = (
    ("core_cd.c", "src/core/cd.o"),
    ("libcd.c", "libcd.o"),
    ("libgpu.c", "libgpu.o"),
    ("pc_raster.c", "pc_raster.o"),
)
MACROS = (
    "-DVH_MAP02_CYCLE_ORDER", "-DVH_MAP02_CD_READ_PROBE",
    "-DVH_MAP02_GPU_CAPTURE", "-DVH_MAP02_POSIX_CAPTURE_WINDOWS",
    "-DVH_MAP02_SCOPED_BLEND_PROBE", "-DVH_MAP02_VRAM_EDGE_PROBE",
    "-DVH_MAP02_POSIX_STAGE", "-DVH_MAP02_CAPTURE_SESSION",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_read(folder, name):
    path = folder / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("source-bound private build input missing or symlinked: " + name)
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("private MAP02 build input not owner-only 0600: " + name)
    return path.read_bytes()


def preflight(upstream, output):
    upstream = Path(upstream).absolute()
    output = Path(output).absolute()
    if upstream.is_symlink() or not upstream.is_dir():
        raise ValueError("pinned original PC checkout missing or symlinked")
    if output.is_symlink() or not output.is_dir():
        raise ValueError("MAP02 private prepared bundle missing or symlinked")
    if output.stat().st_uid != os.geteuid() or (
            stat.S_IMODE(output.stat().st_mode) != 0o700):
        raise ValueError("MAP02 private prepared bundle must be owner 0700")
    if output.resolve() == upstream.resolve() or upstream.resolve() in output.resolve().parents:
        raise ValueError("private MAP02 bundle must live outside checkout")
    makefile = upstream / "platform/pc/Makefile"
    original_make = makefile.read_bytes()
    if makefile.is_symlink() or (
            git_blob_sha1(original_make) !=
            PINNED_BLOB_SHA1["platform/pc/Makefile"]):
        raise ValueError("MAP02 original Makefile differs from pinned")
    manifest = json.loads(private_read(output, "map02_cycle_build_inputs.json"))
    if (type(manifest) is not dict or manifest.get("schema") != SCHEMA or
            manifest.get("retail_gameplay_executed") is not False or
            manifest.get("original_map02_rendering_proven") is not False or
            manifest.get("physical_ps1_equivalence_proven") is not False or
            manifest.get("upstream_makefile_sha256") != sha(original_make)):
        raise ValueError("invalid prepared MAP02 build provenance")
    files = manifest.get("generated_files_sha256")
    expected = set(SOURCE_MAP) | set(SUPPORT_FILES) | {"map02_cycle.mk", FONT_GENERATOR_SNAPSHOT}
    if type(files) is not dict or set(files) != expected:
        raise ValueError("prepared MAP02 bundle has missing or extra generated input")
    if set(p.name for p in output.iterdir()) != expected | {
            "map02_cycle_build_inputs.json"}:
        raise ValueError("private MAP02 build directory contains unapproved file")
    for name in sorted(expected):
        if (type(files[name]) is not str or
                len(files[name]) != 64 or
                sha(private_read(output, name)) != files[name]):
            raise ValueError("prepared MAP02 build input bytes changed: " + name)
    originals = manifest.get("original_source_sha256")
    if type(originals) is not dict or set(originals) != (
            {item[0] for item in SOURCE_MAP.values()} | {FONT_GENERATOR}):
        raise ValueError("incorrect original PC source inventory")
    for relative in originals:
        path = upstream / relative
        if path.is_symlink() or not path.is_file() or (
                sha(path.read_bytes()) != originals[relative]):
            raise ValueError("original pinned PC source changed: " + relative)
        pinned = (FONT_GENERATOR_BLOB_SHA1 if relative == FONT_GENERATOR
                  else next((blob for rel, blob, _ in SOURCE_MAP.values()
                             if rel == relative), None))
        if pinned is None or git_blob_sha1(path.read_bytes()) != pinned:
            raise ValueError("original PC source no longer matches pinned Git blob: " +
                             relative)
    if (sha(private_read(output, FONT_GENERATOR_SNAPSHOT)) !=
            originals[FONT_GENERATOR]):
        raise ValueError("original pinned font generator snapshot changed")
    return output / "map02_cycle.mk"


def verify_dry_run(text, output):
    """Parse ONLY the final link and four patched compile recipes."""
    # Original GNU Make emits the multi-line CC link recipe with \\ continuations.
    normalized = text.replace("\\\n", " ")
    commands = [line.strip() for line in normalized.splitlines()]
    link_cmds = []
    for line in commands:
        if not line or " -o " not in line:
            continue
        try:
            fields = shlex.split(line)
        except ValueError:
            continue
        target = BUILD + "/" + OUTPUT_NAME
        if "-o" in fields and fields.index("-o") + 1 < len(fields) and (
                fields[fields.index("-o") + 1] == target):
            link_cmds.append(fields)
    if len(link_cmds) != 1:
        raise ValueError("full original PC game link command missing or duplicated")
    link = link_cmds[0]
    missing = [item for item in REQUIRED_OBJECTS if
               link.count(BUILD + "/" + item) != 1]
    if missing:
        raise ValueError("final game linker excludes original CD/GPU/data observer: " +
                         ", ".join(missing))
    if len([item for item in link if item.startswith(BUILD + "/") and
            item.endswith(".o")]) < len(REQUIRED_OBJECTS) + 80:
        raise ValueError("complete original game object inventory missing")
    for generated, obj in REQUIRED_COPY_OBJECTS:
        matches = [line for line in commands if
                   str(output / generated) in line and
                   "-o " + BUILD + "/" + obj in line]
        if len(matches) != 1:
            raise ValueError("original MAP02 translation unit missing private source: " +
                             generated)
    # Verify the font cannot be generated by the mutable original checkout
    # script; only the immutable 0600 bundle snapshot is accepted.
    pinned_font = str(output / FONT_GENERATOR_SNAPSHOT)
    font_output = BUILD + "/map02_pinned_kanji_font.c"
    font_gen = [line for line in commands if
                pinned_font in line and
                "VH_GENERATED_OUT=" + font_output in line and
                "python3 " in line]
    font_compile = [line for line in commands if
                    " -o " + BUILD + "/pc_kanji_font.o " in line and
                    " -c " in line and font_output in line]
    if len(font_gen) != 1 or len(font_compile) != 1:
        raise ValueError("private pinned KROM generator/compile plan missing")
    if any("python3 tools/gen_kanji_font.py" in line or
           "src/pc_kanji_font.c" in line and " -c " in line
           for line in commands):
        raise ValueError("original unpinned KROM generation present in game plan")
    all_text = "\n".join(commands)
    for item in MACROS:
        if item not in all_text:
            raise ValueError("missing original MAP02 diagnostics flag in compile plan: " + item)
    if "-lwebp" in link or any(part.startswith("-lav") for part in link):
        raise ValueError("HD codec libraries unexpectedly active in cycle link")
    return {
        "schema": "vh.map02.full-game-make-dry-run.v1",
        "original_and_diagnostic_required_objects": len(REQUIRED_OBJECTS),
        "private_source_compile_rules_verified": len(REQUIRED_COPY_OBJECTS),
        "private_pinned_font_generation_verified": True,
        "full_game_link_command_sha256": sha(" ".join(link).encode("utf-8")),
        "dry_run_only": True,
        "fully_linked_executable_created": False,
        "retail_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }


def audit(upstream, output, *, make="make"):
    overlay = preflight(upstream, output)
    pc = Path(upstream).absolute() / "platform/pc"
    result = subprocess.run(
        [make, "-nB", "-f", "Makefile", "-f", str(overlay),
         "link", "BUILD_DIR=" + BUILD, "REGION=us",
         "NO_WEBP=1", "NO_HDVIDEO=1"],
        cwd=pc, capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise ValueError(
            "full original PC Make dry-run failed (no game binary built): " +
            result.stderr[-1200:])
    return verify_dry_run(result.stdout, Path(output).absolute())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_original_pc_checkout", type=Path)
    p.add_argument("prepared_private_bundle", type=Path)
    args = p.parse_args()
    try:
        report = audit(args.pinned_original_pc_checkout,
                       args.prepared_private_bundle)
    except (OSError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
