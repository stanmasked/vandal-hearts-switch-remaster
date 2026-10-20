"""Synthetic adversarial guard screenshot tests; these are NOT NeXium proofs."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_guard as oracle
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED

BLACK = (0, 0, 0)
YELLOW = (255, 219, 102)
W, H = 1280, 720


def actor(im, x, y, color=None, hp=0):
    px, py = GX + CELL*x, GY + CELL*y
    draw = ImageDraw.Draw(im)
    draw.rectangle((px+17, py+17, px+54, py+54), fill=color or BLACK)
    draw.rectangle((px+16, py+59, px+55, py+62), fill=BLACK)
    if hp:
        draw.rectangle((px+16, py+59, px+15+8*hp, py+62), fill=YELLOW)


def fixture(folder):
    legacy = Image.new("RGB", (W, H), BLACK)
    actor(legacy, 5, 2, ENEMY, 2)
    primary = Image.new("RGB", (W, H), BLACK)
    second = Image.new("RGB", (W, H), BLACK)
    for y in range(4):
        actor(primary, 0, y, HERO, 3)
        actor(primary, 1, y, ENEMY, 2)
        actor(second, 1, y, HERO, 3)
        actor(second, 5, y, ENEMY, 2)
    base = second.copy()
    unguarded = base.copy()
    actor(unguarded, 1, 0, HERO, 1)
    armed = base.copy()
    actor(armed, 1, 2, ACTED, 3)
    guarded = base.copy()
    actor(guarded, 1, 0, HERO, 2)
    healed = guarded.copy()
    actor(healed, 1, 0, HERO, 3)
    actor(healed, 1, 1, ACTED, 3)
    data = {
        "legacy": legacy, "primary": primary, "second": second,
        "after_three": base, "unguarded": unguarded,
        "reset_baseline": second, "guard_ready": base,
        "guard_armed": armed, "guarded": guarded,
        "healed": healed, "final_reset": second,
        "primary_return": primary, "legacy_return": legacy,
    }
    for name, image in data.items():
        image.save(folder / (name + ".png"))


class GuardOracleTests(unittest.TestCase):
    def case(self, mutation=None, failure=None):
        with tempfile.TemporaryDirectory(prefix="vh-guard-oracle-") as temp:
            root = Path(temp)
            fixture(root)
            if mutation: mutation(root)
            if failure:
                with self.assertRaisesRegex(ValueError, failure):
                    oracle.verify(root)
            else:
                oracle.verify(root)

    def replace(self, root, dest, src):
        (root / (dest + ".png")).write_bytes(
            (root / (src + ".png")).read_bytes())

    def change(self, root, frame, fn):
        im = oracle.read(root, frame)
        fn(im)
        im.save(root / (frame + ".png"))

    def test_accept_coherent_reference(self):
        self.case()

    def test_refuse_missing_initial_team(self):
        self.case(lambda r: self.change(
            r, "second", lambda im: actor(im, 1, 3)),
            "initial team missing")

    def test_refuse_wrong_baseline_hp(self):
        self.case(lambda r: self.change(
            r, "after_three", lambda im: actor(im, 1, 0, HERO, 2)),
            "too early")

    def test_refuse_missing_unguarded_damage(self):
        self.case(lambda r: self.replace(r, "unguarded", "second"),
                  "failed to prevent part")

    def test_refuse_unchanged_guard_damage(self):
        self.case(lambda r: self.replace(r, "guarded", "unguarded"),
                  "failed to prevent part")

    def test_refuse_invincible_guard(self):
        self.case(lambda r: self.replace(r, "guarded", "second"),
                  "failed to prevent part")

    def test_refuse_guard_that_did_not_spend_action(self):
        self.case(lambda r: self.replace(r, "guard_armed", "second"),
                  "did not spend")

    def test_refuse_guard_still_acted_after_enemy_phase(self):
        self.case(lambda r: self.change(
            r, "guarded", lambda im: actor(im, 1, 2, ACTED, 3)),
            "did not reset action")

    def test_refuse_no_medic_heal(self):
        self.case(lambda r: self.replace(r, "healed", "guarded"),
                  "medic follow-up")

    def test_refuse_medic_action_not_spent(self):
        self.case(lambda r: self.change(
            r, "healed", lambda im: actor(im, 1, 1, HERO, 3)),
            "medic did not spend")

    def test_refuse_nondeterministic_replay(self):
        self.case(lambda r: self.replace(r, "guard_ready", "unguarded"),
                  "nondeterministic")

    def test_refuse_bad_second_reset(self):
        self.case(lambda r: self.replace(r, "final_reset", "unguarded"),
                  "final Y reset")

    def test_refuse_bad_primary_map(self):
        self.case(lambda r: self.replace(r, "primary_return", "second"),
                  "first original expanded")

    def test_refuse_bad_legacy_map(self):
        self.case(lambda r: self.replace(r, "legacy_return", "guarded"),
                  "original legacy")

    def test_refuse_invalid_frame_dimensions(self):
        self.case(lambda r: Image.new("RGB", (320, 180)).save(
            r / "unguarded.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
