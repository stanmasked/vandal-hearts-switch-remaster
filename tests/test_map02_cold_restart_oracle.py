"""Synthetic adversarial PNG tests for two genuinely separate NeXium boots.

Generated images are not authentic emulator evidence. The independent CI
emulator job must capture new PNGs and distinct OS process identifiers.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_map02_nexium_cold_restart as proof
from test_map02_single_session_oracle import create_synthetic_set, tag, READY, ARMED
from test_map02_guard_oracle import actor
from run_map02_nexium_4v4 import HERO, ACTED


SOURCES = {
    "legacy": "legacy",
    "primary": "primary",
    "second": "second",
    "pre_hit": "second",
    "guard_armed": "guard_armed",
    "guard_hit": "guard_hit",
    "medic_healed": "medic_healed",
    "reset": "second",
    "bow_ready": "bow_ready",
    "bow_hit": "bow_hit",
    "bow_reset": "second",
    "legacy_return": "legacy",
}


def fixtures(folder: Path):
    create_synthetic_set(folder)
    for boot in (1, 2):
        for stage, source in SOURCES.items():
            (folder / f"boot{boot}_{stage}.png").write_bytes(
                (folder / f"{source}.png").read_bytes())
    (folder / "processes.json").write_text(json.dumps({
        "emulator_processes": 2, "process_ids": [10001, 10002],
        "first_process_exited_before_second": True,
    }), encoding="utf-8")


class ColdRestartOracle(unittest.TestCase):
    def case(self, corrupt=None, expected=None):
        with tempfile.TemporaryDirectory(prefix="vh-cold-boot-") as tmp:
            folder = Path(tmp)
            fixtures(folder)
            if corrupt:
                corrupt(folder)
            if expected:
                with self.assertRaisesRegex(ValueError, expected):
                    proof.verify(folder)
            else:
                proof.verify(folder)

    @staticmethod
    def replace(folder, target, source):
        (folder / (target + ".png")).write_bytes(
            (folder / (source + ".png")).read_bytes())

    @staticmethod
    def change(folder, label, mutate):
        im = proof.read(folder, label)
        mutate(im)
        im.save(folder / (label + ".png"))

    @staticmethod
    def record(folder, **kwargs):
        path = folder / "processes.json"
        record = json.loads(path.read_text())
        record.update(kwargs)
        path.write_text(json.dumps(record), encoding="utf-8")

    def test_valid_fake_reference(self):
        self.case()

    def test_reject_one_process_pretending_to_be_two(self):
        self.case(lambda f: self.record(f, process_ids=[23, 23]),
                  "two separately terminated")

    def test_reject_first_process_never_terminated(self):
        self.case(lambda f: self.record(
            f, first_process_exited_before_second=False),
            "two separately terminated")

    def test_reject_only_one_boot(self):
        self.case(lambda f: self.record(f, emulator_processes=1),
                  "two separately terminated")

    def test_reject_boot_two_missing_ally(self):
        self.case(lambda f: self.change(
            f, "boot2_second", lambda im: actor(im, 1, 3)),
            "original second arena spawn missing")

    def test_reject_guard_not_armed_on_second_boot(self):
        self.case(lambda f: self.replace(
            f, "boot2_guard_armed", "boot2_pre_hit"),
            "guard READY/ARMED/BLOCKED")

    def test_reject_boot_two_guard_damage_missing(self):
        self.case(lambda f: self.replace(
            f, "boot2_guard_hit", "boot2_pre_hit"),
            "guard/medic damage mismatch")

    def test_reject_boot_one_medic_not_healing(self):
        self.case(lambda f: self.replace(
            f, "boot1_medic_healed", "boot1_guard_hit"),
            "guard/medic damage mismatch")

    def test_reject_boot_two_first_reset_leaking_state(self):
        self.case(lambda f: self.replace(
            f, "boot2_reset", "boot2_guard_hit"),
            "first Y reset")

    def test_reject_boot_one_bow_shot_missing(self):
        self.case(lambda f: self.replace(
            f, "boot1_bow_hit", "boot1_bow_ready"),
            "fresh bow action")

    def test_reject_second_boot_legacy_changed(self):
        self.case(lambda f: self.replace(
            f, "boot2_legacy_return", "boot2_second"),
            "old authored MAP02 changed")

    def test_reject_cross_boot_board_mismatch_with_individually_valid_stages(self):
        def bad(folder):
            def draw(im):
                ImageDraw.Draw(im).rectangle((740, 445, 751, 455),
                                             fill=(165, 58, 187))
            self.change(folder, "boot2_bow_ready", draw)
        self.case(bad, "non-deterministic on BOARD")

    def test_reject_cross_boot_hud_mismatch_without_breaking_state_validation(self):
        def bad(folder):
            def mutate(im):
                ImageDraw.Draw(im).rectangle((1040, 556, 1060, 564),
                                             fill=(170, 200, 80))
            self.change(folder, "boot2_bow_hit", mutate)
        self.case(bad, "non-deterministic on guard HUD")

    @staticmethod
    def change_one_rgb_channel(im, x, y):
        """Produce a real RGB difference of exactly one, below semantic tolerance."""
        rgb = list(im.getpixel((x, y)))
        rgb[0] += 1 if rgb[0] < 255 else -1
        im.putpixel((x, y), tuple(rgb))

    def test_reject_single_channel_one_unit_board_difference(self):
        self.case(lambda f: self.change(
            f, "boot2_bow_ready",
            lambda im: self.change_one_rgb_channel(im, 740, 445)),
            "non-deterministic on BOARD")

    def test_reject_single_channel_one_unit_hud_difference(self):
        self.case(lambda f: self.change(
            f, "boot2_bow_hit",
            lambda im: self.change_one_rgb_channel(im, 1040, 556)),
            "non-deterministic on guard HUD")

    def test_reject_wrong_dimensions(self):
        self.case(lambda f: Image.new("RGB", (640, 360)).save(
            f / "boot2_legacy.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
