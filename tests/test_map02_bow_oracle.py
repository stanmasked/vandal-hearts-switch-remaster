"""Adversarial screenshot oracle: optional B-button bow action in scene B.

Frames here are synthetic and do NOT substitute real NeXium screenshots.
"""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_bow as oracle
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED

W, H = 1280, 720
BLACK = (0, 0, 0)


def actor(im, x, y, color=None):
    px, py = GX + CELL*x + 17, GY + CELL*y + 17
    ImageDraw.Draw(im).rectangle((px, py, px + 37, py + 37),
                                 fill=color or BLACK)


def frame(allies, enemies, ax, ex):
    im = Image.new("RGB", (W, H), BLACK)
    for y in range(allies):
        actor(im, ax, y, HERO)
    for y in range(enemies):
        actor(im, ex, y, ENEMY)
    return im


def make_frames(folder):
    legacy = Image.new("RGB", (W, H), BLACK)
    actor(legacy, 5, 2, ENEMY)
    first = frame(4, 4, 0, 1)
    second = frame(4, 4, 1, 5)
    invalid = second.copy()
    # Draw selected archer white square, matching native renderer.
    px, py = GX + CELL, GY
    ImageDraw.Draw(invalid).rectangle(
        (px + 11, py + 11, px + 60, py + 60),
        outline=(255, 255, 255), width=1,
    )
    ready = second.copy()
    actor(ready, 1, 0, None)
    actor(ready, 2, 0, HERO)
    actor(ready, 5, 0, None)
    actor(ready, 4, 0, ENEMY)
    shot = ready.copy()
    actor(shot, 2, 0, ACTED)
    actor(shot, 4, 0, None)
    for name, im in {
        "legacy": legacy, "primary": first, "second": second,
        "invalid_bow": invalid, "enemy_approach": ready,
        "shot": shot, "reset": second,
        "primary_again": first, "legacy_again": legacy,
    }.items():
        im.save(folder / (name + ".png"))


class BowOracle(unittest.TestCase):
    def execute(self, modify=None, reason=None):
        with tempfile.TemporaryDirectory(prefix="vh-nexium-bow-") as tmp:
            folder = Path(tmp)
            make_frames(folder)
            if modify:
                modify(folder)
            if reason:
                with self.assertRaisesRegex(ValueError, reason):
                    oracle.verify(folder)
            else:
                oracle.verify(folder)

    def patch(self, root, name, fn):
        im = oracle.read(root, name)
        fn(im)
        im.save(root / (name + ".png"))

    def test_accept_coherent_reference(self):
        self.execute()

    def test_refuse_missing_second_arena_unit(self):
        self.execute(lambda r: self.patch(
            r, "second", lambda im: actor(im, 5, 3)),
            "spawn missing")

    def test_refuse_invalid_range_shot_killing_target(self):
        self.execute(lambda r: self.patch(
            r, "invalid_bow", lambda im: actor(im, 5, 0)),
            "out-of-range B fire")

    def test_refuse_invalid_shot_canceling_selection(self):
        self.execute(lambda r: (r / "invalid_bow.png").write_bytes(
            (r / "second.png").read_bytes()),
            "canceled selected archer")

    def test_refuse_enemy_not_approaching_range(self):
        self.execute(lambda r: (r / "enemy_approach.png").write_bytes(
            (r / "second.png").read_bytes()),
            "enemy never approached")

    def test_refuse_bow_did_not_kill_target(self):
        self.execute(lambda r: (r / "shot.png").write_bytes(
            (r / "enemy_approach.png").read_bytes()),
            "ranged B fire")

    def test_refuse_shot_with_no_spent_action(self):
        self.execute(lambda r: self.patch(
            r, "shot", lambda im: actor(im, 2, 0, HERO)),
            "ranged B fire")

    def test_refuse_overpowered_bow_killing_all(self):
        def change(root):
            self.patch(root, "shot", lambda im: [
                actor(im, 5, y) for y in range(1, 4)
            ])
        self.execute(change, "entire enemy team")

    def test_refuse_failed_scene_reset(self):
        self.execute(lambda r: (r / "reset.png").write_bytes(
            (r / "shot.png").read_bytes()), "Y reset")

    def test_refuse_changed_primary_scene(self):
        self.execute(lambda r: (r / "primary_again.png").write_bytes(
            (r / "second.png").read_bytes()), "primary 4v4")

    def test_refuse_changed_legacy_map(self):
        self.execute(lambda r: (r / "legacy_again.png").write_bytes(
            (r / "shot.png").read_bytes()), "legacy MAP02")

    def test_refuse_wrong_dimensions(self):
        self.execute(lambda r: Image.new("RGB", (320, 180)).save(
            r / "enemy_approach.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
