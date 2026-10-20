#!/usr/bin/env python3
"""Audit *actual* C executables used by synthetic MAP02 texture comparisons.

Compiles three genuine pinned-PC / portable 4bpp helper harnesses and checks
their x86_64 Mach-O minos and dynamic library dependencies. Runs only the two
PUBLIC-source synthetic harnesses. Never opens or runs a private game capture.
An ABI/build-metadata audit is NOT proof of execution on macOS Catalina.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools.map02_intel_mac_offline_selfcheck import (
    macho_minos_is_target,
    pinned_public_raster,
    require_intel_mac,
)
from tools.verify_map02_pc_vram4_equivalence import (
    HARNESS as PAGE_HARNESS,
    extract_sample_functions,
)
from tools.verify_map02_pc_vram4_ft4_binding import (
    EXPECTED as FT4_EXPECTED,
    make_harness as make_ft4_harness,
)
from tools.verify_map02_private_timeline_pc_vram4 import (
    make_harness as make_timeline_harness,
)

SCHEMA = "vh.map02.catalina.pinned-pc-helper-macho-audit.v1"
TARGET = "10.15"
SOURCE_PROGRAMS = ("page", "ft4", "private-timeline")
SYSTEM_LIB_DIRS = ("/usr/lib/", "/System/Library/")


def only_system_dependencies(otool_l_output: str) -> bool:
    """Expect otool -L output including an image-name first line."""
    lines = otool_l_output.splitlines()
    if len(lines) < 2 or not lines[0].endswith(":"):
        return False
    deps = []
    for line in lines[1:]:
        item = line.strip().split(" (compatibility version ", 1)[0]
        if not item or not item.startswith(SYSTEM_LIB_DIRS):
            return False
        deps.append(item)
    return bool(deps)


def sources(pinned: bytes, *, frame_fixture: str, portable_header: str) -> dict:
    decoded = pinned.decode("utf-8")
    extracted = extract_sample_functions(decoded)
    return {
        "page": (
            PAGE_HARNESS.replace("{SOURCE}", extracted),
            portable_header,
        ),
        "ft4": (make_ft4_harness(decoded, frame_fixture), None),
        "private-timeline": (make_timeline_harness(pinned), None),
    }


def inspect(compiled: Path, *, otool: str, lipo: str) -> None:
    arch = subprocess.run(
        [lipo, "-archs", str(compiled)],
        capture_output=True, text=True, timeout=30,
    )
    load = subprocess.run(
        [otool, "-l", str(compiled)],
        capture_output=True, text=True, timeout=30,
    )
    linked = subprocess.run(
        [otool, "-L", str(compiled)],
        capture_output=True, text=True, timeout=30,
    )
    if (
        arch.returncode != 0 or load.returncode != 0 or linked.returncode != 0
        or arch.stdout.strip() != "x86_64"
        or not macho_minos_is_target(load.stdout, TARGET)
        or not only_system_dependencies(linked.stdout)
    ):
        raise ValueError("compiled x86_64 10.15 helper Mach-O audit failed")


def verify(pinned_raster: Path) -> dict:
    require_intel_mac()
    reference = pinned_public_raster(pinned_raster)
    root = Path(__file__).resolve().parent.parent
    frame_fixture = (root / "tests/test_map02_vram4_frame.c").read_text(
        encoding="utf-8"
    )
    portable_header = (root / "source/map02_vram4_page.h").read_text(
        encoding="utf-8"
    )
    built_sources = sources(
        reference.read_bytes(),
        frame_fixture=frame_fixture, portable_header=portable_header,
    )
    if tuple(built_sources) != SOURCE_PROGRAMS:
        raise ValueError("source helper coverage changed")
    clang, otool, lipo = (
        shutil.which(program) for program in ("clang", "otool", "lipo")
    )
    if not all((clang, otool, lipo)):
        raise ValueError("native Intel macOS toolchain unavailable")
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET=TARGET)
    exercised = 0
    with tempfile.TemporaryDirectory(prefix="vh-map02-macho-c-helper-") as tmp:
        work = Path(tmp)
        for name, (code, header) in built_sources.items():
            case = work / name
            case.mkdir(mode=0o700)
            if header is not None:
                (case / "map02_vram4_page.h").write_text(
                    header, encoding="utf-8"
                )
            src = case / "verify.c"
            exe = case / "verify"
            src.write_text(code, encoding="utf-8")
            proc = subprocess.run(
                [
                    clang, "-arch", "x86_64", "-mmacosx-version-min=" + TARGET,
                    "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(root), str(src), "-o", str(exe), "-lm",
                ],
                cwd=str(root), env=env,
                text=True, capture_output=True, timeout=60,
            )
            if proc.returncode or not exe.is_file():
                raise ValueError("pinned public PC helper C11 compilation failed")
            inspect(exe, otool=otool, lipo=lipo)
            if name in ("page", "ft4"):
                result = subprocess.run(
                    [str(exe)], capture_output=True, text=True, timeout=90,
                )
                if result.returncode:
                    raise ValueError("synthetic pinned PC helper execution failed")
                if name == "page":
                    parsed = json.loads(result.stdout)
                    if (
                        parsed.get("scenarios") != 32
                        or parsed.get("pixels_compared") != 2097152
                        or parsed.get("compiled_pc_sampletexture_matches") is not True
                        or parsed.get("real_gameplay_vram_verified") is not False
                    ):
                        raise ValueError("source-pinned page comparison contract changed")
                elif result.stdout.count(FT4_EXPECTED) != 1:
                    raise ValueError("synthetic FT4 texture-register probe failed")
                exercised += 1
            else:
                # A real private timeline would require user-owned snapshot
                # bytes. Do not feed invented input that might look like a
                # successful retail capture.
                denied = subprocess.run(
                    [str(exe)], input=b"", capture_output=True, timeout=30,
                )
                if denied.returncode != 2 or denied.stdout or denied.stderr:
                    raise ValueError("private timeline helper did not refuse absent input")
    if reference.is_symlink() or not reference.is_file():
        raise ValueError("pinned public PC source replaced during audit")
    pinned_public_raster(reference)
    return {
        "schema": SCHEMA,
        "compiled_helpers_audited": 3,
        "synthetic_helpers_executed": exercised,
        "private_timeline_missing_input_rejected": True,
        "helper_architecture": "x86_64",
        "helper_macos_minimum": TARGET,
        "all_helper_load_commands_verified": True,
        "only_system_dynamic_libraries": True,
        "original_ps1_assets_read": False,
        "catalina_10_15_runtime_executed": False,
        "retail_gameplay_authenticated": False,
        "nintendo_switch_hardware_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_raster", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.pinned_public_pc_raster)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired):
        parser.error("synthetic Catalina MAP02 helper audit unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
