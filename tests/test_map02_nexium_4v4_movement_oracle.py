"""Adversarial synthetic proof for independent NeXium 4v4 movement route.

Synthetic unit and wall frames are used only to test the auditor; they are
never accepted as evidence of an actual NeXium emulator session.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_4v4_movement as audit

BLACK = (0, 0, 0)
HP = (255, 219, 102)


def unit(im, x, y, color=None, hp=0):
    xx = audit.GX + audit.CELL * x
    yy = audit.GY + audit.CELL * y
    draw = ImageDraw.Draw(im)
    draw.rectangle((xx + 17, yy + 17, xx + 54, yy + 54),
                   fill=color or BLACK)
    draw.rectangle((xx + 16, yy + 59, xx + 55, yy + 62), fill=BLACK)
    if hp:
        draw.rectangle((xx + 16, yy + 59, xx + 15 + hp * 8,
                        yy + 62), fill=HP)


def fixtures(root):
    base = Image.new("RGB", (audit.GX + audit.CELL * 8 + 400, 720), BLACK)
    # Make exact 1280-wide images, matching the emulator framebuffer.
    base = base.crop((0, 0, 1280, 720))
    legacy = base.copy()
    unit(legacy, 1, 2, audit.HERO, 3)
    unit(legacy, 5, 2, audit.ENEMY, 2)
    start = base.copy()
    for y in range(4):
        unit(start, 0, y, audit.HERO, 3)
        unit(start, 1, y, audit.ENEMY, 2)
    invalid = start.copy()  # a rejected illegal action leaves actors unchanged
    moved = start.copy()
    unit(moved, 0, 3)
    unit(moved, 0, 4, audit.ACTED, 3)
    enemy = moved.copy()
    for y in range(3):
        unit(enemy, 0, y, audit.HERO, 1)
    unit(enemy, 0, 4, audit.HERO, 3)  # X resets acted flags
    unit(enemy, 1, 3)
    unit(enemy, 0, 3, audit.ENEMY, 2)
    for name, image in {
        "legacy": legacy,
        "start": start,
        "invalid_move": invalid,
        "moved": moved,
        "enemy_turn": enemy,
        "reset": start,
        "legacy_return": legacy,
    }.items():
        image.save(root / (name + ".png"))


class EightSlotMoveOracleTests(unittest.TestCase):
    def case(self, mutate=None, expected=None):
        with tempfile.TemporaryDirectory(prefix="vh-map02-move-audit-") as path:
            root = Path(path)
            fixtures(root)
            if mutate:
                mutate(root)
            if expected:
                with self.assertRaisesRegex(ValueError, expected):
                    audit.verify(root)
            else:
                audit.verify(root)

    def test_accept_valid_movement_and_enemy_path(self):
        self.case()

    def test_refuse_hidden_fourth_ally(self):
        def mutate(root):
            im = audit.read(root, "start")
            unit(im, 0, 3)
            im.save(root / "start.png")
        self.case(mutate, "initial ally 3")

    def test_refuse_wall_teleport(self):
        def mutate(root):
            im = audit.read(root, "invalid_move")
            unit(im, 0, 3)
            unit(im, 3, 2, audit.ACTED, 3)
            im.save(root / "invalid_move.png")
        self.case(mutate, "blocked terrain")

    def test_refuse_missing_legal_move(self):
        def mutate(root):
            (root / "moved.png").write_bytes((root / "start.png").read_bytes())
        self.case(mutate, "legal movement")

    def test_refuse_enemy_that_did_not_pursue(self):
        def mutate(root):
            (root / "enemy_turn.png").write_bytes((root / "moved.png").read_bytes())
        self.case(mutate, "enemy movement")

    def test_refuse_attacker_that_failed_to_deal_damage(self):
        def mutate(root):
            im = audit.read(root, "enemy_turn")
            unit(im, 0, 0, audit.HERO, 3)
            im.save(root / "enemy_turn.png")
        self.case(mutate, "lower HP")

    def test_refuse_enemy_phase_that_did_not_reset_actor(self):
        def mutate(root):
            im = audit.read(root, "enemy_turn")
            unit(im, 0, 4, audit.ACTED, 3)
            im.save(root / "enemy_turn.png")
        self.case(mutate, "enemy movement")

    def test_refuse_invalid_reset(self):
        def mutate(root):
            (root / "reset.png").write_bytes((root / "enemy_turn.png").read_bytes())
        self.case(mutate, "reset")

    def test_refuse_wrong_legacy_map(self):
        def mutate(root):
            (root / "legacy_return.png").write_bytes((root / "start.png").read_bytes())
        self.case(mutate, "restore MAP 1")

    def test_refuse_wrong_resolution(self):
        def mutate(root):
            Image.new("RGB", (320, 180)).save(root / "moved.png")
        self.case(mutate, "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
