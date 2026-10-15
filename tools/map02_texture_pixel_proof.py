#!/usr/bin/env python3
"""Build a read-only MAP02 PRS-vs-DAT four-swatch PNG from a user-owned BIN.

This is an indexed-atlas *source pixel* comparison, NOT a rendered scene:
no projection, polygon UV transformations, PS1 dither or semi-transparency
are simulated. The output preserves raw BGR555/STP SHA-256 fingerprints.
Game resource bytes and output images remain local; no assets in this repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from tools.audit_map02_disc_prs import (
    DAT_SECTOR_COUNT, DAT_START_SECTOR, PRIOR_DAT_LENGTH,
    SECTOR_COUNT, START_SECTOR, USER_BYTES, audit_prs,
    read_sectors, unpack_prs,
)
from tools.compare_map02_variants import EXPECTED_LENGTH, FACE_GFX_OFFSET, RECORD_SIZE

ATLAS_LBA, ATLAS_SECTORS, ATLAS_LENGTH = 4374, 16, 32768
LAND_LBA, LAND_SECTORS, LAND_LENGTH = 4954, 61, 123993
LAND_BLOCK_INDEX, LAND_BLOCK_SIZE = 11, 1797
PALETTE_OFFSET = 1285
PALETTE_SLOT_OFFSET = 32
TILE_UV_SIZE = 4
ATLAS_STRIDE = 128
EXPECTED_ATLAS_SHA256 = "a3c6db4516930cdb2555cf7cda2456bcd118e5ec46737e2c320431d7b9a63b75"
EXPECTED_LAND_SHA256 = "e91891bad10efbc58ee010a52740c1510383529fcbf24eec3783e344cbcf773b"
TARGETS = (
    (8, 19, 241, 98),
    (11, 11, 243, 150),
)
SLOT_REFERENCES = {
    98: ((64, 96, 15, 15), 35,
         "b25ca5d0a1ec44fe1ca1584156089119546984409801a7d9e93b5534d53d48c2"),
    150: ((224, 128, 15, 15), 33,
          "9f32f4abb2c1f9f64c905846a9c290e1b39bd693ed8c3c9eedf41dd368635650"),
    241: ((240, 192, 15, 15), 35,
          "f4bea843b56988a75d08dcf5a14eee7ff342ac27bbb5a8a15b6ec9d77c760e94"),
    243: ((240, 208, 15, 15), 33,
          "e908950095f3cb21a7635b0d7923e346fac4959fb57519caf60c598808a09d7b"),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sample_slot(atlas: bytes, land_record: bytes, slot: int) -> dict:
    """Read 4-bit atlas texels and CLUT, retaining exact 16-bit palette values."""
    if len(atlas) != ATLAS_LENGTH or len(land_record) != LAND_BLOCK_SIZE:
        raise ValueError("atlas or LAND_DT record length is incorrect")
    if slot not in SLOT_REFERENCES:
        raise ValueError(f"unsupported MAP02 source slot {slot}")
    u, v, w, h = land_record[slot * TILE_UV_SIZE:(slot + 1) * TILE_UV_SIZE]
    clut = land_record[1028 + slot]
    if w < 1 or h < 1 or u + w >= 256 or v + h >= 256:
        raise ValueError(f"invalid UV dimensions for GFX {slot}")
    if not (PALETTE_SLOT_OFFSET <= clut < 48):
        raise ValueError(f"invalid CLUT for GFX {slot}: {clut}")
    palette_start = PALETTE_OFFSET + (clut - PALETTE_SLOT_OFFSET) * 32
    palette = struct.unpack_from("<16H", land_record, palette_start)
    words = []
    indices = []
    for iy in range(h + 1):
        for ix in range(w + 1):
            px, py = u + ix, v + iy
            packed = atlas[py * ATLAS_STRIDE + px // 2]
            idx = (packed >> (4 * (px & 1))) & 15
            indices.append(idx)
            words.append(palette[idx])
    pixel_key = struct.pack("<HH", w + 1, h + 1) + struct.pack(
        f"<{len(words)}H", *words)
    expected_uv, expected_clut, expected_pixel_sha = SLOT_REFERENCES[slot]
    return {
        "slot": slot,
        "uvwh": [u, v, w, h],
        "clut_index": clut,
        "width": w + 1,
        "height": h + 1,
        "raw_color_words": words,
        "palette_indices": indices,
        "decoded_pixels_sha256": sha(pixel_key),
        "matches_archived_pixels": (
            (u, v, w, h) == expected_uv
            and clut == expected_clut
            and sha(pixel_key) == expected_pixel_sha
        ),
        "raw_zero_pixels": sum(value == 0 for value in words),
        "stp_flag_pixels": sum(bool(value & 0x8000) for value in words),
    }


def color8(v: int) -> int:
    """5-bit PS1 channel to 8-bit without gamma, tone mapping or dithering."""
    return (v << 3) | (v >> 2)


def swatch_rgb(words: list[int], width: int, height: int) -> bytes:
    if len(words) != width * height:
        raise ValueError("pixel buffer length does not match dimensions")
    pixels = bytearray()
    for word in words:
        # Source BGR555/STP: bits 0..4 R, 5..9 G, 10..14 B, bit 15 STP.
        pixels.extend((color8(word & 31),
                       color8((word >> 5) & 31),
                       color8((word >> 10) & 31)))
    return bytes(pixels)


def make_contact_sheet(samples: list[dict], *, scale: int = 8, margin: int = 12) -> tuple[int, int, bytes, list]:
    """Two rows (face 0 targets), two columns (PRS, DAT), opaque RGB only."""
    if len(samples) != 4 or not (1 <= scale <= 32) or margin < 1:
        raise ValueError("expected four samples, valid scale and positive margin")
    if any(item["width"] != 16 or item["height"] != 16 for item in samples):
        raise ValueError("MAP02 comparison requires four 16x16 source swatches")
    panel = 16 * scale
    width = panel * 2 + margin * 3
    height = panel * 2 + margin * 3
    framebuffer = bytearray(bytes((40, 43, 49)) * (width * height))
    panels = []
    for index, item in enumerate(samples):
        row, col = divmod(index, 2)
        ox = margin + col * (panel + margin)
        oy = margin + row * (panel + margin)
        src = swatch_rgb(item["raw_color_words"], 16, 16)
        for py in range(16):
            for px in range(16):
                color = src[(py * 16 + px) * 3:(py * 16 + px + 1) * 3]
                for dy in range(scale):
                    start = ((oy + py * scale + dy) * width + ox + px * scale) * 3
                    framebuffer[start:start + scale * 3] = color * scale
        panels.append({"row": row, "column": col, "slot": item["slot"],
                       "x": ox, "y": oy, "width": panel, "height": panel})
    return width, height, bytes(framebuffer), panels


def encode_png(width: int, height: int, rgb: bytes) -> bytes:
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError("invalid RGB image dimensions")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)

    raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3]
                   for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def build_evidence(image: Path, layout: str, bias: int = 0) -> tuple[dict, bytes]:
    """Collect relevant owned-disc resources without exporting source bytes."""
    prs = read_sectors(image, layout, bias, start_sector=START_SECTOR,
                       sector_count=SECTOR_COUNT)
    dat = read_sectors(image, layout, bias, start_sector=DAT_START_SECTOR,
                       sector_count=DAT_SECTOR_COUNT)[:PRIOR_DAT_LENGTH]
    atlas = read_sectors(image, layout, bias, start_sector=ATLAS_LBA,
                         sector_count=ATLAS_SECTORS)[:ATLAS_LENGTH]
    land = read_sectors(image, layout, bias, start_sector=LAND_LBA,
                        sector_count=LAND_SECTORS)[:LAND_LENGTH]
    cd_report = audit_prs(prs, dat)
    decoded = unpack_prs(prs)
    if len(decoded) != EXPECTED_LENGTH:
        raise ValueError("decoded map length incorrect")
    record = land[LAND_BLOCK_INDEX * LAND_BLOCK_SIZE:
                  (LAND_BLOCK_INDEX + 1) * LAND_BLOCK_SIZE]
    if len(record) != LAND_BLOCK_SIZE:
        raise ValueError("LAND_DT record 11 not present")
    slots = []
    for z, x, prs_slot, dat_slot in TARGETS:
        index = z * 28 + x
        if decoded[index * RECORD_SIZE + FACE_GFX_OFFSET] != prs_slot:
            raise ValueError(f"PRS target GFX mismatch at z={z}, x={x}")
        if dat[index * RECORD_SIZE + FACE_GFX_OFFSET] != dat_slot:
            raise ValueError(f"DAT target GFX mismatch at z={z}, x={x}")
        slots.extend((sample_slot(atlas, record, prs_slot),
                      sample_slot(atlas, record, dat_slot)))
    verification = {
        "compressed_prs_sha256": cd_report["matches_prior_logical_compressed_sha256"],
        "decompressed_prs_sha256": cd_report["matches_prior_decompressed_sha256"],
        "dat_sha256": cd_report["dat_comparison"]["matches_prior_dat_sha256"],
        "two_byte_prs_dat_difference": cd_report["dat_comparison"]["matches_prior_disc_audit"],
        "atlas_sha256": sha(atlas) == EXPECTED_ATLAS_SHA256,
        "land_dt_sha256": sha(land) == EXPECTED_LAND_SHA256,
        "all_four_pixel_sha256": all(sample["matches_archived_pixels"] for sample in slots),
    }
    w, h, framebuffer, panels = make_contact_sheet(slots)
    png = encode_png(w, h, framebuffer)
    metadata = {
        "schema": "map02_prs_dat_pixel_proof_v1",
        "source": str(image),
        "source_layout": layout,
        "sector_bias": bias,
        "verification": verification,
        "all_archived_evidence_matches": all(verification.values()),
        "atlas_sha256": sha(atlas),
        "land_dt_sha256": sha(land),
        "prs_decompressed_sha256": cd_report["decompressed_sha256"],
        "dat_sha256": cd_report["dat_comparison"]["dat_sha256"],
        "swatches": [
            {k: v for k, v in sample.items()
             if k not in ("raw_color_words", "palette_indices")}
            for sample in slots
        ],
        "png_panels": panels,
        "png_width": w,
        "png_height": h,
        "caveats": [
            "Flat source UV/CLUT samples, not captured gameplay or polygon projection",
            "RGB preview ignores PS1 STP blending, transparency, dithering and camera angle",
            "PS1 raw 16-bit BGR555/STP fingerprints are retained in the metadata",
        ],
    }
    return metadata, png


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc-image", type=Path, required=True)
    parser.add_argument("--layout", choices=("mode2-2352", "iso-2048"), required=True)
    parser.add_argument("--sector-bias", type=int, default=0)
    parser.add_argument("--output-prefix", type=Path, required=True,
                        help="write prefix.png and prefix.json outside version control")
    parser.add_argument("--allow-unverified-source", action="store_true",
                        help="explicitly allow source hashes differing from archived RU audit")
    args = parser.parse_args()
    try:
        report, png = build_evidence(args.disc_image, args.layout, args.sector_bias)
        if not report["all_archived_evidence_matches"] and not args.allow_unverified_source:
            raise ValueError("source data differs from archived map02 evidence; use --allow-unverified-source")
        target_png = Path(str(args.output_prefix) + ".png")
        target_json = Path(str(args.output_prefix) + ".json")
        if target_png.exists() or target_json.exists():
            raise ValueError("output already exists; refuse to overwrite a previous evidence bundle")
        if not target_png.parent.is_dir():
            raise ValueError("output directory does not exist")
        target_png.write_bytes(png)
        target_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"png": str(target_png), "json": str(target_json),
                      "all_archived_evidence_matches": report["all_archived_evidence_matches"],
                      "swatches": [item["slot"] for item in report["swatches"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
