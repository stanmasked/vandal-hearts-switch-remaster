#!/usr/bin/env python3
"""Synthetic adversarial PNGs only. A pass here is not a real NeXium pass."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
from run_map02_nexium_guard_boundary import NAMES, verify
from run_map02_nexium_4v4 import GX, GY, CELL


def write_all(folder: Path, frame: Image.Image):
    for name in NAMES:
        frame.save(folder / (name + ".png"))


class GuardTransitionForgeryTests(unittest.TestCase):
    def test_blank_captures_do_not_prove_roster(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_all(folder, Image.new("RGB", (1280, 720), (0, 0, 0)))
            with self.assertRaisesRegex(ValueError, "baseline allies"):
                verify(folder)

    def test_invalid_screen_dimensions_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_all(folder, Image.new("RGB", (640, 480), (0, 0, 0)))
            with self.assertRaisesRegex(ValueError, "unexpected NeXium screenshot"):
                verify(folder)

    def test_static_authored_sprites_cannot_fake_roster_change(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            frame = Image.new("RGB", (1280, 720), (12, 18, 34))
            draw = ImageDraw.Draw(frame)
            for y in (0, 2):
                x0, y0 = GX + CELL + 17, GY + CELL * y + 17
                draw.rectangle((x0, y0, x0 + 37, y0 + 37),
                               fill=(86, 190, 244))
            write_all(folder, frame)
            with self.assertRaisesRegex(ValueError, "1v4 roster failed"):
                verify(folder)


if __name__ == "__main__":
    unittest.main()
