#!/usr/bin/env python3
"""Prepare a noninvasive make overlay for map02 load/draw tracing in the US PC port.

The user supplies their own pinned upstream checkout and disc/executable.
This script makes two generated C files and one make overlay OUTSIDE the checkout.
It never runs the game or edits upstream source/data.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.instrument_map02_loader import instrument as instrument_loader
from tools.instrument_map02_renderer import instrument as instrument_renderer

PINNED_UPSTREAM_REF = "14552fffa0e0b47e02b57592e274fc6e7a649923"
# Git object blob IDs from the exact upstream revision, not hashes of decoded text.
PINNED_BLOB_SHA1 = {
    "src/core/graphics.c": "b89a83c226639f6b4db13ddbf0e3118b49262d39",
    "src/states/game_setup.c": "cd685b1ecf470f82bbcd3b805fc8e2867d905a75",
    "platform/pc/Makefile": "5d7f43aa755926aa69c7975ce4f2cd1e8e3393aa",
}


def git_blob_sha1(contents: bytes) -> str:
    header = f"blob {len(contents)}\\0".encode("ascii").replace(b"\\0", b"\x00")
    return hashlib.sha1(header + contents).hexdigest()


REQUIRED_MAKE_ANCHORS = (
    "GAME_C_FLAGS",
    "$(BUILD_DIR)/src/%.o: $(SRC_DIR)/%.c | stage",
    "$(CC) $(GAME_C_FLAGS) -MMD -MP -c -o $@ $<",
)


def prepare(upstream: Path, output: Path, allow_modified_source: bool = False) -> Path:
    upstream = upstream.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(upstream):
        raise ValueError("output must be outside upstream checkout")
    if any(ch.isspace() or ch in "#$" for ch in str(output)):
        raise ValueError("output path cannot contain whitespace or make-special characters")
    if output.exists():
        raise ValueError("output directory already exists; refusing to overwrite")
    identities = {}
    for relative, expected in PINNED_BLOB_SHA1.items():
        data = (upstream / relative).read_bytes()
        observed = git_blob_sha1(data)
        identities[relative] = {
            "git_blob_sha1": observed,
            "sha256": hashlib.sha256(data).hexdigest(),
            "matches_pinned": observed == expected,
        }
        if observed != expected and not allow_modified_source:
            raise ValueError(
                f"{relative} differs from pinned upstream {PINNED_UPSTREAM_REF}: "
                f"observed Git blob {observed}; expected {expected}. "
                "Use --allow-modified-source only for deliberate experiments."
            )
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
    provenance = {
        "upstream_reference": PINNED_UPSTREAM_REF,
        "allow_modified_source": allow_modified_source,
        "source_files": identities,
        "warning": "Source provenance only; not evidence of a successful build or actual game trace.",
    }
    (output / "source_provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return output / "map02_trace.mk"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_checkout", type=Path, help="pinned upstream US PC-port repository root")
    parser.add_argument("new_output_directory", type=Path, help="new empty directory outside upstream checkout")
    parser.add_argument("--allow-modified-source", action="store_true",
                        help="permit altered upstream files and flag them in provenance")
    args = parser.parse_args()
    try:
        overlay = prepare(args.upstream_checkout, args.new_output_directory,
                          allow_modified_source=args.allow_modified_source)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Generated {overlay}. Run from upstream platform/pc:")
    print(f"make -f Makefile -f {overlay} link BUILD_DIR=build-map02-trace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
