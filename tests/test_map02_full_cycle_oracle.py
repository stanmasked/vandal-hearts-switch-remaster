"""Synthetic adversarial oracle for ONE NeXium-process specialist→victory→defeat route.

This does not claim real emulator execution. Images are fabricated only to
prove that the acceptance oracle rejects incorrect state transitions.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_full_cycle as proof
from test_map02_single_session_oracle import create_synthetic_set
from test_map02_guard_oracle import actor
from run_map02_nexium_4v4 import HERO, ENEMY, ACTED

YELLOW = (255, 219, 102)
BLUE = (86, 190, 244)
BLACK = (0, 0, 0)


def status(image, color):
    ImageDraw.Draw(image).rectangle((90, 85, 138, 97), fill=color)


def synthetic_cycle(folder: Path):
    create_synthetic_set(folder)
    initial = proof.read(folder, "primary")
    killed_one = initial.copy()
    actor(killed_one, 1, 0)
    actor(killed_one, 0, 0, ACTED, 3)
    status(killed_one, BLUE)

    victory = initial.copy()
    for y in range(4):
        actor(victory, 1, y)
        actor(victory, 0, y, ACTED, 3)
    status(victory, YELLOW)

    enemy_hit = initial.copy()
    for y in range(4):
        actor(enemy_hit, 0, y, HERO, 1)
    status(enemy_hit, BLUE)

    enemy_won = initial.copy()
    for y in range(4):
        actor(enemy_won, 0, y)
    status(enemy_won, YELLOW)

    for name, frame in {
        "first_kill": killed_one,
        "first_victory": victory,
        "victory_reset": initial,
        "enemy_first": enemy_hit,
        "enemy_defeat": enemy_won,
        "defeat_reset": initial,
    }.items():
        frame.save(folder / (name + ".png"))


class CrossClassVictoryDefeatOracle(unittest.TestCase):
    def scenario(self, corrupt=None, expected=None):
        with tempfile.TemporaryDirectory(prefix="vh-full-cycle-") as name:
            folder = Path(name)
            synthetic_cycle(folder)
            if corrupt:
                corrupt(folder)
            if expected:
                with self.assertRaisesRegex(ValueError, expected):
                    proof.verify(folder)
            else:
                proof.verify(folder)

    def replace(self, folder, target, source):
        (folder / (target + ".png")).write_bytes(
            (folder / (source + ".png")).read_bytes())

    def change(self, folder, target, fn):
        frame = proof.read(folder, target)
        fn(frame)
        frame.save(folder / (target + ".png"))

    def test_accept_complete_fixture(self):
        self.scenario()

    def test_reject_forged_bow_reset_before_victory(self):
        self.scenario(
            lambda p: self.replace(p, "bow_reset", "bow_hit"),
            "reset after bow")

    def test_reject_missing_first_kill(self):
        self.scenario(
            lambda p: self.replace(p, "first_kill", "primary"),
            "first melee kill")

    def test_reject_false_victory_with_surviving_opponent(self):
        self.scenario(
            lambda p: self.replace(p, "first_victory", "first_kill"),
            "complete first-arena victory")

    def test_reject_victory_without_status_change(self):
        def corrupt(p):
            img = proof.read(p, "first_victory")
            status(img, BLUE)
            img.save(p / "first_victory.png")
        self.scenario(corrupt, "win status")

    def test_reject_false_victory_reset(self):
        self.scenario(
            lambda p: self.replace(p, "victory_reset", "first_victory"),
            "Y after victory")

    def test_reject_first_enemy_phase_killing_allies(self):
        self.scenario(
            lambda p: self.replace(p, "enemy_first", "enemy_defeat"),
            "premature defeat")

    def test_reject_first_enemy_phase_without_damage(self):
        self.scenario(
            lambda p: self.replace(p, "enemy_first", "primary"),
            "real first enemy phase")

    def test_reject_second_enemy_phase_survivors(self):
        self.scenario(
            lambda p: self.replace(p, "enemy_defeat", "enemy_first"),
            "did not defeat")

    def test_reject_defeat_without_status(self):
        def corrupt(p):
            img = proof.read(p, "enemy_defeat")
            status(img, BLUE)
            img.save(p / "enemy_defeat.png")
        self.scenario(corrupt, "defeat status")

    def test_reject_defeat_reset_leaking_dead_party(self):
        self.scenario(
            lambda p: self.replace(p, "defeat_reset", "enemy_defeat"),
            "Y after defeat")

    def test_reject_corrupted_original_map_after_full_cycle(self):
        self.scenario(
            lambda p: self.replace(p, "legacy_again", "first_victory"),
            "approved original MAP02")

    def test_reject_missing_guard_before_old_battle(self):
        self.scenario(
            lambda p: self.replace(p, "guard_hit", "pre_guard"),
            "failed to cooperate")

    def test_reject_wrong_full_cycle_screenshot_size(self):
        self.scenario(
            lambda p: Image.new("RGB", (640, 360)).save(
                p / "first_victory.png"),
            "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
