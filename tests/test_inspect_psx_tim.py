"""Standalone binary TIM validation regressions; all fixtures are synthetic."""
from pathlib import Path
import struct
import sys
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_psx_tim import MAX_SECTION_BYTES, parse_tim  # noqa: E402


def section(x, y, width_words, height, words):
    assert len(words) == width_words * height
    data = struct.pack("<" + "H" * len(words), *words)
    return struct.pack("<IHHHH", 12 + len(data), x, y, width_words, height) + data


def indexed_tim(depth=0):
    palette_count = 16 if depth == 0 else 256
    palette = [0, 0x001F, 0x03E0] + [0] * (palette_count - 3)
    pixels = [0x2121] * 4 if depth == 0 else [0x0201] * 4
    return (struct.pack("<II", 0x10, depth | 8) +
            section(0, 42, palette_count, 1, palette) +
            section(384, 0, 2, 2, pixels))


class TimInspectorTests(unittest.TestCase):
    def test_4bpp_headers_and_coordinates(self):
        info = parse_tim(indexed_tim())
        self.assertEqual(info["depth"], "4bpp")
        self.assertEqual(info["flags"], 8)
        self.assertEqual(info["clut"]["rect"], [0, 42, 16, 1])
        self.assertEqual(info["pixels"]["rect"], [384, 0, 2, 2])
        self.assertEqual((info["logical_width"], info["logical_height"]), (8, 2))
        self.assertEqual(info["clut"]["payload_bytes"], 32)
        self.assertEqual(info["pixels"]["payload_bytes"], 8)

    def test_8bpp_palette(self):
        info = parse_tim(indexed_tim(1))
        self.assertEqual(info["depth"], "8bpp")
        self.assertEqual(info["clut"]["rect"], [0, 42, 256, 1])
        self.assertEqual(info["logical_width"], 4)

    def test_15bpp_without_clut(self):
        blob = struct.pack("<II", 0x10, 2) + section(
            448, 0, 2, 2, [0x03FF, 0x7C1F, 0x03FF, 0x7C1F])
        info = parse_tim(blob)
        self.assertEqual(info["depth"], "15bpp")
        self.assertIsNone(info["clut"])
        self.assertEqual(info["logical_width"], 2)

    def test_guest_tim_matches_exact_binary_layout(self):
        guest = (ROOT / "probes/pinned_drawotag_switch_smoke.c").read_text()
        match = re.search(r'unsigned int\s+tim_words\s*\[18\]\s*=\s*'
                          r'\{([^}]+)\}', guest)
        self.assertIsNotNone(match)
        words = [int(x.strip().rstrip("uU"), 0)
                 for x in match.group(1).split(",")]
        self.assertEqual(len(words), 18)
        blob = struct.pack("<18I", *words)
        # Guest fixture includes the same palette with only the first
        # three colors explicitly initialized; zero-filled tail.
        self.assertEqual(blob, indexed_tim())
        self.assertEqual(parse_tim(blob)["pixels"]["payload_offset"], 64)
        for token in (
            "OpenTIM(tim_words);", "ReadTIM(&tim_image)",
            "LoadImage(tim_image.crect, tim_image.caddr);",
            "LoadImage(tim_image.prect, tim_image.paddr);",
        ):
            self.assertIn(token, guest)

    def test_reject_missing_clut(self):
        raw = struct.pack("<II", 0x10, 0) + section(384, 0, 2, 2, [0] * 4)
        with self.assertRaisesRegex(ValueError, "requires CLUT"):
            parse_tim(raw)

    def test_reject_bad_magic(self):
        blob = bytearray(indexed_tim())
        struct.pack_into("<I", blob, 0, 0x11)
        with self.assertRaisesRegex(ValueError, "magic"):
            parse_tim(blob)

    def test_reject_truncated_clut(self):
        with self.assertRaises(ValueError):
            parse_tim(indexed_tim()[:20])

    def test_reject_truncated_pixels(self):
        with self.assertRaisesRegex(ValueError, "truncated image pixels"):
            parse_tim(indexed_tim()[:-2])

    def test_reject_section_size_mismatch(self):
        blob = bytearray(indexed_tim())
        struct.pack_into("<I", blob, 8, 40)
        with self.assertRaises(ValueError):
            parse_tim(blob)

    def test_reject_vram_overrun(self):
        blob = bytearray(indexed_tim())
        struct.pack_into("<H", blob, 8 + 4, 1010)
        with self.assertRaisesRegex(ValueError, "outside PS1 VRAM"):
            parse_tim(blob)

    def test_reject_zero_sized_image(self):
        blob = bytearray(indexed_tim())
        # The image section starts at offset 8 + 44.
        struct.pack_into("<H", blob, 52 + 8, 0)
        with self.assertRaisesRegex(ValueError, "outside PS1 VRAM"):
            parse_tim(blob)

    def test_reject_trailing_bytes(self):
        with self.assertRaisesRegex(ValueError, "unexpected bytes"):
            parse_tim(indexed_tim() + b"\\x00" * 4)

    def test_reject_non_word_aligned_section(self):
        blob = bytearray(indexed_tim())
        struct.pack_into("<I", blob, 8, 43)
        with self.assertRaisesRegex(ValueError, "length"):
            parse_tim(blob)

    def test_reject_unsupported_modes(self):
        for flags in (3, 0x0C, 0x100):
            blob = bytearray(indexed_tim())
            struct.pack_into("<I", blob, 4, flags)
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                parse_tim(blob)

    def test_reject_oversized_section(self):
        blob = bytearray(indexed_tim())
        struct.pack_into("<I", blob, 8, MAX_SECTION_BYTES + 4)
        with self.assertRaisesRegex(ValueError, "length"):
            parse_tim(blob)


if __name__ == "__main__":
    unittest.main()
