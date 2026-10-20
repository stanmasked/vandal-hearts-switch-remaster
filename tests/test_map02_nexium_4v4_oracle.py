"""Adversarial synthetic NeXium images audit the optional 4v4 pixel oracle.

These tests never substitute for real NeXium evidence; they ensure fake or
incomplete captures cannot produce a successful result.
"""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_4v4 as oracle


BACKGROUND = (0, 0, 0)
HP = (255, 219, 102)


def rect(x, y):
    left = oracle.GX + oracle.CELL * x + 17
    top = oracle.GY + oracle.CELL * y + 17
    return (left, top, left + 37, top + 37)


def health_bar(x, y, hp):
    left = oracle.GX + oracle.CELL * x + 16
    top = oracle.GY + oracle.CELL * y + 59
    return (left, top, left + 8 * hp - 1, top + 3)


def avatar(image, x, y, color=None, hp=None):
    draw = ImageDraw.Draw(image)
    draw.rectangle(rect(x, y), fill=color or BACKGROUND)
    # Fake frames use black as the panel; erase the whole HP region before
    # painting a shorter health bar so stale pixels cannot falsely pass.
    left = oracle.GX + oracle.CELL * x + 16
    top = oracle.GY + oracle.CELL * y + 59
    draw.rectangle((left, top, left + 39, top + 3), fill=BACKGROUND)
    if hp:
        draw.rectangle(health_bar(x, y, hp), fill=HP)


def make_images(folder):
    blank = Image.new("RGB", (oracle.WIDTH, oracle.HEIGHT), BACKGROUND)
    old = blank.copy()
    avatar(old, 1, 2, oracle.HERO, hp=3)
    avatar(old, 5, 2, oracle.ENEMY, hp=2)

    initial = blank.copy()
    for y in range(4):
        avatar(initial, 0, y, oracle.HERO, hp=3)
        avatar(initial, 1, y, oracle.ENEMY, hp=2)

    partial = initial.copy()
    avatar(partial, 0, 0, oracle.ACTED, hp=3)
    avatar(partial, 1, 0)

    win = partial.copy()
    for y in (1, 2, 3):
        avatar(win, 0, y, oracle.ACTED, hp=3)
        avatar(win, 1, y)

    # Add a realistic status message area transition that the oracle
    # requires to distinguish a completed victory from an action.
    ImageDraw.Draw(win).rectangle((70, 90, 240, 96), fill=(240, 240, 240))

    first_turn = initial.copy()
    for y in range(4):
        avatar(first_turn, 0, y, oracle.HERO, hp=1)

    loss = first_turn.copy()
    for y in range(4):
        avatar(loss, 0, y)
    ImageDraw.Draw(loss).rectangle((70, 90, 240, 96), fill=(240, 240, 240))

    data = {
        "legacy": old, "four_start": initial,
        "first_kill": partial, "four_victory": win,
        "four_reset": initial, "enemy_turn_1": first_turn,
        "four_defeat": loss, "defeat_reset": initial,
        "legacy_return": old,
    }
    for name, image in data.items():
        image.save(folder / (name + ".png"))


class FourVsFourOracleTest(unittest.TestCase):
    def test_hp_detector_rejects_fixed_window_coordinates(self):
        """NeXium viewport offset: frame-coordinate HP sampling is wrong."""
        original = Image.new("RGB", (oracle.WIDTH, oracle.HEIGHT),
                             BACKGROUND)
        after = original.copy()
        x, y = oracle.GX + 27, oracle.GY + 13
        for frame, hp in ((original, 3), (after, 1)):
            draw = ImageDraw.Draw(frame)
            draw.rectangle((x, y, x + 35, y + 35), fill=oracle.HERO)
            draw.rectangle((x - 1, y + 40,
                            x - 2 + hp * 8, y + 43), fill=HP)
            # The old fixed-coordinate test incorrectly read this outline.
            draw.rectangle((oracle.GX + 16, oracle.GY + 59,
                            oracle.GX + 25, oracle.GY + 62), fill=HP)
        self.assertEqual(oracle.health_bar_pixels(original, 0, 0), 96)
        self.assertEqual(oracle.health_bar_pixels(after, 0, 0), 32)

    def proof(self, action=None, issue=None):
        with tempfile.TemporaryDirectory(prefix="vh-map02-four-oracle-") as root:
            folder = Path(root)
            make_images(folder)
            if action:
                action(folder)
            if issue:
                with self.assertRaisesRegex(ValueError, issue):
                    oracle.verify(folder)
            else:
                oracle.verify(folder)

    def test_correct_complete_win_loss_reset_is_accepted(self):
        self.proof()

    def test_rejects_missing_fourth_ally(self):
        def mutate(folder):
            im = oracle.read(folder, "four_start")
            avatar(im, 0, 3)
            im.save(folder / "four_start.png")
        self.proof(mutate, "lacks a live ally")

    def test_rejects_fake_first_attack(self):
        def mutate(folder):
            (folder / "first_kill.png").write_bytes(
                (folder / "four_start.png").read_bytes()
            )
        self.proof(mutate, "first legal attack")

    def test_rejects_fake_victory_if_one_foe_survives(self):
        def mutate(folder):
            im = oracle.read(folder, "four_victory")
            avatar(im, 1, 3, oracle.ENEMY, hp=2)
            im.save(folder / "four_victory.png")
        self.proof(mutate, "opponents survived")

    def test_rejects_enemy_phase_without_hp_damage(self):
        def mutate(folder):
            (folder / "enemy_turn_1.png").write_bytes(
                (folder / "four_start.png").read_bytes()
            )
        self.proof(mutate, "reduce live ally HP")

    def test_rejects_premature_loss_on_first_ai_phase(self):
        def mutate(folder):
            (folder / "enemy_turn_1.png").write_bytes(
                (folder / "four_defeat.png").read_bytes()
            )
        self.proof(mutate, "died prematurely")

    def test_rejects_missing_final_enemy_defeat(self):
        def mutate(folder):
            (folder / "four_defeat.png").write_bytes(
                (folder / "enemy_turn_1.png").read_bytes()
            )
        self.proof(mutate, "survived the second enemy attack")

    def test_rejects_failed_victory_reset(self):
        def mutate(folder):
            (folder / "four_reset.png").write_bytes(
                (folder / "four_victory.png").read_bytes()
            )
        self.proof(mutate, "reset")

    def test_rejects_failed_loss_reset(self):
        def mutate(folder):
            (folder / "defeat_reset.png").write_bytes(
                (folder / "four_defeat.png").read_bytes()
            )
        self.proof(mutate, "reset")

    def test_rejects_old_map_not_restored(self):
        def mutate(folder):
            (folder / "legacy_return.png").write_bytes(
                (folder / "four_start.png").read_bytes()
            )
        self.proof(mutate, "restore MAP 1")

    def test_rejects_invalid_dimensions(self):
        def mutate(folder):
            Image.new("RGB", (320, 180)).save(folder / "four_start.png")
        self.proof(mutate, "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
