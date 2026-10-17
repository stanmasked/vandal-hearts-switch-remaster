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
import shutil
import subprocess

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
# Make's % wildcard also accepts "../", shell metacharacters and spaces.
# Validate BUILD_DIR using GNU Make string functions BEFORE recipe expansion;
# generated source paths and build targets must not escape the checkout.
VH_MAP02_PRIVATE_BUILD_CHARS := a b c d e f g h i j k l m n o p q r s t u v w x y z A B C D E F G H I J K L M N O P Q R S T U V W X Y Z 0 1 2 3 4 5 6 7 8 9 - _
define vh_map02_private_strip_chars
$(if $(strip $(2)),$(call vh_map02_private_strip_chars,$(subst $(firstword $(2)),,$(1)),$(wordlist 2,$(words $(2)),$(2))),$(1))
endef
ifneq ($(words $(BUILD_DIR)),1)
$(error MAP02 private GPU BUILD_DIR contains whitespace)
endif
ifneq ($(strip $(call vh_map02_private_strip_chars,$(BUILD_DIR),$(VH_MAP02_PRIVATE_BUILD_CHARS))),)
$(error MAP02 private GPU BUILD_DIR has unsafe characters)
endif
ifeq ($(BUILD_DIR),build-map02-)
$(error MAP02 private GPU BUILD_DIR requires a nonempty suffix)
endif
VH_MAP02_PRIVATE_GPU_SRC := {root}
VH_MAP02_PRIVATE_GPU_DEFINES := {definitions}

$(BUILD_DIR)/libgpu.o: $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_GPU}
\t@mkdir -p $(dir $@)
\t$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_PRIVATE_GPU_DEFINES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_GPU}

$(BUILD_DIR)/pc_raster.o: $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_RASTER}
\t@mkdir -p $(dir $@)
\t$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_PRIVATE_GPU_DEFINES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_PRIVATE_GPU_SRC)/{GENERATED_RASTER}

# The upstream 'link' recipe names GAME_O_FILES and BACKEND_OBJS but
# depends only on DATA_OBJS. On a clean checkout it can therefore reach
# the linker with missing game/backend objects. For this opt-in overlay,
# explicitly attach the upstream 'objs' prerequisite to link. Do not
# replace the original link recipe or alter any normal build invocation.
.PHONY: map02-private-gpu-objects map02-private-pc-link
map02-private-gpu-objects: $(BUILD_DIR)/libgpu.o $(BUILD_DIR)/pc_raster.o
link: objs
map02-private-pc-link: link
"""


def _require_pinned_clean_checkout(upstream: Path):
    """Refuse altered game/port source before preparing a full-link overlay.

    The three GPU/Make blob hashes pin the instrumented source units,
    while the full executable links many additional tracked game files.
    Verify their Git checkout as well, ignoring user-owned untracked assets.
    Never return private checkout paths or changed filenames.
    """
    git = shutil.which("git", path="/usr/bin:/bin")
    if not git:
        raise ValueError("pinned public PC Git inspector unavailable")
    child_env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    for args in (("rev-parse", "--verify", "HEAD"),
                 ("status", "--porcelain=v1", "--untracked-files=no")):
        try:
            result = subprocess.run(
                [git, *args], cwd=upstream, env=child_env,
                capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("pinned public PC checkout inspection failed") from exc
        if result.returncode != 0:
            raise ValueError("pinned public PC checkout inspection failed")
        if args[0] == "rev-parse":
            if result.stdout.strip() != PINNED_UPSTREAM_REF:
                raise ValueError("pinned public PC checkout HEAD differs")
        elif result.stdout.strip():
            raise ValueError("pinned public PC tracked source files modified")


def prepare(upstream: Path, output: Path):
    upstream = Path(upstream).resolve(strict=True)
    output = Path(output).absolute()
    # Resolve the *parent* too: a symlinked parent must not silently
    # redirect the generated C and Make overlay into the source checkout.
    try:
        real_parent = output.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("private output parent directory unavailable") from exc
    canonical_output = real_parent / output.name
    if (not upstream.is_dir() or canonical_output == upstream
            or upstream in canonical_output.parents):
        raise ValueError("private overlay must be outside upstream checkout")
    if real_parent != output.parent:
        raise ValueError("private output parent cannot be a symlink alias")
    if output.is_symlink() or output.exists():
        raise ValueError("private output directory already exists")
    _require_pinned_clean_checkout(upstream)
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
    # The opt-in 'link: objs' overlay assumes the original target graph:
    # 'objs' builds game/backends and generated-data objects, and the
    # original 'link' recipe consumes all three object lists.
    link_anchors = (
        "default: $(GAME_O_FILES) $(BACKEND_OBJS)",
        "objs: default $(DATA_OBJS)",
        "link: $(DATA_OBJS)",
        "$(GAME_O_FILES) $(BACKEND_OBJS) $(DATA_OBJS)",
        "BACKEND_OBJS",
        "libgpu.c pc_raster.c",
    )
    if not all(anchor in makefile for anchor in link_anchors):
        raise ValueError("pinned original PC full-link Make dependency graph changed")

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
        "full_checkout_head_verified": True,
        "full_tracked_checkout_clean": True,
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
