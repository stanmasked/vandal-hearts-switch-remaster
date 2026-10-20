"""Adversarial PNG verifier for the one-process NeXium battle sequence.

These PNG fixtures are synthetic, intentionally never passed off as
actual emulator evidence. The dedicated CI job runs an independent genuine
NeXium instance and captures all named screenshots from that one process.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_single_session as proof
from run_map02_nexium_4v4 import GX, GY, CELL, HERO, ENEMY, ACTED
from test_map02_guard_oracle import actor, fixture

BLACK = (0, 0, 0)
READY = (105, 126, 151)
ARMED = (255, 219, 102)
BLOCKED = (86, 190, 244)
TAG = (987, 568, 1085, 576)
SELECTED = (224, 234, 246)


def tag(frame: Image.Image, color):
    ImageDraw.Draw(frame).rectangle(TAG, fill=color)


def create_synthetic_set(folder: Path):
    fixture(folder)
    legacy = proof.read(folder, "legacy")
    primary = proof.read(folder, "primary")
    second = proof.read(folder, "second")
    tag(second, READY)

    invalid = second.copy()
    px, py = GX + CELL, GY
    ImageDraw.Draw(invalid).rectangle(
        (px + 11, py + 11, px + 60, py + 60),
        outline=SELECTED, width=1)

    ready = second.copy()
    actor(ready, 1, 0)
    actor(ready, 2, 0, HERO, 3)
    actor(ready, 5, 0)
    actor(ready, 4, 0, ENEMY, 2)
    shot = ready.copy()
    actor(shot, 2, 0, ACTED, 3)
    actor(shot, 4, 0)

    guard_armed = second.copy()
    tag(guard_armed, ARMED)
    actor(guard_armed, 1, 2, ACTED, 3)
    guarded = second.copy()
    tag(guarded, BLOCKED)
    actor(guarded, 1, 0, HERO, 2)
    healed = guarded.copy()
    actor(healed, 1, 0, HERO, 3)
    actor(healed, 1, 1, ACTED, 3)

    three = second.copy()
    actor(three, 1, 3)
    actor(three, 5, 3)
    one = second.copy()
    for y in range(1, 4):
        actor(one, 1, y)

    frames = {
        "legacy": legacy, "primary": primary, "second": second,
        "bow_rejected": invalid, "bow_ready": ready, "bow_hit": shot,
        "bow_reset": second, "pre_guard": second,
        "guard_armed": guard_armed, "guard_hit": guarded,
        "medic_healed": healed, "combo_reset": second,
        "roster_three": three, "roster_one": one,
        "roster_four_again": second, "primary_again": primary,
        "legacy_again": legacy,
    }
    for label, image in frames.items():
        image.save(folder / (label + ".png"))


class SingleSessionImageOracleTests(unittest.TestCase):
    def check(self, modify=None, expected=None):
        with tempfile.TemporaryDirectory(prefix="vh-map02-combo-") as td:
            root = Path(td)
            create_synthetic_set(root)
            if modify:
                modify(root)
            if expected:
                with self.assertRaisesRegex(ValueError, expected):
                    proof.verify(root)
            else:
                proof.verify(root)

    def replace(self, root, dest, src):
        (root / (dest + ".png")).write_bytes(
            (root / (src + ".png")).read_bytes())

    def change(self, root, label, mutate):
        image = proof.read(root, label)
        mutate(image)
        image.save(root / (label + ".png"))

    def test_valid_synthetic_reference(self):
        self.check()

    def test_reject_missing_initial_enemy(self):
        self.check(lambda r: self.change(
            r, "second", lambda im: actor(im, 5, 3)),
            "spawn missing")

    def test_reject_invalid_shot_that_cancelled(self):
        self.check(lambda r: self.replace(r, "bow_rejected", "second"),
                   "cancelled archer")

    def test_reject_missing_actual_bow_pursuit(self):
        self.check(lambda r: self.replace(r, "bow_ready", "second"),
                   "advance and enemy pursuit")

    def test_reject_bow_shot_that_misses(self):
        self.check(lambda r: self.replace(r, "bow_hit", "bow_ready"),
                   "arrow did not defeat")

    def test_reject_bow_reset_stale(self):
        self.check(lambda r: self.replace(r, "bow_reset", "bow_hit"),
                   "reset after bow")

    def test_reject_guard_no_visual_arming(self):
        self.check(lambda r: self.replace(r, "guard_armed", "pre_guard"),
                   "visible states")

    def test_reject_no_guarded_reduction(self):
        self.check(lambda r: self.replace(r, "guard_hit", "pre_guard"),
                   "failed to cooperate")

    def test_reject_fake_medic_healing(self):
        self.check(lambda r: self.replace(r, "medic_healed", "guard_hit"),
                   "failed to cooperate")

    def test_reject_missing_medic_spent_action(self):
        self.check(lambda r: self.change(
            r, "medic_healed", lambda im: actor(im, 1, 1, HERO, 3)),
            "medic did not spend")

    def test_reject_wrong_3v3_padding(self):
        self.check(lambda r: self.replace(r, "roster_three", "second"),
                   "padded fourth slot")

    def test_reject_wrong_1v4_padding(self):
        self.check(lambda r: self.replace(r, "roster_one", "second"),
                   "retained absent ally")

    def test_reject_combined_reset_state(self):
        self.check(lambda r: self.replace(r, "combo_reset", "guard_hit"),
                   "guard and medic leaked")

    def test_reject_first_arena_contamination(self):
        self.check(lambda r: self.replace(r, "primary_again", "second"),
                   "initial expanded arena changed")

    def test_reject_legacy_contamination(self):
        self.check(lambda r: self.replace(r, "legacy_again", "second"),
                   "approved original MAP02 changed")

    def test_reject_wrong_neXium_capture_dimensions(self):
        self.check(lambda r: Image.new("RGB", (320, 180)).save(
            r / "roster_one.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
