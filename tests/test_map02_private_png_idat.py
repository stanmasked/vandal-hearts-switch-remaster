"""Synthetic PNG IDAT coverage: invented pixels, never PS1 screenshots."""
import struct
import unittest
import zlib

from tools.map02_private_png_idat import verify_idat_scanlines


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def png(raw, *, width=1, height=1, color=2, depth=8, interlace=0,
        palette=None, compressed=None, ancillary_between_idat=False):
    ihdr = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace)
    stream = zlib.compress(raw) if compressed is None else compressed
    entries = [chunk(b"IHDR", ihdr)]
    if palette is not None:
        entries.append(chunk(b"PLTE", palette))
    if ancillary_between_idat:
        halfway = len(stream) // 2
        entries.extend([
            chunk(b"IDAT", stream[:halfway]),
            chunk(b"tEXt", b"a\x00b"),
            chunk(b"IDAT", stream[halfway:]),
        ])
    else:
        entries.append(chunk(b"IDAT", stream))
    entries.append(chunk(b"IEND", b""))
    return b"\x89PNG\r\n\x1a\n" + b"".join(entries)


class PrivatePngIdatTests(unittest.TestCase):
    def test_synthetic_truecolor_decodes(self):
        self.assertEqual(verify_idat_scanlines(png(b"\x00\x12\x34\x56")), (1, 1))

    def test_rgba_two_pixels_decodes(self):
        self.assertEqual(verify_idat_scanlines(
            png(b"\x00" + b"\x11\x22\x33\x44" * 2, width=2, color=6)), (2, 1))

    def test_grayscale_low_bit_depth(self):
        self.assertEqual(verify_idat_scanlines(png(b"\x00\x80", color=0, depth=1)), (1, 1))

    def test_indexed_png_requires_real_palette(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x00", color=3, depth=8))
        self.assertEqual(verify_idat_scanlines(
            png(b"\x00\x00", color=3, depth=8, palette=b"\xff\x00\x00")), (1, 1))

    def test_one_pixel_adam7_png(self):
        self.assertEqual(verify_idat_scanlines(
            png(b"\x00\x12\x34\x56", interlace=1)), (1, 1))

    def test_corrupt_idat_zlib_even_with_recomputed_png_crc(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"", compressed=b"\x00\x01\x02\x03"))

    def test_empty_zlib_pixels_refused(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"", compressed=zlib.compress(b"")))

    def test_extra_raw_bytes_refused(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x12\x34\x56garbage"))

    def test_missing_scanline_pixels_refused(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x12\x34"))

    def test_invalid_scanline_filter_refused(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x05\x12\x34\x56"))

    def test_truncated_zlib_refused(self):
        compressed = zlib.compress(b"\x00\x12\x34\x56")
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"", compressed=compressed[:-2]))

    def test_trailing_compressed_garbage_refused(self):
        compressed = zlib.compress(b"\x00\x12\x34\x56")
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"", compressed=compressed + b"extra"))

    def test_nonconsecutive_idat_refused(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x12\x34\x56", ancillary_between_idat=True))

    def test_palette_disallowed_for_grayscale(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x00", color=0, palette=b"\x00\x00\x00"))

    def test_palette_entries_exceed_index_bit_depth(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x00", color=3, depth=1,
                                      palette=b"\x00\x00\x00" * 3))

    def test_invalid_truecolor_depth(self):
        with self.assertRaises(ValueError):
            verify_idat_scanlines(png(b"\x00\x12\x34\x56", color=2, depth=4))

    def test_two_row_filters_valid(self):
        self.assertEqual(verify_idat_scanlines(
            png(b"\x00\x01\x02\x03\x04\x04\x05\x06", height=2)), (1, 2))


if __name__ == "__main__":
    unittest.main()
