"""Synthetic PRS compressed cache decoder tests, derived from pinned unpack.c."""
import struct
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from decode_vh_map_prs import (  # noqa: E402
    MAX_COMPRESSED_BYTES, decode_prs_stream, decode_map_prs,
)
from inspect_vh_map_geometry import MAP_11_BYTES, parse_tile  # noqa: E402


def wrap(stream, padding=b""):
    return struct.pack("<I", len(stream)) + stream + padding


class MapPrsDecoderTests(unittest.TestCase):
    def test_literal_bits_followed_by_absolute_cache_copy(self):
        # Bits 0..6: 7 literals. Bit 7: absolute 10-bit cache offset 990.
        stream = b"\x80ABCDEFG" + bytes((0, 990 & 255))
        self.assertEqual(decode_prs_stream(stream), b"ABCDEFGABC")

    def test_short_relative_cache_copy(self):
        # b1=0x81 means distance=1, count=2; both are last byte G.
        self.assertEqual(decode_prs_stream(b"\x80ABCDEFG\x81"),
                         b"ABCDEFGGG")

    def test_literal_run_up_to_71_bytes(self):
        # 8 control bits are set; each 0xc0 op consumes 8 more literals.
        letters = bytes(range(64, 72))
        stream = b"\xff" + (b"\xc0" + letters) * 8
        self.assertEqual(decode_prs_stream(stream), letters * 8)

    def test_zero_control_terminates_stream(self):
        stream = b"\x80ABCDEFG\x81\x00"
        self.assertEqual(decode_map_prs(wrap(stream)), b"ABCDEFGGG")

    def test_initial_cache_zero_and_full_decompressed_map(self):
        # Real map 11 stores 28x12 304-byte tile prefixes.
        # 0xff + eight 0x80 short-backrefs produces 16 zero bytes.
        self.assertEqual(MAP_11_BYTES % 16, 0)
        stream = (b"\xff" + b"\x80" * 8) * (MAP_11_BYTES // 16)
        result = decode_map_prs(wrap(stream), min_output=MAP_11_BYTES,
                                max_output=MAP_11_BYTES)
        self.assertEqual(result, bytes(MAP_11_BYTES))
        self.assertEqual(parse_tile(result, 6, 3)["face_count"], 0)

    def test_detect_truncated_literals(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            decode_prs_stream(b"\x80AB")

    def test_detect_truncated_cache_backref(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            decode_prs_stream(b"\x80ABCDEFG\x00")

    def test_detect_truncated_inline_literal_run(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            decode_prs_stream(b"\xff\xc0Z")

    def test_fail_closed_at_decompressed_output_cap(self):
        with self.assertRaisesRegex(ValueError, "output limit"):
            decode_prs_stream(b"\x80ABCDEFG\x81", max_output=8)

    def test_invalid_header_and_short_file(self):
        for data in (b"", b"\x01\x00\x00\x00", b"\x00"*5,
                     b"\xff\xff\xff\xffX"):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    decode_map_prs(data)

    def test_truncated_payload_and_reject_nonzero_tail(self):
        with self.assertRaisesRegex(ValueError, "truncated"):
            decode_map_prs(struct.pack("<I", 30) + b"\xff")
        with self.assertRaisesRegex(ValueError, "unexpected nonzero"):
            decode_map_prs(wrap(b"\x80ABCDEFG\x81", b"\x01"))
        self.assertEqual(decode_map_prs(wrap(b"\x80ABCDEFG\x81", bytes(32))),
                         b"ABCDEFGGG")

    def test_reject_min_output_not_met(self):
        with self.assertRaisesRegex(ValueError, "fewer bytes"):
            decode_map_prs(wrap(b"\x80ABCDEFG\x81"),
                           min_output=MAP_11_BYTES)

    def test_reject_excessive_input_and_limits(self):
        with self.assertRaisesRegex(ValueError, "invalid"):
            decode_prs_stream(bytes(MAX_COMPRESSED_BYTES + 1))
        for limit in (0, -1):
            with self.assertRaisesRegex(ValueError, "limit"):
                decode_prs_stream(b"\x80ABCDEFG\x81", max_output=limit)


if __name__ == "__main__":
    unittest.main()
