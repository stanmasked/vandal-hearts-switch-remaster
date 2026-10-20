"""Adversarial synthetic PNG oracle for interrupt and fresh action reentry.

Only the separate NeXium CI run provides authentic emulator evidence.
"""
from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_map02_nexium_reentry_actions as proof
from test_map02_interrupts_oracle import fixtures
from test_map02_guard_oracle import actor
from run_map02_nexium_4v4 import HERO, ACTED


def create(folder: Path):
    fixtures(folder)
    armed = proof.read(folder, "armed_before_hit")
    damaged = proof.read(folder, "blocked")
    healed = damaged.copy()
    actor(healed, 1, 0, HERO, 3)
    actor(healed, 1, 1, ACTED, 3)
    frames = {
        "reentered_guard": armed,
        "reentered_block": damaged,
        "reentered_heal": healed,
        "reentered_reset": proof.read(folder, "second"),
        "reentered_bow_ready": proof.read(folder, "bow_ready"),
        "reentered_bow_hit": proof.read(folder, "bow_hit"),
    }
    for name, image in frames.items():
        image.save(folder / (name + ".png"))


class ReentryActionOracle(unittest.TestCase):
    def case(self, mutation=None, error=None):
        with tempfile.TemporaryDirectory(prefix="vh-reentry-") as td:
            folder = Path(td)
            create(folder)
            if mutation:
                mutation(folder)
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    proof.verify(folder)
            else:
                proof.verify(folder)

    @staticmethod
    def replace(folder, dest, source):
        (folder / (dest + ".png")).write_bytes(
            (folder / (source + ".png")).read_bytes())

    def test_valid_synthetic_reentry(self):
        self.case()

    def test_reject_missing_fresh_guard(self):
        self.case(lambda p: self.replace(p, "reentered_guard", "pre_hit"),
                  "reentered guard action")

    def test_reject_stale_protection_after_hit(self):
        self.case(lambda p: self.replace(p, "reentered_block", "reentered_guard"),
                  "reentered guard damage")

    def test_reject_medic_not_healing_after_reentry(self):
        self.case(lambda p: self.replace(p, "reentered_heal", "reentered_block"),
                  "medic recovery")

    def test_reject_unspent_medic_after_reentry(self):
        def bad(folder):
            image = proof.read(folder, "reentered_heal")
            actor(image, 1, 1, HERO, 3)
            image.save(folder / "reentered_heal.png")
        self.case(bad, "medic action not spent")

    def test_reject_stale_y_reset_after_treatment(self):
        self.case(lambda p: self.replace(p, "reentered_reset", "reentered_block"),
                  "Y did not reset")

    def test_reject_unavailable_archer_after_reentry(self):
        self.case(lambda p: self.replace(p, "reentered_bow_ready", "second"),
                  "bow movement or AI pursuit")

    def test_reject_bow_that_did_not_kill(self):
        self.case(lambda p: self.replace(p, "reentered_bow_hit", "reentered_bow_ready"),
                  "bow could not kill")

    def test_reject_missing_minus_free_roam(self):
        self.case(lambda p: self.replace(p, "demo_off", "legacy"),
                  "MINUS did not actually disable")

    def test_reject_bad_capture_dimensions(self):
        self.case(lambda p: Image.new("RGB", (320,180)).save(
            p / "reentered_guard.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
