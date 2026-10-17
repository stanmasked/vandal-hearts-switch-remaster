#!/usr/bin/env python3
"""Prepare source-pinned GPU + 2-word PutPixel + native DDA Make overrides.

Uses only the exact public PC-port source. Generates a private *opt-in*
overlay outside upstream; never alters upstream files, ships game data,
launches the game, or claims to have captured retail MAP02 gameplay.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.prepare_map02_pcport import (
    PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF, git_blob_sha1,
    REQUIRED_MAKE_ANCHORS,
)
from tools.instrument_map02_multi_putpixel_scope import (
    multi_gpu, multi_raster,
)
from tools.instrument_map02_putpixel_scope import GPU_BLOB, RASTER_BLOB
from tools.instrument_map02_raster_skips import instrument_raster_skips
from tools.instrument_map02_vertical_dda import instrument_vertical
from tools.instrument_map02_dda_span import instrument_span

MAKE_REL = "platform/pc/Makefile"
GPU_REL = "platform/pc/src/libgpu.c"
RASTER_REL = "platform/pc/src/pc_raster.c"
FLAGS = (
    "-DVH_MAP02_GPU_CAPTURE",
    "-DVH_MAP02_MULTI_PUTPIXEL_SCOPE",
    # Span's dependency guard also requires this earlier single-scope
    # compile flag; actual pixel hooks in the composed source remain the
    # shared MULTI observer and do not create a second pixel event stream.
    "-DVH_MAP02_PUTPIXEL_SCOPE",
    "-DVH_MAP02_RASTER_SKIP_TRACE",
    "-DVH_MAP02_DDA_VERTICAL_TRACE",
    "-DVH_MAP02_DDA_SPAN_TRACE",
)
SYMBOLS = (
    "VH_CaptureEvent", "VH_Map02PixelScopeSet",
    "VH_Map02PixelScopeClear", "VH_PixelSampleRecord",
    "VH_Map02SkipAt", "VH_Map02SpanObserve",
)
GENERATED_GPU = "libgpu.private.c"
GENERATED_RASTER = "pc_raster.private.c"
GENERATED_MAKE = "map02_private_gpu.mk"


def make_overlay(directory: Path):
    """Literal path only; never interpolate shell or Make metacharacters."""
    root = str(directory)
    if not re.fullmatch(r"[/A-Za-z0-9_.-]+", root):
        raise ValueError("private make overlay directory has unsafe characters")
    definitions = " ".join(FLAGS)
    return f"""# MAP02 private US PC-port GPU/DDA opt-in, generated from pinned sources.
# This file ONLY overrides the two backend compilation recipes.
# The baseline Makefile, original sources and build directory stay untouched.
ifneq ($(REGION),us)
$(error MAP02 private GPU instrumentation supports pinned US PC port only)
endif
ifeq ($(filter build-map02-%,$(BUILD_DIR)),)
$(error MAP02 private GPU requires isolated BUILD_DIR=build-map02-NAME)
endif
VH_MAP02_PRIVATE_GPU_SRC := {root}
VH_MAP02_PRIVATE_GPU_DEFINES := {definitions}

$(BUILD_DIR)/libgpu.o: $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_GPU}
\t@mkdir -p $(dir $@)
\t$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_PRIVATE_GPU_DEFINES) -Iinclude -g -MMD -MP -c -o $@ $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_GPU}

$(BUILD_DIR)/pc_raster.o: $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_RASTER}
\t@mkdir -p $(dir $@)
\t$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_PRIVATE_GPU_DEFINES) -Iinclude -g -MMD -MP -c -o $@ $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_RASTER}

.PHONY: map02-private-gpu-objects
map02-private-gpu-objects: $(BUILD_DIR)/libgpu.o $(BUILD_DIR)/pc_raster.o
"""


def prepare(upstream: Path, output: Path):
    upstream = Path(upstream).resolve(strict=True)
    output = Path(output).absolute()
    if not upstream.is_dir() or output == upstream or upstream in output.parents:
        raise ValueError("private overlay must be outside upstream checkout")
    if output.is_symlink() or output.exists():
        raise ValueError("private output directory already exists")
    # Avoid using an arbitrary value from Make or the shell as generated code.
    overlay = make_overlay(output)
    src = {}
    expected = {
        MAKE_REL: PINNED_BLOB_SHA1[MAKE_REL],
        GPU_REL: GPU_BLOB,
        RASTER_REL: RASTER_BLOB,
    }
    for relative, digest in expected.items():
        origin = upstream / relative
        if origin.is_symlink() or not origin.is_file():
            raise ValueError("pinned public PC source missing or symlinked")
        data = origin.read_bytes()
        if git_blob_sha1(data) != digest:
            raise ValueError("pinned public PC source Git blob differs")
        src[relative] = data
    makefile = src[MAKE_REL].decode("utf-8")
    if not all(x in makefile for x in REQUIRED_MAKE_ANCHORS):
        raise ValueError("unexpected original PC Makefile profile")
    if ("$(BUILD_DIR)/libgpu.o: src/libgpu.c" not in makefile or
            "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c" not in makefile):
        raise ValueError("pinned backend Make recipes changed")

    gpu = multi_gpu(src[GPU_REL].decode("utf-8"))
    raster = instrument_span(instrument_vertical(
        instrument_raster_skips(multi_raster(src[RASTER_REL].decode("utf-8")))))
    artifacts = {
        GENERATED_GPU: gpu.encode("utf-8"),
        GENERATED_RASTER: raster.encode("utf-8"),
        GENERATED_MAKE: overlay.encode("utf-8"),
    }

    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    created = []
    try:
        for filename, payload in artifacts.items():
            destination = output / filename
            with destination.open("xb") as stream:
                created.append(destination)
                stream.write(payload)
    except BaseException:
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
        try:
            output.rmdir()
        except OSError:
            pass
        raise
    return {
        "schema": "vh.map02.private-native-two-word-dda-overlay.v1",
        "pinned_public_pc_commit": PINNED_UPSTREAM_REF,
        "source_pinned": True,
        "original_checkout_modified": False,
        "native_gpu_two_word_and_dda_in_same_make_objects": True,
        "source_sha256": {p: hashlib.sha256(data).hexdigest()
                          for p, data in sorted(src.items())},
        "generated_sha256": {p: hashlib.sha256(data).hexdigest()
                             for p, data in sorted(artifacts.items())},
        "required_compiler_defines": list(FLAGS),
        "required_native_symbols": list(SYMBOLS),
        "output_files": sorted(artifacts),
        "isolated_build_directory_required": True,
        "game_assets_included": False,
        "retail_map02_gameplay_captured": False,
        "native_process_to_gpu_log_causality_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pinned_public_pc_checkout", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = prepare(args.pinned_public_pc_checkout, args.output_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
