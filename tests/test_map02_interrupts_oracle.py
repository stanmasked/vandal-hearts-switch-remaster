"""Synthetic positive and adversarial PNG fixtures for guard interruption.

The fixture images are deliberately NOT NeXium screenshots. Only the
separate genuine NeXium job can prove runtime gameplay.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_interrupts as proof
from test_map02_single_session_oracle import create_synthetic_set, tag, READY, ARMED, BLOCKED
from test_map02_guard_oracle import actor
from run_map02_nexium_4v4 import HERO, ACTED

UNAVAILABLE = (190, 65, 105)


def fixtures(folder: Path):
    create_synthetic_set(folder)
    initial = proof.read(folder, "second")
    old = proof.read(folder, "legacy")
    primary = proof.read(folder, "primary")
    armed = initial.copy()
    actor(armed, 1, 2, ACTED, 3)
    tag(armed, ARMED)

    three = initial.copy()
    actor(three, 1, 3)
    actor(three, 5, 3)
    one = initial.copy()
    for y in range(1, 4):
        actor(one, 1, y)
    tag(one, UNAVAILABLE)

    blocked = initial.copy()
    actor(blocked, 1, 0, HERO, 2)
    tag(blocked, BLOCKED)
    images = {
        "legacy": old, "primary": primary, "second": initial,
        "armed_before_scene": armed, "primary_after_scene": primary,
        "second_after_scene": initial, "armed_before_roster": armed,
        "roster_three": three, "roster_one": one,
        "second_after_roster": initial, "armed_before_y": armed,
        "after_y": initial, "pre_hit": initial,
        "armed_before_hit": armed, "blocked": blocked,
        "legacy_after_block": old, "primary_reentry": primary,
        "second_reentry": initial, "legacy_after_minus": old,
        "primary_after_minus": primary, "second_after_minus": initial,
        "final_legacy": old,
    }
    for name, image in images.items():
        image.save(folder / (name + ".png"))


class InterruptFrameOracle(unittest.TestCase):
    def case(self, mutation=None, message=None):
        with tempfile.TemporaryDirectory(prefix="vh-map02-interrupts-") as name:
            folder = Path(name)
            fixtures(folder)
            if mutation:
                mutation(folder)
            if message:
                with self.assertRaisesRegex(ValueError, message):
                    proof.verify(folder)
            else:
                proof.verify(folder)

    @staticmethod
    def replace(folder: Path, dest: str, source: str):
        (folder / (dest + ".png")).write_bytes(
            (folder / (source + ".png")).read_bytes())

    @staticmethod
    def altered(folder: Path, label: str, method):
        image = proof.read(folder, label)
        method(image)
        image.save(folder / (label + ".png"))

    def test_coherent_synthetic_fixture(self):
        self.case()

    def test_reject_missing_initial_foe(self):
        from test_map02_guard_oracle import actor
        self.case(lambda p: self.altered(
            p, "second", lambda i: actor(i, 5, 3)), "incomplete")

    def test_reject_guard_that_was_not_armed(self):
        self.case(lambda p: self.replace(
            p, "armed_before_scene", "second"), "not armed")

    def test_reject_guard_not_cleared_by_scene_change(self):
        self.case(lambda p: self.replace(
            p, "second_after_scene", "armed_before_scene"), "not pristine")

    def test_reject_guard_not_cleared_by_roster_change(self):
        self.case(lambda p: self.replace(
            p, "second_after_roster", "armed_before_roster"), "not pristine")

    def test_reject_guard_not_cleared_by_y_restart(self):
        self.case(lambda p: self.replace(
            p, "after_y", "armed_before_y"), "not pristine")

    def test_reject_phantom_fourth_ally_in_three_by_three(self):
        self.case(lambda p: self.replace(
            p, "roster_three", "second"), "phantom fourth")

    def test_reject_phantom_ally_in_one_by_four(self):
        self.case(lambda p: self.replace(
            p, "roster_one", "second"), "inactive ally")

    def test_reject_wrong_unavailable_guard_label(self):
        self.case(lambda p: self.altered(
            p, "roster_one", lambda i: tag(i, READY)),
            "unavailable guard")

    def test_reject_missing_real_enemy_damage(self):
        self.case(lambda p: self.replace(
            p, "blocked", "second"), "no actual guarded")

    def test_reject_missing_guard_blocked_transition(self):
        self.case(lambda p: self.altered(
            p, "blocked", lambda i: tag(i, ARMED)), "never changed")

    def test_reject_hurt_ally_after_mode_reentry(self):
        self.case(lambda p: self.replace(
            p, "second_reentry", "blocked"), "not pristine")

    def test_reject_changed_original_after_guarded_hit(self):
        self.case(lambda p: self.replace(
            p, "legacy_after_block", "second"), "approved legacy")

    def test_reject_changed_scene_a_after_return(self):
        self.case(lambda p: self.replace(
            p, "primary_reentry", "second"), "scene A inherited")

    def test_reject_missing_minus_reset(self):
        self.case(lambda p: self.replace(
            p, "second_after_minus", "armed_before_scene"), "not pristine")

    def test_reject_changed_final_legacy_scene(self):
        self.case(lambda p: self.replace(
            p, "final_legacy", "second"), "approved legacy")

    def test_reject_invalid_capture_dimensions(self):
        self.case(lambda p: Image.new("RGB", (320, 180)).save(
            p / "blocked.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
