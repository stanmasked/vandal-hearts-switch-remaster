"""Strict pixel decoder for OWNER-PRIVATE BizHawk review PNGs.

No external image libraries or image export. Accepts only PNG with 8-bit
non-interlaced grayscale/RGB/(opaque) GA/RGBA data. Rejects other formats
rather than guessing colors. PNG envelope/CRC/zlib validated independently
before this function is called. Output is uncropped RGB pixels, not PS1 VRAM.
"""
from __future__ import annotations

import struct
import zlib

from tools.verify_map02_private_visual_candidates import png_header_and_crc
from tools.map02_private_png_idat import verify_idat_scanlines

MAX_PIXELS = 4_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}


def decode_private_rgb8(data: bytes) -> tuple[int, int, bytes]:
    """Return width,height,RGB bytes; fail closed for unsupported screenshot formats."""
    png_header_and_crc(data)
    verify_idat_scanlines(data)
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not PNG")
    offset = 8
    width = height = depth = color = interlace = None
    idats = []
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:offset + 8 + length]
        offset += length + 12
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idats.append(body)
        elif kind == b"IEND":
            break
    if (color not in CHANNELS or depth != 8 or interlace != 0
            or width * height > MAX_PIXELS):
        raise ValueError("visual comparison requires <=4MP noninterlaced 8-bit gray/RGB/RGBA PNG")
    samples = CHANNELS[color]
    row_length = width * samples
    expected = height * (row_length + 1)
    # Input was independently validated, but impose the same explicit limit.
    decompress = zlib.decompressobj()
    try:
        raw = decompress.decompress(b"".join(idats), expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid PNG compression") from exc
    if (not decompress.eof or decompress.unused_data
            or decompress.unconsumed_tail or len(raw) != expected):
        raise ValueError("invalid PNG scanline sizes")

    last = bytearray(row_length)
    rgb = bytearray(width * height * 3)
    out = 0
    pos = 0
    for _ in range(height):
        f = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + row_length])
        pos += 1 + row_length
        for i in range(row_length):
            a = row[i - samples] if i >= samples else 0
            b = last[i]
            c = last[i - samples] if i >= samples else 0
            if f == 0:
                value = 0
            elif f == 1:
                value = a
            elif f == 2:
                value = b
            elif f == 3:
                value = (a + b) // 2
            elif f == 4:
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                value = a if da <= db and da <= dc else b if db <= dc else c
            else:
                raise ValueError("invalid PNG filter")
            row[i] = (row[i] + value) & 255
        for j in range(0, row_length, samples):
            if color == 0:
                r = g = b = row[j]
            elif color == 2:
                r, g, b = row[j], row[j + 1], row[j + 2]
            elif color == 4:
                if row[j + 1] != 255:
                    raise ValueError("nonopaque grayscale screenshot cannot be compared without compositing")
                r = g = b = row[j]
            else:
                if row[j + 3] != 255:
                    raise ValueError("nonopaque RGBA screenshot cannot be compared without compositing")
                r, g, b = row[j], row[j + 1], row[j + 2]
            rgb[out:out + 3] = bytes((r, g, b))
            out += 3
        last = row
    return width, height, bytes(rgb)


def compare_private_rgb8(first: tuple[int, int, bytes],
                         second: tuple[int, int, bytes],
                         *, threshold: int = 32) -> dict:
    """Raw screenshot-difference proxy, NOT a scene-transition classifier.

    Pixel is marked changed if the average absolute RGB channel difference
    strictly exceeds threshold. No chromatic adaptation, UI masks or scaling.
    """
    if type(threshold) is not int or not 0 <= threshold <= 254:
        raise ValueError("pixel change threshold must be integer 0..254")
    width, height, before = first
    next_width, next_height, after = second
    if (width != next_width or height != next_height
            or len(before) != len(after)
            or len(before) != width * height * 3):
        raise ValueError("screenshot resolution or pixel buffer differs")
    total = 0
    changed = 0
    for idx in range(0, len(before), 3):
        magnitude = (abs(before[idx] - after[idx])
                     + abs(before[idx + 1] - after[idx + 1])
                     + abs(before[idx + 2] - after[idx + 2]))
        total += magnitude
        if magnitude > 3 * threshold:
            changed += 1
    count = width * height
    return {
        "mean_absolute_rgb_channel_delta": round(total / (3 * count), 4),
        "fraction_pixels_above_threshold": round(changed / count, 6),
    }
