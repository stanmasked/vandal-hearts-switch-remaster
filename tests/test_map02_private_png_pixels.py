"""No-retail PNG reconstruction regression tests for the private MAP02 reviewer."""
import struct
import unittest
import zlib

from tools.map02_private_png_pixels import private_normalized_pixel_sha256

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(kind, payload):
    crc = zlib.crc32(kind + payload) & 0xffffffff
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _paeth(left, upper, upper_left):
    pred = left + upper - upper_left
    diffs = (abs(pred - left), abs(pred - upper), abs(pred - upper_left))
    if diffs[0] <= diffs[1] and diffs[0] <= diffs[2]:
        return left
    if diffs[1] <= diffs[2]:
        return upper
    return upper_left


def invented_png(*, rgba=False, filt=0, level=6, text=None, change=False,
                 opaque_rgb=False, transparency=False, gamma=False,
                 color_profile=False):
    channels = 4 if rgba else 3
    width, height = 2, 2
    raw_rows = [
        bytes(range(21, 21 + channels * width)),
        bytes(range(71, 71 + channels * width)),
    ]
    if opaque_rgb and rgba:
        raw_rows = [
            b"".join(
                bytes(range(base + x * 3, base + x * 3 + 3)) + bytes([255])
                for x in range(width)
            ) for base in (21, 71)
        ]
    if change:
        raw_rows[1] = raw_rows[1][:-1] + bytes([raw_rows[1][-1] ^ 1])
    previous = bytes(channels * width)
    filtered_rows = []
    for row in raw_rows:
        out = bytearray()
        for index, pixel in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filt == 0:
                prediction = 0
            elif filt == 1:
                prediction = left
            elif filt == 2:
                prediction = up
            elif filt == 3:
                prediction = (left + up) // 2
            elif filt == 4:
                prediction = _paeth(left, up, up_left)
            else:
                raise AssertionError("synthetic filter unsupported")
            out.append((pixel - prediction) & 0xff)
        filtered_rows.append(bytes([filt]) + bytes(out))
        previous = row
    header = struct.pack(">IIBBBBB", width, height, 8, 6 if rgba else 2,
                         0, 0, 0)
    ancillary = _chunk(b"tEXt", b"Note\x00fictional") if text else b""
    if transparency:
        if rgba:
            raise ValueError("tRNS test fixture is for RGB")
        ancillary += _chunk(b"tRNS", struct.pack(">HHH", 21, 22, 23))
    if gamma:
        ancillary += _chunk(b"gAMA", struct.pack(">I", 45455))
    if color_profile:
        ancillary += _chunk(b"sRGB", b"\x00")
    return (PNG_SIG + _chunk(b"IHDR", header) + ancillary
            + _chunk(b"IDAT", zlib.compress(b"".join(filtered_rows), level))
            + _chunk(b"IEND", b""))


class NormalizedPrivatePixelsTests(unittest.TestCase):
    def test_png_filters_zero_through_four_reconstruct_same_rgb(self):
        original = private_normalized_pixel_sha256(invented_png(filt=0))
        self.assertEqual(len(original), 32)
        for filter_type in (1, 2, 3, 4):
            with self.subTest(filter=filter_type):
                observed = private_normalized_pixel_sha256(
                    invented_png(filt=filter_type, level=9))
                self.assertEqual(original, observed)

    def test_recompression_and_private_metadata_are_ignored(self):
        a = invented_png(level=0)
        b = invented_png(level=9, text="metadata")
        self.assertNotEqual(a, b)
        self.assertEqual(private_normalized_pixel_sha256(a),
                         private_normalized_pixel_sha256(b))

    def test_rgb_vs_rgba_not_conflated(self):
        self.assertNotEqual(private_normalized_pixel_sha256(invented_png()),
                            private_normalized_pixel_sha256(invented_png(rgba=True)))

    def test_opaque_rgba_matches_same_rgb_samples(self):
        rgb = invented_png(filt=1, level=1)
        rgba = invented_png(rgba=True, opaque_rgb=True, filt=4, level=9,
                            text="harmless")
        self.assertNotEqual(rgb, rgba)
        self.assertEqual(private_normalized_pixel_sha256(rgb),
                         private_normalized_pixel_sha256(rgba))

    def test_nonopaque_rgba_does_not_match_rgb(self):
        rgb = invented_png(filt=0)
        rgba = invented_png(rgba=True, opaque_rgb=True, filt=0, change=True)
        self.assertNotEqual(private_normalized_pixel_sha256(rgb),
                            private_normalized_pixel_sha256(rgba))

    def test_rgb_transparency_metadata_is_not_assumed_opaque(self):
        original = private_normalized_pixel_sha256(invented_png())
        transparency = invented_png(transparency=True)
        self.assertIsNotNone(original)
        self.assertIsNone(private_normalized_pixel_sha256(transparency))

    def test_gamma_and_color_profile_require_manual_review(self):
        for extra in ({"gamma": True}, {"color_profile": True}):
            with self.subTest(extra=extra):
                self.assertIsNone(private_normalized_pixel_sha256(
                    invented_png(**extra)))
        self.assertIsNotNone(private_normalized_pixel_sha256(
            invented_png(text="innocuous textual comment")))

    def test_rgba_different_filters_decode_equally(self):
        a = private_normalized_pixel_sha256(invented_png(rgba=True, filt=0))
        b = private_normalized_pixel_sha256(invented_png(rgba=True, filt=4))
        self.assertEqual(a, b)

    def test_actual_pixel_changes_are_detected(self):
        a = private_normalized_pixel_sha256(invented_png(filt=1))
        b = private_normalized_pixel_sha256(invented_png(filt=4, change=True))
        self.assertNotEqual(a, b)

    def test_grayscale_is_explicitly_unsupported_not_false_mismatch(self):
        header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
        image = (PNG_SIG + _chunk(b"IHDR", header)
                 + _chunk(b"IDAT", zlib.compress(b"\x00\x20"))
                 + _chunk(b"IEND", b""))
        self.assertIsNone(private_normalized_pixel_sha256(image))

    def test_invalid_png_crc_fails_closed(self):
        image = bytearray(invented_png())
        image[-8] ^= 0x01
        with self.assertRaises(ValueError):
            private_normalized_pixel_sha256(bytes(image))


if __name__ == "__main__":
    unittest.main()
