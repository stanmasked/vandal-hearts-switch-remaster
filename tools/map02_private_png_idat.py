"""Bounded PNG IDAT + scanline verification for *private* candidate screenshots.

Call only after the caller has checked PNG chunk structure and CRCs.
A valid PNG is not evidence it depicts the PS1 game or MAP02.
No third-party libraries, filesystem access or network access.
"""
from __future__ import annotations

import struct
import zlib

MAX_DECODED_IMAGE = 64 * 1024 * 1024
# Pixel channel counts from the PNG specification.
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
VALID_DEPTHS = {
    0: (1, 2, 4, 8, 16),
    2: (8, 16),
    3: (1, 2, 4, 8),
    4: (8, 16),
    6: (8, 16),
}
ADAM7 = (
    (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8),
    (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2),
    (0, 1, 1, 2),
)


def _passes(width: int, height: int, interlace: int):
    if interlace == 0:
        return [(width, height)]
    sizes = []
    for start_x, start_y, step_x, step_y in ADAM7:
        cols = 0 if width <= start_x else (width - start_x + step_x - 1) // step_x
        rows = 0 if height <= start_y else (height - start_y + step_y - 1) // step_y
        if cols and rows:
            sizes.append((cols, rows))
    return sizes


def verify_idat_scanlines(data: bytes) -> tuple[int, int]:
    """Reject unreadable zlib streams, bombs, invalid filters and PNG chunk order.

    Does not reconstruct pixels, interpret colors, inspect gameplay, or authenticate
    the origin of the file. data must already have passed PNG CRC verification.
    """
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG signature absent")
    offset = 8
    bit_depth = color_type = interlace = None
    width = height = None
    palette_entries = 0
    had_palette = False
    had_idat = False
    finished_idat = False
    compressed = []
    chunks = 0
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if size > len(data) or end > len(data):
            raise ValueError("invalid PNG chunk length")
        payload = data[offset + 8:offset + 8 + size]
        offset = end
        chunks += 1
        if chunks > 20001:
            raise ValueError("too many PNG chunks")
        if chunks == 1:
            if kind != b"IHDR" or size != 13:
                raise ValueError("PNG header missing")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if (not 1 <= width <= 8192 or not 1 <= height <= 8192
                    or width * height > 40_000_000
                    or color_type not in VALID_DEPTHS
                    or bit_depth not in VALID_DEPTHS[color_type]
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)):
                raise ValueError("unsupported PNG pixel configuration")
        elif kind == b"PLTE":
            if had_idat or had_palette or color_type in (0, 4) or not (3 <= size <= 768 and size % 3 == 0):
                raise ValueError("invalid PNG palette")
            had_palette = True
            palette_entries = size // 3
        elif kind == b"IDAT":
            if finished_idat:
                raise ValueError("PNG IDAT must be consecutive")
            had_idat = True
            compressed.append(payload)
        elif kind == b"IEND":
            if not had_idat or not (color_type != 3 or had_palette) or size != 0 or offset != len(data):
                raise ValueError("incomplete PNG image")
            break
        elif had_idat:
            finished_idat = True
        if kind == b"IHDR" and chunks != 1:
            raise ValueError("duplicate IHDR")
    else:
        raise ValueError("PNG IEND missing")
    if color_type == 3 and palette_entries > (1 << bit_depth):
        raise ValueError("indexed PNG palette exceeds bit depth")
    if not had_idat:
        raise ValueError("PNG lacks image data")

    row_sizes = []
    for cols, rows in _passes(width, height, interlace):
        bytes_per_row = (cols * CHANNELS[color_type] * bit_depth + 7) // 8
        row_sizes.extend([bytes_per_row] * rows)
        if sum(row_sizes) + len(row_sizes) > MAX_DECODED_IMAGE:
            raise ValueError("PNG decompressed pixel limit exceeded")
    expected = sum(row_sizes) + len(row_sizes)
    if expected < 2 or expected > MAX_DECODED_IMAGE:
        raise ValueError("invalid expanded PNG size")
    decompressor = zlib.decompressobj()
    # Output is strictly bounded, regardless of malicious zlib expansion.
    try:
        pixels = decompressor.decompress(b"".join(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid PNG compressed pixels") from exc
    if (not decompressor.eof or decompressor.unused_data
            or decompressor.unconsumed_tail or len(pixels) != expected):
        raise ValueError("PNG compressed payload truncated, oversized or trailing data")
    pos = 0
    for bytes_per_row in row_sizes:
        if pixels[pos] not in (0, 1, 2, 3, 4):
            raise ValueError("invalid PNG scanline filter")
        pos += bytes_per_row + 1
    if pos != expected:
        raise ValueError("incorrect PNG scanline layout")
    return width, height
