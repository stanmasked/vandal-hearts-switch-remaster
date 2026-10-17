#!/usr/bin/env python3
"""Compile REAL pinned original-PC GPU translation units after opt-in patching.

No proprietary SLUS file / BIOS / game assets required. This is a host-GPU
object compilation and relocatable link, NOT a playable PC binary or verified
MAP02 gameplay capture. Mirrors the Makefile's PC-backend warnings/includes.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from tools.instrument_map02_drawotag_scope import instrument as patch_drawotag
from tools.instrument_map02_scoped_blend import instrument as patch_raster


def run_checked(command, *, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True,
                            text=True, timeout=120, check=False)
    if result.returncode:
        raise ValueError("PC GPU diagnostic compilation failed: "
                         + result.stderr[-2400:])
    return result.stdout


def verify_gpu_objects(upstream, *, cc="cc", linker=None, nm="nm"):
    upstream = Path(upstream).resolve()
    pc = upstream / "platform" / "pc"
    original_raster = pc / "src" / "pc_raster.c"
    original_walker = pc / "src" / "libgpu.c"
    # Fail for absent upstream files before invoking source-anchor validation.
    if not original_raster.is_file() or not original_walker.is_file():
        raise FileNotFoundError("missing pinned original PC GPU translation unit")
    raster = patch_raster(original_raster.read_text(encoding="utf-8"))
    walker = patch_drawotag(original_walker.read_text(encoding="utf-8"))
    if linker is None:
        linker = cc
    with tempfile.TemporaryDirectory(prefix="vh-map02-real-gpu-") as temp:
        root = Path(temp)
        src_raster = root / "pc_raster.instrumented.c"
        src_walker = root / "libgpu.instrumented.c"
        src_raster.write_text(raster, encoding="utf-8")
        src_walker.write_text(walker, encoding="utf-8")
        common = [
            "-std=gnu99", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-Wno-missing-field-initializers",
            "-DVH_REGION_US", "-I", str(pc / "include"),
            "-I", str(pc / "src"),
        ]
        tools = Path(__file__).resolve().parent
        cases = (
            ("ordinary", []),
            ("scoped", ["-DVH_MAP02_SCOPED_BLEND_PROBE"]),
            ("private-posix", ["-DVH_MAP02_SCOPED_BLEND_PROBE",
                               "-DVH_MAP02_POSIX_STAGE"]),
        )
        checked = []
        for label, defines in cases:
            case = root / label
            case.mkdir()
            objects = []
            for src in (src_raster, src_walker):
                dst = case / (src.stem + ".o")
                run_checked([cc, *common, *defines, "-c",
                             str(src), "-o", str(dst)])
                objects.append(dst)
            if defines:
                sink = case / "sink.o"
                run_checked([cc, *common, *defines,
                             "-I", str(tools), "-c",
                             str(tools / "map02_scoped_blend_sink.c"),
                             "-o", str(sink)])
                objects.append(sink)
            if label == "private-posix":
                stage = case / "stage.o"
                run_checked([cc, *common, *defines,
                             "-I", str(tools), "-c",
                             str(tools / "map02_scoped_blend_stage.c"),
                             "-o", str(stage)])
                objects.append(stage)
            combined = case / "gpu-linked.o"
            run_checked([linker, "-r", *(str(obj) for obj in objects),
                         "-o", str(combined)])
            undefined = run_checked([nm, "-u", str(combined)])
            if re.search(r"\bvh_map02_", undefined):
                raise ValueError("unresolved private MAP02 observer symbols")
            checked.append(label)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_upstream_repo", type=Path)
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--nm", default="nm")
    a = parser.parse_args()
    try:
        checks = verify_gpu_objects(a.pinned_upstream_repo, cc=a.cc, nm=a.nm)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print("Original PC GPU TUs compiled and linked: " + ", ".join(checks))
    print("No original game executable, original gameplay capture or "
          "PS1 hardware equivalence proven.")


if __name__ == "__main__":
    main()
