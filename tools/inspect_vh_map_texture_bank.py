#!/usr/bin/env python3
"""Read-only, bounded inspector for Vandal Hearts map texture/CLUT resources.

The original LoadMapTextures() consumes F_TEXxx.DAT as a raw 4bpp VRAM upload
at (320,0), 64 words wide x 256 rows. LAND_DT.DAT has 69 records of 1797 bytes:
257 UVWH entries, 257 CLUT selectors, 16*16 little-endian BGR555 colors.

Never interpret either .DAT file as a standalone TIM. No game files are bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

TEXTURE_BYTES = 64 * 256 * 2
MAP_COUNT = 69
SLOT_COUNT = 257
MAP_RECORD_BYTES = SLOT_COUNT * 4 + SLOT_COUNT + 16 * 16 * 2
LAND_BYTES = MAP_COUNT * MAP_RECORD_BYTES
SECTOR_BYTES = 2352
SECTOR_DATA_OFFSET = 24
SECTOR_USER_BYTES = 2048
PS1_SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def extract_mode2_file(image, lba, byte_count):
    """Read precisely byte_count payload bytes from Mode-2 Form-1 raw sectors."""
    if lba < 0 or byte_count < 0 or byte_count > LAND_BYTES:
        raise ValueError("invalid disc LBA or extraction byte length")
    sectors = (byte_count + SECTOR_USER_BYTES - 1) // SECTOR_USER_BYTES
    start = lba * SECTOR_BYTES
    if start + sectors * SECTOR_BYTES > image.stat().st_size:
        raise ValueError("disc image is truncated at requested sector range")
    out = bytearray()
    with image.open("rb") as handle:
        handle.seek(start)
        for index in range(sectors):
            sector = handle.read(SECTOR_BYTES)
            if (len(sector) != SECTOR_BYTES or sector[:12] != PS1_SYNC or
                    sector[15] != 2):
                raise ValueError(f"invalid raw Mode-2 sector at LBA {lba + index}")
            # Mode-2 Form-1 submode bit 0x20 is clear in BOTH XA subheaders.
            if (sector[18] & 0x20 or sector[22] & 0x20 or
                    sector[16:20] != sector[20:24]):
                raise ValueError(f"not a Mode-2 Form-1 data sector at LBA {lba + index}")
            out.extend(sector[SECTOR_DATA_OFFSET:
                              SECTOR_DATA_OFFSET + SECTOR_USER_BYTES])
    return bytes(out[:byte_count])


def inspect_bank(texture, land, map_number):
    if len(texture) != TEXTURE_BYTES:
        raise ValueError(f"expected {TEXTURE_BYTES} 4bpp texture bytes")
    if len(land) != LAND_BYTES:
        raise ValueError(f"expected {LAND_BYTES} LAND_DT bytes")
    if not 0 <= map_number < MAP_COUNT:
        raise ValueError(f"map index must be between 0 and {MAP_COUNT - 1}")
    base = map_number * MAP_RECORD_BYTES
    record = land[base:base + MAP_RECORD_BYTES]
    uvwh = [list(record[i * 4:i * 4 + 4]) for i in range(SLOT_COUNT)]
    clut = list(record[SLOT_COUNT * 4:SLOT_COUNT * 5])
    palette_words = struct.unpack_from("<256H", record, SLOT_COUNT * 5)
    # The first 32 gClutIds are initialized in SetupGfx. The LAND_DT
    # palettes replace indices 32..47 with 16 rows at VRAM (672,496).
    row_counts = {str(n): clut.count(n) for n in range(32, 48)}
    return {
        "format": "VH_MAP_TEXTURE_BANK_RAW_4BPP",
        "map_number": map_number,
        "texture_vram_rect_words": [320, 0, 64, 256],
        "texture_pixels": [256, 256],
        "palette_vram_rect_words": [672, 496, 16, 16],
        "texture_slots": SLOT_COUNT,
        "slot_uvwh": uvwh,
        "slot_clut_ids": clut,
        "local_clut_usage": row_counts,
        "unmapped_clut_ids": sorted(set(clut) - set(range(32, 48))),
        "palette_nonzero_words": sum(w != 0 for w in palette_words),
        "texture_sha256": hashlib.sha256(texture).hexdigest(),
        "land_dt_sha256": hashlib.sha256(land).hexdigest(),
    }


def _png_chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def render_palette_png(texture, land, map_number, slot):
    """Preview full page with the specified slot's palette; not a game frame."""
    if not 0 <= slot < SLOT_COUNT:
        raise ValueError("texture slot is outside 0..256")
    inspect_bank(texture, land, map_number)
    base = map_number * MAP_RECORD_BYTES
    palette_id = land[base + 4 * SLOT_COUNT + slot]
    if not 32 <= palette_id <= 47:
        raise ValueError(f"slot {slot} uses CLUT {palette_id}, not local rows 32..47")
    offset = base + 5 * SLOT_COUNT + (palette_id - 32) * 32
    colors = struct.unpack_from("<16H", land, offset)
    rgba = [(
        ((c & 31) * 255 + 15) // 31,
        (((c >> 5) & 31) * 255 + 15) // 31,
        (((c >> 10) & 31) * 255 + 15) // 31,
        0 if c == 0 else 255,
    ) for c in colors]
    # 4bpp PS1 texels: low nibble is left pixel, high nibble right.
    rows = bytearray()
    for y in range(256):
        rows.append(0)  # PNG filter type 0
        for packed in texture[y * 128:(y + 1) * 128]:
            rows.extend(rgba[packed & 15])
            rows.extend(rgba[packed >> 4])
    header = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 256, 256, 8, 6, 0, 0, 0)
    return (header + _png_chunk(b"IHDR", ihdr) +
            _png_chunk(b"IDAT", zlib.compress(bytes(rows))) +
            _png_chunk(b"IEND", b""))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    files = p.add_mutually_exclusive_group(required=True)
    files.add_argument("--texture", type=Path, help="extracted F_TEXxx.DAT")
    files.add_argument("--raw-bin", type=Path, help="user-owned raw 2352-byte-sector BIN")
    p.add_argument("--land", type=Path, help="extracted LAND_DT.DAT (required with --texture)")
    p.add_argument("--texture-lba", type=int, help="ISO Mode-2 data LBA for texture file")
    p.add_argument("--land-lba", type=int, help="ISO Mode-2 data LBA for LAND_DT")
    p.add_argument("--map", type=int, required=True, dest="map_number")
    p.add_argument("--preview-png", type=Path, help="optional local 256x256 palette preview")
    p.add_argument("--slot", type=int, help="palette-selector slot (required for PNG)")
    args = p.parse_args(argv)
    if args.raw_bin:
        if args.land or args.texture_lba is None or args.land_lba is None:
            p.error("--raw-bin requires --texture-lba and --land-lba; omit --land")
        texture = extract_mode2_file(args.raw_bin, args.texture_lba, TEXTURE_BYTES)
        land = extract_mode2_file(args.raw_bin, args.land_lba, LAND_BYTES)
    else:
        if not args.land or args.texture_lba is not None or args.land_lba is not None:
            p.error("--texture requires --land; omit LBA options")
        if args.texture.stat().st_size != TEXTURE_BYTES or args.land.stat().st_size != LAND_BYTES:
            p.error("wrong F_TEX or LAND_DT file size")
        texture = args.texture.read_bytes()
        land = args.land.read_bytes()
    try:
        report = inspect_bank(texture, land, args.map_number)
        if args.preview_png:
            if args.slot is None:
                p.error("--preview-png requires --slot")
            png = render_palette_png(texture, land, args.map_number, args.slot)
            args.preview_png.write_bytes(png)
            report["preview_palette_slot"] = args.slot
            report["preview_path"] = str(args.preview_png)
        elif args.slot is not None:
            p.error("--slot requires --preview-png")
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
