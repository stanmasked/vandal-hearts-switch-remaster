"""Synthetic UI images verify the NeXium battle screenshot oracle itself."""
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from check_map02_battle_nexium import (
    ACTED_HERO, ENEMY, GRID_X, GRID_Y, CELL, HERO, HEIGHT, WIDTH, audit
)


def unit_box(x, y):
    left = GRID_X + CELL * x + 17
    top = GRID_Y + CELL * y + 17
    return (left, top, left + 37, top + 37)


def make_evidence(root: Path) -> None:
    original = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    ImageDraw.Draw(original).rectangle((65, 20, 165, 42), fill=(250, 250, 250))
    original.save(root / "original.png")

    battle = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(battle)
    draw.rectangle(unit_box(1, 2), fill=HERO)
    draw.rectangle(unit_box(1, 4), fill=HERO)
    draw.rectangle(unit_box(5, 2), fill=ENEMY)
    draw.rectangle(unit_box(6, 4), fill=ENEMY)
    battle.save(root / "battle.png")

    moved = battle.copy()
    draw = ImageDraw.Draw(moved)
    draw.rectangle(unit_box(1, 2), fill=(0, 0, 0))
    draw.rectangle(unit_box(2, 2), fill=ACTED_HERO)
    moved.save(root / "moved.png")

    enemy_turn = moved.copy()
    draw = ImageDraw.Draw(enemy_turn)
    draw.rectangle(unit_box(2, 2), fill=HERO)
    draw.rectangle(unit_box(5, 2), fill=(0, 0, 0))
    draw.rectangle(unit_box(4, 2), fill=ENEMY)
    enemy_turn.save(root / "enemy.png")

    reset = battle.copy()
    # Small but perceptible variations at top simulate Lavapipe/X11
    # screenshot jitter. These are not allowed to hide mode switches.
    for x in range(300, 550):
        reset.putpixel((x, 37), (77, 77, 77))
    reset.save(root / "reset.png")


class NeXiumBattleScreenshotOracle(unittest.TestCase):
    def test_valid_move_muted_action_enemy_turn_and_reset(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root)
            stats = audit(root)
            self.assertGreater(stats["title_changed_pixels"], 1000)
            self.assertGreater(stats["hero_move_pixels"], 500)
            self.assertLess(stats["enemy_after_pixels"], 200)

    def test_refuses_fake_ally_move_even_when_title_changed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root)
            (root / "moved.png").write_bytes((root / "battle.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "move/restore hero"):
                audit(root)

    def test_refuses_missing_enemy_turn(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root)
            enemy = Image.open(root / "enemy.png").convert("RGB")
            ImageDraw.Draw(enemy).rectangle(unit_box(5, 2), fill=ENEMY)
            enemy.save(root / "enemy.png")
            with self.assertRaisesRegex(ValueError, "end-turn"):
                audit(root)

    def test_refuses_reset_that_preserves_actor_move(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root)
            (root / "reset.png").write_bytes((root / "enemy.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "move/restore hero"):
                audit(root)

    def test_refuses_wrong_screen_or_wrong_dimensions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root)
            (root / "battle.png").write_bytes((root / "original.png").read_bytes())
            with self.assertRaisesRegex(ValueError, "did not enter"):
                audit(root)
            make_evidence(root)
            Image.new("RGB", (320, 180)).save(root / "battle.png")
            with self.assertRaisesRegex(ValueError, "dimensions"):
                audit(root)


if __name__ == "__main__":
    unittest.main()
