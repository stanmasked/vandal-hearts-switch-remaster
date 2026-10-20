"""Synthetic adversarial screenshot tests for the real field-medic proof.

These are deliberately NOT real NeXium evidence; CI needs a separate
hardware-controller-mapped emulator playback and original PNG captures.
"""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_medic as oracle
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED

BLACK = (0, 0, 0)
HP = (255, 219, 102)
W, H = 1280, 720


def actor(im, x, y, color=None, hp=0):
    px, py = GX + CELL * x, GY + CELL * y
    draw = ImageDraw.Draw(im)
    draw.rectangle((px + 17, py + 17, px + 54, py + 54),
                   fill=color or BLACK)
    draw.rectangle((px + 16, py + 59, px + 55, py + 62), fill=BLACK)
    if hp:
        draw.rectangle((px + 16, py + 59, px + 15 + 8 * hp, py + 62),
                       fill=HP)


def make_fake(root: Path):
    legacy = Image.new("RGB", (W, H), BLACK)
    actor(legacy, 5, 2, ENEMY, 2)
    primary = Image.new("RGB", (W, H), BLACK)
    second = Image.new("RGB", (W, H), BLACK)
    for y in range(4):
        actor(primary, 0, y, HERO, 3)
        actor(primary, 1, y, ENEMY, 2)
        actor(second, 1, y, HERO, 3)
        actor(second, 5, y, ENEMY, 2)
    wounded = second.copy()
    actor(wounded, 1, 0, HERO, 1)
    healed = wounded.copy()
    actor(healed, 1, 0, HERO, 3)
    actor(healed, 1, 1, ACTED, 3)
    files = {
        "legacy": legacy, "primary": primary, "second": second,
        "full_hp_b": second, "wounded": wounded, "healed": healed,
        "reset": second, "primary_return": primary,
        "legacy_return": legacy,
    }
    for name, frame in files.items():
        frame.save(root / (name + ".png"))


class MedicScreenOracle(unittest.TestCase):
    def proof(self, action=None, reason=None, phase=4):
        with tempfile.TemporaryDirectory(prefix="vh-medic-oracle-") as temp:
            root = Path(temp)
            make_fake(root)
            if action:
                action(root)
            if reason:
                with self.assertRaisesRegex(ValueError, reason):
                    oracle.verify(root, phase)
            else:
                oracle.verify(root, phase)

    def change(self, root, name, fn):
        frame = oracle.read(root, name)
        fn(frame)
        frame.save(root / (name + ".png"))

    def test_accept_complete_screen_sequence(self):
        self.proof()

    def test_reject_unbounded_enemy_wait(self):
        self.proof(reason="bounded", phase=9)

    def test_reject_missing_second_scene_actor(self):
        self.proof(lambda r: self.change(
            r, "second", lambda im: actor(im, 1, 3)),
            "missing allied/enemy")

    def test_reject_healthy_heal_mistakenly_spending_action(self):
        self.proof(lambda r: (r / "full_hp_b.png").write_bytes(
            (r / "healed.png").read_bytes()), "full-HP")

    def test_reject_no_natural_hp_damage(self):
        self.proof(lambda r: (r / "wounded.png").write_bytes(
            (r / "second.png").read_bytes()), "did not restore wounded")

    def test_reject_dead_patient(self):
        self.proof(lambda r: self.change(
            r, "wounded", lambda im: actor(im, 1, 0)),
            "did not restore wounded")

    def test_reject_heal_that_did_not_restore_hp(self):
        self.proof(lambda r: (r / "healed.png").write_bytes(
            (r / "wounded.png").read_bytes()), "did not restore wounded")

    def test_reject_heal_over_cap(self):
        self.proof(lambda r: self.change(
            r, "healed", lambda im: actor(im, 1, 0, HERO, 5)),
            "did not restore wounded")

    def test_reject_no_spent_medic_action(self):
        self.proof(lambda r: self.change(
            r, "healed", lambda im: actor(im, 1, 1, HERO, 3)),
            "spend an actual support")

    def test_reject_reset_with_wounded_actor(self):
        self.proof(lambda r: (r / "reset.png").write_bytes(
            (r / "wounded.png").read_bytes()), "Y reset")

    def test_reject_changed_primary_scene(self):
        self.proof(lambda r: (r / "primary_return.png").write_bytes(
            (r / "second.png").read_bytes()), "first 4v4 arena")

    def test_reject_changed_original_map(self):
        self.proof(lambda r: (r / "legacy_return.png").write_bytes(
            (r / "second.png").read_bytes()), "original MAP02")

    def test_reject_wrong_frame_dimensions(self):
        self.proof(lambda r: Image.new("RGB", (320, 180)).save(
            r / "healed.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
