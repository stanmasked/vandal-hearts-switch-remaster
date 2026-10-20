"""Synthetic adversarial tests for the real NeXium two-arena screenshot oracle.

Synthetic images test only the oracle; they cannot be used as real emulator
evidence. The real acceptance job captures NeXium frames independently.
"""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_two_eight_arenas as scene
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED

BLACK = (0, 0, 0)
W, H = 1280, 720


def actor(image, x, y, color=None):
    px, py = GX + CELL * x + 17, GY + CELL * y + 17
    ImageDraw.Draw(image).rectangle((px, py, px + 37, py + 37),
                                   fill=color or BLACK)


def base_scene(allies, enemies, arena_b=False):
    im = Image.new("RGB", (W, H), BLACK)
    ax, ex = (1, 5) if arena_b else (0, 1)
    for y in range(allies):
        actor(im, ax, y, HERO)
    for y in range(enemies):
        actor(im, ex, y, ENEMY)
    if arena_b:
        ImageDraw.Draw(im).rectangle((993, 490, 1040, 495),
                                     fill=(255, 219, 102))
    return im


def make_fake_evidence(root):
    old = Image.new("RGB", (W, H), BLACK)
    actor(old, 5, 2, ENEMY)
    a4 = base_scene(4, 4)
    b4 = base_scene(4, 4, True)
    b3 = base_scene(3, 3, True)
    b1 = base_scene(1, 4, True)
    bmove = b1.copy()
    actor(bmove, 1, 0)
    actor(bmove, 2, 0, ACTED)
    bturn = bmove.copy()
    actor(bturn, 2, 0, HERO)
    actor(bturn, 5, 0)
    actor(bturn, 4, 0, ENEMY)
    a1 = base_scene(1, 4)
    for name, im in {
        "legacy": old, "a_four": a4, "b_four": b4,
        "b_three": b3, "b_one": b1, "b_moved": bmove,
        "b_enemy_turn": bturn, "b_reset": b1,
        "a_one": a1, "a_four_again": a4,
        "legacy_return": old,
    }.items():
        im.save(root / (name + ".png"))


class TwoArenasPixelOracleTests(unittest.TestCase):
    def audit(self, mutation=None, error=None):
        with tempfile.TemporaryDirectory(prefix="vh-second-arena-") as td:
            root = Path(td)
            make_fake_evidence(root)
            if mutation:
                mutation(root)
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    scene.verify(root)
            else:
                scene.verify(root)

    def change_frame(self, root, name, action):
        im = scene.read(root, name)
        action(im)
        im.save(root / (name + ".png"))

    def test_accept_complete_fake_reference(self):
        self.audit()

    def test_refuse_missing_second_arena_ally(self):
        self.audit(lambda r: self.change_frame(
            r, "b_four", lambda im: actor(im, 1, 3)),
            "second arena failed to spawn")

    def test_refuse_padded_fourth_ally_in_three_by_three(self):
        self.audit(lambda r: self.change_frame(
            r, "b_three", lambda im: actor(im, 1, 3, HERO)),
            "padded slots")

    def test_refuse_fake_extra_ally_in_one_by_four(self):
        self.audit(lambda r: self.change_frame(
            r, "b_one", lambda im: actor(im, 1, 1, HERO)),
            "absent/forged allies")

    def test_refuse_missing_1v4_enemy(self):
        self.audit(lambda r: self.change_frame(
            r, "b_one", lambda im: actor(im, 5, 3)),
            "missing foe 3")

    def test_refuse_unperformed_ally_move(self):
        self.audit(lambda r: (r / "b_moved.png").write_bytes(
            (r / "b_one.png").read_bytes()), "legal ally step")

    def test_refuse_missing_ai_pursuit(self):
        self.audit(lambda r: (r / "b_enemy_turn.png").write_bytes(
            (r / "b_moved.png").read_bytes()), "opponent did not pursue")

    def test_refuse_failed_b_reset(self):
        self.audit(lambda r: (r / "b_reset.png").write_bytes(
            (r / "b_moved.png").read_bytes()), "restore second arena")

    def test_refuse_missing_primary_4v4_roundtrip(self):
        self.audit(lambda r: (r / "a_four_again.png").write_bytes(
            (r / "a_one.png").read_bytes()), "original 4v4 arena")

    def test_refuse_changed_legacy_map(self):
        self.audit(lambda r: (r / "legacy_return.png").write_bytes(
            (r / "b_one.png").read_bytes()), "legacy MAP02")

    def test_refuse_forged_hud_identifier(self):
        def tamper(im):
            ImageDraw.Draw(im).rectangle((993, 490, 1040, 495),
                                         fill=BLACK)
        self.audit(lambda r: self.change_frame(r, "b_four", tamper),
                   "HUD identifier")

    def test_refuse_wrong_screen_resolution(self):
        self.audit(lambda r: Image.new("RGB", (320, 180)).save(
            r / "b_three.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
