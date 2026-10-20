#!/usr/bin/env python3
"""Generate a private opt-in GNU Make overlay for ONE original PC-port ELF.

Never changes the pinned upstream source or its Makefile. The overlay compiles
instrumented original core/cd.c, libcd.c, libgpu.c and pc_raster.c and links their observers
into a dedicated diagnostic game build. It does NOT supply copyrighted game
assets, build an ELF on its own, or attest a retail gameplay cycle.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.instrument_map02_cycle_order import (
    patch_core, patch_gpu, patch_libcd, patch_raster,
)
from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, git_blob_sha1
from tools.instrument_map02_cd_read import SOURCE_CD, SOURCE_LIBCD
from tools.instrument_map02_gpu_native_events import PINNED_SOURCE
from tools.instrument_map02_pc_preoverlay_capture import instrument as patch_pc_present
from tools.check_map02_pc_present_rgb24_source import BLOB_SHA1 as PC_PRESENT_SOURCE
from tools.check_map02_private_pc_inputs import (FONT_GENERATOR,
    FONT_GENERATOR_BLOB_SHA1)

SOURCE_MAP = {
    "core_cd.c": ("src/core/cd.c", SOURCE_CD, patch_core),
    "libcd.c": ("platform/pc/src/libcd.c", SOURCE_LIBCD, patch_libcd),
    "libgpu.c": ("platform/pc/src/libgpu.c", PINNED_SOURCE, patch_gpu),
    "pc_raster.c": ("platform/pc/src/pc_raster.c",
                    "ba8a05d161ad778c0b75e452ff0a11ed163c65cd", patch_raster),
    "pc_gpu_window.c": ("platform/pc/src/pc_gpu_window.c",
                        PC_PRESENT_SOURCE, patch_pc_present),
}
SUPPORT_FILES = (
    "map02_cycle_order.c", "map02_cycle_order.h",
    "map02_cd_read_probe.c", "map02_cd_read_probe.h",
    "map02_capture_session.c", "map02_capture_session.h",
    "map02_pc_preoverlay_capture.c", "map02_pc_preoverlay_capture.h",
    "map02_scoped_blend_sink.c", "map02_scoped_blend_sink.h",
    "map02_scoped_blend_stage.c", "map02_scoped_blend_stage.h",
    "map02_vram_edges.c", "map02_vram_edges.h",
)
MAKEFILE_SHA = PINNED_BLOB_SHA1["platform/pc/Makefile"]
FONT_GENERATOR_SNAPSHOT = "map02_pinned_gen_kanji_font.py"
MAKE_ANCHORS = (
    "$(BUILD_DIR)/libcd.o: src/libcd.c",
    "$(BUILD_DIR)/libgpu.o: src/libgpu.c",
    "$(BUILD_DIR)/pc_raster.o: src/pc_raster.c",
    "$(BUILD_DIR)/pc_gpu_window.o: src/pc_gpu_window.c",
    "link: $(DATA_OBJS)",
    "$(BUILD_DIR)/src/%.o: $(SRC_DIR)/%.c | stage",
)
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _validate_paths(upstream, output, support):
    for path, label in ((upstream, "upstream"), (support, "support")):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(label + " directory missing or symlinked")
    if output.is_symlink() or output.exists():
        raise ValueError("output must be a NEW directory, not a symlink")
    upstream, output, support = (p.resolve() for p in (upstream, output, support))
    if output == upstream or upstream in output.parents:
        raise ValueError("output must be outside original PC-port checkout")
    if output == support or support in output.parents:
        raise ValueError("output cannot overwrite observer source files")
    if not SAFE_PATH.fullmatch(str(output)) or ".." in output.parts:
        raise ValueError("make overlay path contains unsafe characters")
    return upstream, output, support


def _render_makefile(output):
    # Limit compilation to US, a separate build folder, and a single region.
    # make's original "link" recipe expands BACKEND_OBJS at execution, so the
    # three private support objects are included in the final game ELF.
    return f"""# Generated read-only-input MAP02 private diagnostic make overlay.
# Use from pinned upstream platform/pc, never copy this into public releases.
VH_MAP02_CYCLE_ROOT := {output}
ifneq ($(REGION),us)
$(error MAP02 source-pinned cycle diagnostics support REGION=us only)
endif
ifeq ($(UNIFIED),1)
$(error MAP02 cycle diagnostic is not validated with UNIFIED=1)
endif
ifeq ($(BUILD_DIR),build)
$(error Set a dedicated BUILD_DIR=build-map02-cycle; do not reuse baseline objects)
endif
ifneq ($(filter -DVH_MAP02_CYCLE_ORDER,$(GAME_C_FLAGS)),)
$(error Do not set cycle instrumentation globally; per-object recipes own flags)
endif
VH_MAP02_CYCLE_DEFS := -DVH_MAP02_CYCLE_ORDER -DVH_MAP02_CD_READ_PROBE
VH_MAP02_GPU_DEFS := -DVH_MAP02_CYCLE_ORDER -DVH_MAP02_GPU_CAPTURE -DVH_MAP02_POSIX_CAPTURE_WINDOWS -DVH_MAP02_SCOPED_BLEND_PROBE -DVH_MAP02_VRAM_EDGE_PROBE -DVH_MAP02_POSIX_STAGE -DVH_MAP02_CAPTURE_SESSION
VH_MAP02_STAGE_DEFS := -DVH_MAP02_CD_READ_PROBE -DVH_MAP02_VRAM_EDGE_PROBE -DVH_MAP02_CAPTURE_SESSION
VH_MAP02_PC_PRESENT_DEFS := -DVH_MAP02_PC_PREOVERLAY_CAPTURE
VH_MAP02_CYCLE_INCLUDES := -I$(VH_MAP02_CYCLE_ROOT)
# Only the source-pinned private snapshot is allowed to read owned KROM data.
# This shadow target prevents GNU Make from invoking its inherited source
# generator to write copyrighted data into the original checkout.
src/pc_kanji_font.c: $(VH_MAP02_CYCLE_ROOT)/{FONT_GENERATOR_SNAPSHOT}
	@:
$(BUILD_DIR)/map02_pinned_kanji_font.c: $(VH_MAP02_CYCLE_ROOT)/{FONT_GENERATOR_SNAPSHOT}
	@mkdir -p $(dir $@)
	@test ! -e $@ && test ! -L $@ || (echo "MAP02 private generated font already exists" >&2; exit 1)
	@umask 077; VH_REGION=us VH_GENERATED_OUT=$@ python3 -I $(VH_MAP02_CYCLE_ROOT)/{FONT_GENERATOR_SNAPSHOT}
# Inherited prerequisites remain, but this recipe NEVER reads src/pc_kanji_font.c.
$(BUILD_DIR)/pc_kanji_font.o: $(BUILD_DIR)/map02_pinned_kanji_font.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) -Iinclude -g -MMD -MP -c -o $@ $(BUILD_DIR)/map02_pinned_kanji_font.c
VH_MAP02_CYCLE_SUPPORT := $(addprefix $(BUILD_DIR)/,map02_cycle_order.o map02_cd_read_probe.o map02_capture_session.o map02_pc_preoverlay_capture.o map02_scoped_blend_sink.o map02_scoped_blend_stage.o map02_vram_edges.o)
BACKEND_OBJS += $(VH_MAP02_CYCLE_SUPPORT)
link: $(VH_MAP02_CYCLE_SUPPORT)
# Some original public C files include retail-generated assets/*.inc.
# Compile only code without such direct includes; never fabricate binary assets.
# An independent Python verifier audits EVERY excluded original translation unit.
VH_MAP02_ASSET_BOUND_SOURCES := $(shell grep -lE '^[[:space:]]*#[[:space:]]*include[[:space:]]*"assets/' $(GAME_ROOT)/src/*.c $(GAME_ROOT)/src/*/*.c)
VH_MAP02_ASSET_BOUND_OBJECTS := $(patsubst $(GAME_ROOT)/src/%.c,$(BUILD_DIR)/src/%.o,$(VH_MAP02_ASSET_BOUND_SOURCES))
VH_MAP02_PUBLIC_CODE_OBJS := $(filter-out $(VH_MAP02_ASSET_BOUND_OBJECTS),$(GAME_O_FILES))
# The original pc_kanji_font.c is generated from user's Sony PsyQ
# KROMDAT.BIN (not publicly tracked); do not synthesize this copyrighted font.
VH_MAP02_BIOS_FONT_OBJECT := $(BUILD_DIR)/pc_kanji_font.o
VH_MAP02_PUBLIC_BACKEND_OBJS := $(filter-out $(VH_MAP02_BIOS_FONT_OBJECT),$(BACKEND_OBJS))
.PHONY: map02-public-code
map02-public-code: $(VH_MAP02_PUBLIC_CODE_OBJS) $(VH_MAP02_PUBLIC_BACKEND_OBJS)

$(BUILD_DIR)/src/core/cd.o: $(VH_MAP02_CYCLE_ROOT)/core_cd.c | stage
	@mkdir -p $(dir $@)
	$(CC) $(GAME_C_FLAGS) $(VH_MAP02_CYCLE_DEFS) $(VH_MAP02_CYCLE_INCLUDES) -MMD -MP -c -o $@ $(VH_MAP02_CYCLE_ROOT)/core_cd.c

$(BUILD_DIR)/libcd.o: $(VH_MAP02_CYCLE_ROOT)/libcd.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_DEFS) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_CYCLE_ROOT)/libcd.c

$(BUILD_DIR)/libgpu.o: $(VH_MAP02_CYCLE_ROOT)/libgpu.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_GPU_DEFS) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_CYCLE_ROOT)/libgpu.c

$(BUILD_DIR)/pc_raster.o: $(VH_MAP02_CYCLE_ROOT)/pc_raster.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) -DVH_MAP02_SCOPED_BLEND_PROBE $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_CYCLE_ROOT)/pc_raster.c

$(BUILD_DIR)/pc_gpu_window.o: $(VH_MAP02_CYCLE_ROOT)/pc_gpu_window.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_PC_PRESENT_DEFS) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -Isrc -g -MMD -MP -c -o $@ $(VH_MAP02_CYCLE_ROOT)/pc_gpu_window.c

$(BUILD_DIR)/map02_cycle_order.o: $(VH_MAP02_CYCLE_ROOT)/map02_cycle_order.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_cd_read_probe.o: $(VH_MAP02_CYCLE_ROOT)/map02_cd_read_probe.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_capture_session.o: $(VH_MAP02_CYCLE_ROOT)/map02_capture_session.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_pc_preoverlay_capture.o: $(VH_MAP02_CYCLE_ROOT)/map02_pc_preoverlay_capture.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_scoped_blend_sink.o: $(VH_MAP02_CYCLE_ROOT)/map02_scoped_blend_sink.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_scoped_blend_stage.o: $(VH_MAP02_CYCLE_ROOT)/map02_scoped_blend_stage.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_STAGE_DEFS) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<

$(BUILD_DIR)/map02_vram_edges.o: $(VH_MAP02_CYCLE_ROOT)/map02_vram_edges.c
	@mkdir -p $(dir $@)
	$(CC) $(M32) $(SAN) $(PORT_WARN) $(VH_MAP02_CYCLE_INCLUDES) -Iinclude -g -MMD -MP -c -o $@ $<
"""


def prepare(upstream: Path, output: Path, *, support=None):
    support = Path(support) if support is not None else Path(__file__).resolve().parent
    upstream, output, support = _validate_paths(
        Path(upstream), Path(output), support)
    make_path = upstream / "platform/pc/Makefile"
    if make_path.is_symlink():
        raise ValueError("upstream Makefile cannot be a symlink")
    make_bytes = make_path.read_bytes()
    if git_blob_sha1(make_bytes) != MAKEFILE_SHA:
        raise ValueError("upstream Makefile differs from source-pinned build")
    make_text = make_bytes.decode("utf-8")
    if (any(make_text.count(anchor) != 1 for anchor in MAKE_ANCHORS) or
            any(anchor not in make_text for anchor in
                ("BACKEND_OBJS", "GAME_C_FLAGS", "PORT_WARN"))):
        raise ValueError("source-pinned Makefile target or build profile drift")

    rendered = {}
    originals = {}
    for target, (relative, expected, instrument) in SOURCE_MAP.items():
        file = upstream / relative
        if file.is_symlink():
            raise ValueError("original upstream unit is a symlink: " + relative)
        data = file.read_bytes()
        if git_blob_sha1(data) != expected:
            raise ValueError("original pinned source changed: " + relative)
        originals[relative] = _sha(data)
        rendered[target] = instrument(data.decode("utf-8")).encode("utf-8")
    # Snapshot the exact original public KROM generator in the 0700 bundle.
    # The original upstream Makefile is not modified or executed for this
    # generator. Its private copy will receive the validated source ROM path.
    generator_path = upstream / FONT_GENERATOR
    if generator_path.is_symlink() or not generator_path.is_file():
        raise ValueError("pinned original font generator missing or linked")
    font_script = generator_path.read_bytes()
    if git_blob_sha1(font_script) != FONT_GENERATOR_BLOB_SHA1:
        raise ValueError("pinned original font generator source drift")
    originals[FONT_GENERATOR] = _sha(font_script)
    rendered[FONT_GENERATOR_SNAPSHOT] = font_script
    for name in SUPPORT_FILES:
        file = support / name
        if file.is_symlink() or not file.is_file():
            raise ValueError("cycle support file missing or symlinked: " + name)
        rendered[name] = file.read_bytes()
    rendered["map02_cycle.mk"] = _render_makefile(output).encode("utf-8")
    manifest = {
        "schema": "vh.map02.private-single-elf-build-inputs.v1",
        "upstream_makefile_sha256": _sha(make_bytes),
        "original_source_sha256": originals,
        "generated_files_sha256": {
            key: _sha(value) for key, value in sorted(rendered.items())
        },
        "retail_gameplay_executed": False,
        "original_map02_rendering_proven": False,
        "physical_ps1_equivalence_proven": False,
    }
    rendered["map02_cycle_build_inputs.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # On partial failure, preserve this freshly created directory instead
    # of recursively deleting it: another process may have populated it in
    # the meantime. A failed bundle is never reused because _validate_paths
    # requires a *new* output pathname on the next attempt.
    output.mkdir(parents=True, mode=0o700)
    for name, data in rendered.items():
        target = output / name
        with target.open("xb") as f:
            f.write(data)
        target.chmod(0o600)
    return output / "map02_cycle.mk"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pinned_upstream_checkout", type=Path)
    p.add_argument("new_private_output_dir", type=Path)
    args = p.parse_args()
    try:
        prepare(args.pinned_upstream_checkout, args.new_private_output_dir)
    except (OSError, ValueError, UnicodeError):
        # Native filesystem errors and path-validation exceptions may embed
        # the user's private game checkout, overlay location or SDK paths.
        # Keep terminal/CI status independent of any caller-controlled path.
        p.error("private MAP02 source-pinned overlay preparation failed")
    print("Private source-pinned MAP02 Make overlay created.")
    print("Run the separate Make-plan audit with the paths supplied above;")
    print("then use the private full-PC-ELF builder, not a direct public make.")
    print("No retail bytes read, no executable compiled, no gameplay executed.")


if __name__ == "__main__":
    main()
