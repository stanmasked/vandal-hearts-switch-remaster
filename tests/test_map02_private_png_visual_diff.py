"""Completely fabricated PNG data, testing filters and pixel-diff invariants."""
import struct
import unittest
import zlib

from tools.map02_private_png_visual_diff import (
    decode_private_rgb8, compare_private_rgb8,
)


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def filters_encode(rows, sample_count=3, filters=(0,)):
    result = bytearray()
    previous = bytes(len(rows[0]))
    for row_idx, row in enumerate(rows):
        f = filters[row_idx % len(filters)]
        result.append(f)
        for i, v in enumerate(row):
            a = row[i - sample_count] if i >= sample_count else 0
            b = previous[i]
            c = previous[i - sample_count] if i >= sample_count else 0
            if f == 0:
                predictor = 0
            elif f == 1:
                predictor = a
            elif f == 2:
                predictor = b
            elif f == 3:
                predictor = (a + b) // 2
            else:
                p = a + b - c
                da, db, dc = abs(p - a), abs(p - b), abs(p - c)
                predictor = a if da <= db and da <= dc else b if db <= dc else c
            result.append((v - predictor) % 256)
        previous = row
    return bytes(result)


def synthetic_png(rows, *, channels=3, color=2, depth=8, interlace=0,
                  filters=(0,), palette=None, compression=None):
    width = len(rows[0]) // channels
    header = struct.pack(">IIBBBBB", width, len(rows), depth, color, 0, 0, interlace)
    stream = (zlib.compress(filters_encode(rows, channels, filters))
              if compression is None else compression)
    parts = [chunk(b"IHDR", header)]
    if palette is not None:
        parts.append(chunk(b"PLTE", palette))
    parts.extend((chunk(b"IDAT", stream), chunk(b"IEND", b"")))
    return b"\x89PNG\r\n\x1a\n" + b"".join(parts)


class PrivateRgb8ScreenshotTests(unittest.TestCase):
    def test_unfiltered_two_by_two_rgb(self):
        rows = [bytes((0, 10, 20, 30, 40, 50)),
                bytes((60, 70, 80, 90, 100, 110))]
        width, height, rgb = decode_private_rgb8(synthetic_png(rows))
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(rgb, b"".join(rows))

    def test_all_five_png_filter_types(self):
        rows = [
            bytes((11, 22, 33, 44, 55, 66)),
            bytes((21, 32, 43, 54, 65, 76)),
        ]
        for f in (0, 1, 2, 3, 4):
            with self.subTest(filter=f):
                self.assertEqual(
                    decode_private_rgb8(synthetic_png(rows, filters=(f,)))[2],
                    b"".join(rows))

    def test_mix_of_png_filters_reconstructs_row_delta(self):
        rows = [bytes((10, 20, 30)), bytes((40, 50, 60)),
                bytes((61, 62, 63)), bytes((199, 150, 160)),
                bytes((7, 8, 9))]
        self.assertEqual(
            decode_private_rgb8(synthetic_png(rows, filters=(0, 1, 2, 3, 4)))[2],
            b"".join(rows))

    def test_grayscale_eight_bit_normalized_to_rgb(self):
        self.assertEqual(
            decode_private_rgb8(synthetic_png([bytes((20, 200))],
                                              color=0, channels=1))[2],
            bytes((20, 20, 20, 200, 200, 200)))

    def test_rgba_opaque_alpha_discarded(self):
        self.assertEqual(
            decode_private_rgb8(synthetic_png(
                [bytes((1, 2, 3, 255, 4, 5, 6, 255))],
                color=6, channels=4))[2], bytes((1, 2, 3, 4, 5, 6)))

    def test_rgba_transparent_pixel_rejected(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((1, 2, 3, 128))], color=6, channels=4))

    def test_gray_alpha_opaque(self):
        self.assertEqual(
            decode_private_rgb8(synthetic_png(
                [bytes((33, 255))], color=4, channels=2))[2],
            bytes((33, 33, 33)))

    def test_gray_alpha_translucent_rejected(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((33, 0))], color=4, channels=2))

    def test_indexed_png_rejected_instead_of_wrong_colors(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((0,))], color=3, channels=1,
                palette=b"\x00\x00\x00"))

    def test_sixteen_bit_rgb_rejected(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((0, 0, 0, 0, 0, 0))], color=2, channels=6, depth=16))

    def test_adam7_rejected_instead_of_guessing_pixels(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((7, 8, 9))], interlace=1))

    def test_png_crc_corruption_rejected(self):
        raw = bytearray(synthetic_png([bytes((1, 2, 3))]))
        raw[28] ^= 1
        with self.assertRaises(ValueError):
            decode_private_rgb8(bytes(raw))

    def test_bad_compression_with_valid_png_crc_rejected(self):
        with self.assertRaises(ValueError):
            decode_private_rgb8(synthetic_png(
                [bytes((1, 2, 3))], compression=b"NOT ZLIB"))

    def test_identical_images_have_zero_pixel_difference(self):
        img = (1, 1, bytes((10, 20, 30)))
        self.assertEqual(compare_private_rgb8(img, img),
                         {"mean_absolute_rgb_channel_delta": 0.0,
                          "fraction_pixels_above_threshold": 0.0})

    def test_full_black_to_white_difference(self):
        a, b = (1, 1, b"\x00" * 3), (1, 1, b"\xff" * 3)
        self.assertEqual(compare_private_rgb8(a, b),
                         {"mean_absolute_rgb_channel_delta": 255.0,
                          "fraction_pixels_above_threshold": 1.0})

    def test_pixel_difference_threshold_is_strict(self):
        before = (2, 1, bytes((0, 0, 0, 0, 0, 0)))
        after = (2, 1, bytes((32, 32, 32, 33, 33, 33)))
        self.assertEqual(
            compare_private_rgb8(before, after, threshold=32),
            {"mean_absolute_rgb_channel_delta": 32.5,
             "fraction_pixels_above_threshold": 0.5})

    def test_mismatched_screenshot_resolution_rejected(self):
        with self.assertRaises(ValueError):
            compare_private_rgb8(
                (1, 1, b"\x00" * 3), (2, 1, b"\x00" * 6))

    def test_wrong_pixel_buffer_length_rejected(self):
        with self.assertRaises(ValueError):
            compare_private_rgb8(
                (1, 1, b"\x00" * 3), (1, 1, b"\x00" * 2))

    def test_invalid_threshold_rejected(self):
        for t in (-1, 255, True, 4.5):
            with self.subTest(threshold=t), self.assertRaises(ValueError):
                compare_private_rgb8(
                    (1, 1, b"\x00" * 3), (1, 1, b"\x00" * 3),
                    threshold=t)


if __name__ == "__main__":
    unittest.main()
