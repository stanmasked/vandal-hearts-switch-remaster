"""Asset-free regressions for original Vandal Hearts map texture-bank layout."""
import struct
import sys
import tempfile
from pathlib import Path
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_texture_bank import (  # noqa: E402
    LAND_BYTES, MAP_RECORD_BYTES, PS1_SYNC, SECTOR_BYTES, SLOT_COUNT,
    TEXTURE_BYTES, extract_mode2_file, inspect_bank, render_palette_png,
)


def fixtures():
    texture = bytes([0x21]) * TEXTURE_BYTES
    land = bytearray(LAND_BYTES)
    base = 11 * MAP_RECORD_BYTES
    land[base:base + 4] = bytes([16, 24, 15, 15])
    land[base + 4 * SLOT_COUNT] = 32  # first LOCAL CLUT row
    land[base + 4 * SLOT_COUNT + 241] = 35
    palette_start = base + 5 * SLOT_COUNT
    struct.pack_into("<HHH", land, palette_start, 0, 0x001F, 0x03E0)
    struct.pack_into("<H", land, palette_start + 3 * 32 + 2, 0x7C00)
    return texture, bytes(land)


def make_raw_bin(texture, land, tex_lba=5, land_lba=30):
    """A local Mode2 Form1 BIN mock; no copyrighted data."""
    payloads = ((tex_lba, texture), (land_lba, land))
    max_sector = max(start + (len(data) + 2047) // 2048
                     for start, data in payloads)
    result = bytearray(SECTOR_BYTES * max_sector)
    for lba, data in payloads:
        for idx in range((len(data) + 2047) // 2048):
            offset = (lba + idx) * SECTOR_BYTES
            result[offset:offset + 12] = PS1_SYNC
            result[offset + 15] = 2
            # XA Mode2 subheaders both zero = Form1 data.
            block = data[idx * 2048:(idx + 1) * 2048]
            result[offset + 24:offset + 24 + len(block)] = block
    return bytes(result)


class TextureBankTests(unittest.TestCase):
    def setUp(self):
        self.texture, self.land = fixtures()

    def test_exact_map_record_layout(self):
        self.assertEqual(MAP_RECORD_BYTES, 1797)
        self.assertEqual(LAND_BYTES, 123993)
        self.assertEqual(TEXTURE_BYTES, 32768)
        self.assertEqual(SLOT_COUNT, 257)

    def test_extract_map_11_uvwh_and_clut(self):
        info = inspect_bank(self.texture, self.land, 11)
        self.assertEqual(info["texture_vram_rect_words"], [320, 0, 64, 256])
        self.assertEqual(info["palette_vram_rect_words"], [672, 496, 16, 16])
        self.assertEqual(info["texture_pixels"], [256, 256])
        self.assertEqual(info["slot_uvwh"][0], [16, 24, 15, 15])
        self.assertEqual(info["slot_clut_ids"][0], 32)
        self.assertEqual(info["slot_clut_ids"][241], 35)
        self.assertEqual(info["local_clut_usage"]["35"], 1)

    def test_preview_png_uses_ps1_nibble_order_and_bgr555(self):
        png = render_palette_png(self.texture, self.land, 11, 0)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack_from(">II", png, 16), (256, 256))
        # Decode only IDAT from the generated PNG.
        idx = 8
        chunks = {}
        while idx < len(png):
            length = struct.unpack_from(">I", png, idx)[0]
            tag = png[idx + 4:idx + 8]
            chunks[tag] = png[idx + 8:idx + 8 + length]
            idx += length + 12
        rgba = zlib.decompress(chunks[b"IDAT"])
        self.assertEqual(rgba[0], 0)
        self.assertEqual(tuple(rgba[1:5]), (255, 0, 0, 255))
        self.assertEqual(tuple(rgba[5:9]), (0, 255, 0, 255))
        self.assertEqual(tuple(rgba[9:13]), (255, 0, 0, 255))

    def test_preview_transparent_word_not_palette_index(self):
        land = bytearray(self.land)
        off = 11 * MAP_RECORD_BYTES + 5 * SLOT_COUNT
        struct.pack_into("<H", land, off, 0x9C87)  # nonzero index 0
        texture = bytes([0]) * TEXTURE_BYTES
        png = render_palette_png(texture, bytes(land), 11, 0)
        off = png.index(b"IDAT")
        size = struct.unpack_from(">I", png, off - 4)[0]
        raw = zlib.decompress(png[off + 4:off + 4 + size])
        self.assertEqual(raw[4], 255)  # CLUT index 0 is *opaque* here

    def test_invalid_palette_slot(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            render_palette_png(self.texture, self.land, 11, 257)
        with self.assertRaisesRegex(ValueError, "not local"):
            render_palette_png(self.texture, self.land, 0, 0)

    def test_reject_wrong_texture_length(self):
        with self.assertRaisesRegex(ValueError, "texture bytes"):
            inspect_bank(self.texture[:-1], self.land, 11)

    def test_reject_wrong_land_size(self):
        with self.assertRaisesRegex(ValueError, "LAND_DT"):
            inspect_bank(self.texture, self.land[:-1], 11)

    def test_reject_invalid_map_index(self):
        for index in (-1, 69):
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "map index"):
                inspect_bank(self.texture, self.land, index)

    def test_mode2_bin_exact_cross_sector_read(self):
        image = make_raw_bin(self.texture, self.land)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.bin"
            path.write_bytes(image)
            self.assertEqual(extract_mode2_file(path, 5, TEXTURE_BYTES), self.texture)
            self.assertEqual(extract_mode2_file(path, 30, LAND_BYTES), self.land)

    def test_reject_invalid_mode2_sync(self):
        image = bytearray(make_raw_bin(self.texture, self.land))
        image[5 * SECTOR_BYTES] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.bin"
            path.write_bytes(image)
            with self.assertRaisesRegex(ValueError, "raw Mode-2"):
                extract_mode2_file(path, 5, TEXTURE_BYTES)

    def test_reject_invalid_xa_form2_submode(self):
        image = bytearray(make_raw_bin(self.texture, self.land))
        start = 5 * SECTOR_BYTES
        image[start + 18] = 0x20
        image[start + 22] = 0x20
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "form2.bin"
            path.write_bytes(image)
            with self.assertRaisesRegex(ValueError, "Form-1"):
                extract_mode2_file(path, 5, TEXTURE_BYTES)

    def test_reject_truncated_disc_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated.bin"
            path.write_bytes(make_raw_bin(self.texture, self.land)[:-2352])
            with self.assertRaisesRegex(ValueError, "truncated"):
                extract_mode2_file(path, 30, LAND_BYTES)

    def test_reject_negative_lba_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.bin"
            path.write_bytes(b"")
            for lba, size in ((-1, 2048), (0, LAND_BYTES + 1), (0, -1)):
                with self.subTest(lba=lba, size=size), self.assertRaisesRegex(ValueError, "invalid"):
                    extract_mode2_file(path, lba, size)


if __name__ == "__main__":
    unittest.main()
