"""Private-only normalized pixel digest for 8-bit non-interlaced PNGs.

The caller must independently verify PNG CRC/chunk order and IDAT validity.
No PIL, network, files, game assets, or image/hash output. Returns None for
other PNG pixel configurations rather than making a false mismatch claim.
This does not verify PS1 provenance or MAP02 scene identity.
"""
from __future__ import annotations

import hashlib
import struct
import zlib

from tools.map02_private_png_idat import MAX_DECODED_IMAGE
from tools.verify_map02_private_visual_candidates import png_header_and_crc
from tools.map02_private_png_idat import verify_idat_scanlines

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth(left: int, upper: int, upper_left: int) -> int:
    prediction = left + upper - upper_left
    a = abs(prediction - left)
    b = abs(prediction - upper)
    c = abs(prediction - upper_left)
    if a <= b and a <= c:
        return left
    if b <= c:
        return upper
    return upper_left


def private_normalized_pixel_sha256(png: bytes) -> bytes | None:
    """Digest reconstructed 8-bit RGB/RGBA pixel bytes, or None if unsupported.

    Filtered scanline bytes, IDAT compression and ancillary PNG metadata are
    ignored; width/height/channel count are included in the private digest.
    Raises ValueError for invalid PNGs. Returned digest is never printed.
    """
    width, height = png_header_and_crc(png)
    verify_idat_scanlines(png)
    if not png.startswith(PNG_SIG):
        raise ValueError("PNG signature absent")
    end = 8
    idat = []
    pixel_channels = None
    while end < len(png):
        length = struct.unpack_from(">I", png, end)[0]
        kind = png[end + 4:end + 8]
        data = png[end + 8:end + 8 + length]
        end += 12 + length
        if kind == b"IHDR":
            w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", data)
            if (w, h) != (width, height):
                raise ValueError("PNG dimensions inconsistent")
            if depth == 8 and interlace == 0 and color in (2, 6):
                pixel_channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat.append(data)
        elif kind == b"IEND":
            break
    if pixel_channels is None:
        return None
    stride = width * pixel_channels
    expanded_size = height * (stride + 1)
    if not 0 < expanded_size <= MAX_DECODED_IMAGE:
        raise ValueError("PNG expanded pixel size outside bounded range")
    inflator = zlib.decompressobj()
    try:
        raw = inflator.decompress(b"".join(idat), expanded_size + 1)
    except zlib.error as exc:
        raise ValueError("PNG IDAT decompression failed") from exc
    if (len(raw) != expanded_size or not inflator.eof
            or inflator.unused_data or inflator.unconsumed_tail):
        raise ValueError("PNG expanded data malformed")

    result = hashlib.sha256()
    result.update(struct.pack(">IIB", width, height, pixel_channels))
    prior = bytearray(stride)
    offset = 0
    for _ in range(height):
        style = raw[offset]
        offset += 1
        filtered = raw[offset:offset + stride]
        offset += stride
        row = bytearray(stride)
        for i, value in enumerate(filtered):
            left = row[i - pixel_channels] if i >= pixel_channels else 0
            upper = prior[i]
            upper_left = prior[i - pixel_channels] if i >= pixel_channels else 0
            if style == 0:
                predictor = 0
            elif style == 1:
                predictor = left
            elif style == 2:
                predictor = upper
            elif style == 3:
                predictor = (left + upper) // 2
            elif style == 4:
                predictor = _paeth(left, upper, upper_left)
            else:
                raise ValueError("PNG scanline filter is invalid")
            row[i] = (value + predictor) & 0xff
        result.update(row)
        prior = row
    return result.digest()
