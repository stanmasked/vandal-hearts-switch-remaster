#!/usr/bin/env python3
"""Bounds-checked PlayStation TIM inspector (no proprietary resource included).

Accepts a standalone little-endian TIM file, not an entire ISO/CD image.
This preflights the source buffer before the pinned port's OpenTIM/ReadTIM,
which parse sections without a buffer-length argument.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

VRAM_WIDTH = 1024
VRAM_HEIGHT = 512
MAX_SECTION_BYTES = 0x20000
MAX_TIM_BYTES = 8 + 2 * MAX_SECTION_BYTES


def parse_tim(data):
    """Return metadata for one complete, bounded 4/8/15bpp TIM file."""
    if len(data) < 8 or len(data) > MAX_TIM_BYTES:
        raise ValueError("invalid total TIM length")
    magic, flags = struct.unpack_from("<II", data)
    if magic != 0x10:
        raise ValueError("invalid TIM magic/version")
    if flags & ~0xB:
        raise ValueError("unsupported TIM mode/flag bits")
    depth = flags & 0x7
    if depth not in (0, 1, 2):
        raise ValueError("unsupported TIM pixel depth")
    if (depth in (0, 1)) != bool(flags & 8):
        raise ValueError("indexed TIM requires CLUT; direct TIM must not have one")

    def section(offset, role):
        if offset + 12 > len(data):
            raise ValueError(f"truncated {role} section header")
        size, x, y, w, h = struct.unpack_from("<IHHHH", data, offset)
        if size < 12 or size > MAX_SECTION_BYTES or size % 4:
            raise ValueError(f"invalid {role} section length")
        if w == 0 or h == 0 or x + w > VRAM_WIDTH or y + h > VRAM_HEIGHT:
            raise ValueError(f"{role} destination outside PS1 VRAM")
        if size != 12 + 2 * w * h:
            raise ValueError(f"{role} section byte size does not match rectangle")
        if offset + size > len(data):
            raise ValueError(f"truncated {role} pixels")
        return {
            "rect": [x, y, w, h],
            "payload_offset": offset + 12,
            "payload_bytes": size - 12,
        }, offset + size

    offset = 8
    palette = None
    if flags & 8:
        palette, offset = section(offset, "CLUT")
    pixels, offset = section(offset, "image")
    if offset != len(data):
        raise ValueError("unexpected bytes after image section")

    depth_name = {0: "4bpp", 1: "8bpp", 2: "15bpp"}[depth]
    logical_width = pixels["rect"][2] * {0: 4, 1: 2, 2: 1}[depth]
    return {
        "format": "PS1_TIM",
        "depth": depth_name,
        "flags": flags,
        "logical_width": logical_width,
        "logical_height": pixels["rect"][3],
        "clut": palette,
        "pixels": pixels,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("tim", type=Path, help="standalone TIM from a user-owned game image")
    args = cli.parse_args(argv)
    if args.tim.stat().st_size > MAX_TIM_BYTES:
        cli.error("TIM exceeds bounds-checked maximum")
    try:
        metadata = parse_tim(args.tim.read_bytes())
    except ValueError as exc:
        cli.error(str(exc))
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
