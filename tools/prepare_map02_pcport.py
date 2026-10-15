#!/usr/bin/env python3
"""Prepare a noninvasive make overlay for map02 load/draw tracing in the US PC port.

The user supplies their own pinned upstream checkout and disc/executable.
This script makes two generated C files and one make overlay OUTSIDE the checkout.
It never runs the game or edits upstream source/data.
"""
import argparse
from pathlib import Path

from tools.instrument_map02_loader import instrument as instrument_loader
from tools.instrument_map02_renderer import instrument as instrument_renderer

REQUIRED_MAKE_ANCHORS = (
    "GAME_C_FLAGS",
    "$(BUILD_DIR)/src/%.o: $(SRC_DIR)/%.c | stage",
    "$(CC) $(GAME_C_FLAGS) -MMD -MP -c -o $@ $<",
)


def prepare(upstream: Path, output: Path) -> Path:
    upstream = upstream.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(upstream):
        raise ValueError("output must be outside upstream checkout")
    if any(ch.isspace() or ch in "#$" for ch in str(output)):
        raise ValueError("output path cannot contain whitespace or make-special characters")
    if output.exists():
        raise ValueError("output directory already exists; refusing to overwrite")
    makefile = (upstream / "platform/pc/Makefile").read_text(encoding="utf-8")
    if not all(anchor in makefile for anchor in REQUIRED_MAKE_ANCHORS):
        raise ValueError("upstream Makefile is not the expected US PC-port build profile")
    loader = (upstream / "src/states/game_setup.c").read_text(encoding="utf-8")
    renderer = (upstream / "src/core/graphics.c").read_text(encoding="utf-8")
    loader_result = "#include <stdio.h>\n" + instrument_loader(loader)
    renderer_result = instrument_renderer(renderer)  # already includes stdio
    make_overlay = f'''# Generated map02 diagnostic build overlay (US PC port only).
# Invoke from upstream platform/pc:
# make -f Makefile -f {output}/map02_trace.mk link BUILD_DIR=build-map02-trace
VH_MAP02_TRACE_DIR := {output}
$(BUILD_DIR)/src/states/game_setup.o: $(VH_MAP02_TRACE_DIR)/game_setup.trace.c | stage
\t@mkdir -p $(dir $@)
\t$(CC) $(GAME_C_FLAGS) -DVH_TRACE_MAP02_POST_LOAD -MMD -MP -c -o $@ $(VH_MAP02_TRACE_DIR)/game_setup.trace.c
$(BUILD_DIR)/src/core/graphics.o: $(VH_MAP02_TRACE_DIR)/graphics.trace.c | stage
\t@mkdir -p $(dir $@)
\t$(CC) $(GAME_C_FLAGS) -DVH_TRACE_MAP02_DRAW -MMD -MP -c -o $@ $(VH_MAP02_TRACE_DIR)/graphics.trace.c
'''
    output.mkdir(parents=True, exist_ok=False)
    (output / "game_setup.trace.c").write_text(loader_result, encoding="utf-8")
    (output / "graphics.trace.c").write_text(renderer_result, encoding="utf-8")
    (output / "map02_trace.mk").write_text(make_overlay, encoding="utf-8")
    return output / "map02_trace.mk"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_checkout", type=Path, help="pinned upstream US PC-port repository root")
    parser.add_argument("new_output_directory", type=Path, help="new empty directory outside upstream checkout")
    args = parser.parse_args()
    try:
        overlay = prepare(args.upstream_checkout, args.new_output_directory)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Generated {overlay}. Run from upstream platform/pc:")
    print(f"make -f Makefile -f {overlay} link BUILD_DIR=build-map02-trace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
