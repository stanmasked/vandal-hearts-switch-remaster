"""Adversarial fake-frame regression for guard indicator screenshot oracle.

Synthetic frames verify the checker and are never used as proof of
emulator execution; the real job captures PNGs from the Switch NRO.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_map02_guard_oracle as inherited
import run_map02_nexium_guard_hud as hud

BKG = (0, 0, 0)
READY = (105, 126, 151)
ARMED = (255, 219, 102)
BLOCKED = (86, 190, 244)
ROI = (987, 568, 1085, 576)


def draw_state(image, state):
    ImageDraw.Draw(image).rectangle(ROI, fill=state)


def frames(folder):
    inherited.fixture(folder)
    sources = {
        "legacy": "legacy", "primary": "primary",
        "before": "second", "first_armed": "guard_armed",
        "first_expired": "second", "pre_attack": "after_three",
        "second_armed": "guard_armed", "blocked": "guarded",
        "reset": "second", "primary_return": "primary",
        "legacy_return": "legacy",
    }
    for dest, source in sources.items():
        im = hud.read(folder, source)
        if dest in ("before", "first_expired", "pre_attack", "reset"):
            draw_state(im, READY)
        elif dest in ("first_armed", "second_armed"):
            draw_state(im, ARMED)
        elif dest == "blocked":
            draw_state(im, BLOCKED)
        im.save(folder / (dest + ".png"))


class GuardHUDImageOracle(unittest.TestCase):
    def case(self, mutation=None, match=None):
        with tempfile.TemporaryDirectory(prefix="vh-guard-hud-") as path:
            root = Path(path)
            frames(root)
            if mutation:
                mutation(root)
            if match:
                with self.assertRaisesRegex(ValueError, match):
                    hud.verify(root)
            else:
                hud.verify(root)

    def replace(self, root, dest, source):
        (root / (dest + ".png")).write_bytes(
            (root / (source + ".png")).read_bytes())

    def test_accept_consistent_reference(self):
        self.case()

    def test_reject_no_arming_indicator(self):
        self.case(lambda r: self.replace(r, "first_armed", "before"),
                  "arming guard")

    def test_reject_nonexpired_guard(self):
        self.case(lambda r: self.replace(r, "first_expired", "first_armed"),
                  "no-hit guard")

    def test_reject_no_second_arming(self):
        self.case(lambda r: self.replace(r, "second_armed", "pre_attack"),
                  "second guard")

    def test_reject_forged_block_message(self):
        self.case(lambda r: self.replace(r, "blocked", "pre_attack"),
                  "actual absorbed hit")

    def test_reject_unmitigated_damage(self):
        self.case(lambda r: self.replace(r, "blocked", "before"),
                  "actual absorbed hit")

    def test_reject_bad_y_reset(self):
        self.case(lambda r: self.replace(r, "reset", "blocked"),
                  "Y reset")

    def test_reject_primary_scene_leak(self):
        def mutate(root):
            im = hud.read(root, "primary_return")
            draw_state(im, READY)
            im.save(root / "primary_return.png")
        self.case(mutate, "first arena")

    def test_reject_changed_original_map(self):
        self.case(lambda r: self.replace(r, "legacy_return", "blocked"),
                  "legacy MAP02")

    def test_reject_wrong_capture_dimensions(self):
        self.case(lambda r: Image.new("RGB", (320, 180)).save(
            r / "blocked.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
