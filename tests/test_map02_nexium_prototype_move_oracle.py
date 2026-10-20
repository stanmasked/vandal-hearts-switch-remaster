#!/usr/bin/env python3
"""Adversarial synthetic screenshots. These tests are NOT emulator evidence."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
from tests.run_map02_nexium_prototype_move import verify, GX, GY, CELL

NAMES = ("initial", "selected", "hover", "rejected", "moved",
         "reselected", "canceled", "returned")


def frames(folder: Path, image: Image.Image) -> None:
    for name in NAMES:
        image.save(folder / (name + ".png"))


class FakeFrameRejection(unittest.TestCase):
    def test_blank_screens_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            frames(folder, Image.new("RGB", (1280, 720), (0, 0, 0)))
            with self.assertRaisesRegex(ValueError, "blue ally"):
                verify(folder)

    def test_wrong_resolution_fails_before_pixel_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            frames(folder, Image.new("RGB", (640, 480), (0, 0, 0)))
            with self.assertRaisesRegex(ValueError, "dimensions"):
                verify(folder)

    def test_static_forged_start_frame_cannot_claim_a_real_move(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            im = Image.new("RGB", (1280, 720), (12, 18, 34))
            d = ImageDraw.Draw(im)
            hx, hy = GX + CELL * 1, GY + CELL * 2
            ex, ey = GX + CELL * 6, GY + CELL * 3
            d.rectangle((hx + 18, hy + 18, hx + 53, hy + 53),
                        fill=(86, 190, 244))
            d.rectangle((ex + 17, ey + 17, ex + 54, ey + 54),
                        fill=(235, 89, 98))
            d.rectangle((ex + 25, ey + 25, ex + 46, ey + 46),
                        fill=(12, 18, 34))
            # A static hand-drawn frame must not be mistaken for eight
            # independent, mapped-controller NeXium capture states.
            d.rectangle((hx + 4, hy + 4, hx + 67, hy + 7),
                        fill=(255, 219, 102))
            d.rectangle((hx + 4, hy + 64, hx + 67, hy + 67),
                        fill=(255, 219, 102))
            d.rectangle((hx + 4, hy + 4, hx + 7, hy + 67),
                        fill=(255, 219, 102))
            d.rectangle((hx + 64, hy + 4, hx + 67, hy + 67),
                        fill=(255, 219, 102))
            frames(folder, im)
            with self.assertRaisesRegex(ValueError, "visibly select"):
                verify(folder)


if __name__ == "__main__":
    unittest.main()
