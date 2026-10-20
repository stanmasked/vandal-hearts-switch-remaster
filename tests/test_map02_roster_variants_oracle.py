"""Adversarial synthetic frames for the 4v4 -> 3v3 -> 1v4 screenshot oracle.

No fake screenshot may count as genuine NeXium runtime evidence.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_roster_variants as check
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED

W, H = 1280, 720
BLACK = (0, 0, 0)


def actor(image, x, y, color):
    px, py = GX + CELL*x + 17, GY + CELL*y + 17
    ImageDraw.Draw(image).rectangle((px, py, px + 37, py + 37),
                                   fill=color or BLACK)


def fixtures(root):
    blank = Image.new("RGB", (W, H), BLACK)
    legacy = blank.copy()
    actor(legacy, 5, 2, ENEMY)

    four = blank.copy()
    three = blank.copy()
    one = blank.copy()
    for y in range(4):
        actor(four, 0, y, HERO)
        actor(four, 1, y, ENEMY)
        actor(one, 1, y, ENEMY)
        if y < 3:
            actor(three, 0, y, HERO)
            actor(three, 1, y, ENEMY)
    actor(one, 0, 0, HERO)
    for image, x in ((four, 995), (three, 1005), (one, 1015)):
        ImageDraw.Draw(image).rectangle((x, 184, x + 7, 190),
                                        fill=(255, 219, 102))

    one_attack = one.copy()
    actor(one_attack, 0, 0, ACTED)
    actor(one_attack, 1, 0, None)

    for name, image in {
        "legacy": legacy, "four": four, "three": three,
        "one": one, "one_attack": one_attack, "one_reset": one,
        "four_again": four, "legacy_return": legacy,
    }.items():
        image.save(root / (name + ".png"))


class RosterSelectionOracleTests(unittest.TestCase):
    def case(self, mutate=None, error=None):
        with tempfile.TemporaryDirectory(prefix="vh-roster-oracle-") as td:
            root = Path(td)
            fixtures(root)
            if mutate:
                mutate(root)
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    check.verify(root)
            else:
                check.verify(root)

    def test_accept_exact_valid_cycle(self):
        self.case()

    def test_refuse_missing_fourth_opponent(self):
        def change(root):
            im = check.read(root, "four")
            actor(im, 1, 3, None)
            im.save(root / "four.png")
        self.case(change, "missing row")

    def test_refuse_ghost_slot_in_three_by_three(self):
        def change(root):
            im = check.read(root, "three")
            actor(im, 0, 3, HERO)
            im.save(root / "three.png")
        self.case(change, "padded fourth slots")

    def test_refuse_two_allies_in_one_by_four(self):
        def change(root):
            im = check.read(root, "one")
            actor(im, 0, 1, HERO)
            im.save(root / "one.png")
        self.case(change, "padded allied slots")

    def test_refuse_missing_last_enemy_in_one_by_four(self):
        def change(root):
            im = check.read(root, "one")
            actor(im, 1, 3, None)
            im.save(root / "one.png")
        self.case(change, "enemy 3 missing")

    def test_refuse_missing_melee(self):
        def change(root):
            (root / "one_attack.png").write_bytes((root / "one.png").read_bytes())
        self.case(change, "combat selection")

    def test_refuse_broken_y_reset(self):
        def change(root):
            (root / "one_reset.png").write_bytes((root / "one_attack.png").read_bytes())
        self.case(change, "reset selected 1v4")

    def test_refuse_broken_4v4_roundtrip(self):
        def change(root):
            (root / "four_again.png").write_bytes((root / "three.png").read_bytes())
        self.case(change, "cycle back")

    def test_refuse_broken_legacy_return(self):
        def change(root):
            (root / "legacy_return.png").write_bytes((root / "four.png").read_bytes())
        self.case(change, "legacy MAP 1")

    def test_refuse_same_roster_label(self):
        def change(root):
            im = check.read(root, "three")
            rect = check.ROSTER_LABEL
            four = check.read(root, "four")
            im.paste(four.crop(rect), rect[:2])
            im.save(root / "three.png")
        self.case(change, "labels")

    def test_refuse_wrong_dimensions(self):
        def change(root):
            Image.new("RGB", (320, 180)).save(root / "one.png")
        self.case(change, "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
