"""Adversarial synthetic image probes for six-entry NeXium stress test.

The synthetic PNGs are NEVER interpreted as real emulator evidence.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from PIL import Image

import run_map02_nexium_reentry_stress as run
from test_map02_interrupts_oracle import fixtures as interruption_fixtures
from test_map02_single_session_oracle import tag, READY


def fixtures(root: Path):
    interruption_fixtures(root)
    for i, route in enumerate(run.ROUTES):
        for dest, source in (
            (f"cycle{i}_armed", "armed_before_scene"),
            (f"cycle{i}_second", "second"),
            (f"cycle{i}_legacy", "legacy"),
            (f"cycle{i}_primary", "primary"),
        ):
            (root / (dest + ".png")).write_bytes(
                (root / (source + ".png")).read_bytes())
    extra = {
        "cycle1_three": "roster_three",
        "cycle1_one": "roster_one",
        "cycle2_scene_a": "primary",
        "cycle4_pre_hit": "pre_hit",
        "cycle4_blocked": "blocked",
        "cycle5_free_roam": "demo_off",
    }
    for dest, source in extra.items():
        (root / (dest + ".png")).write_bytes(
            (root / (source + ".png")).read_bytes())


class ReentryStressOracle(unittest.TestCase):
    def scenario(self, mutation=None, error=None):
        with tempfile.TemporaryDirectory(prefix="vh-map02-reentry-") as dirname:
            root = Path(dirname)
            fixtures(root)
            if mutation:
                mutation(root)
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    run.verify(root)
            else:
                run.verify(root)

    @staticmethod
    def replace(root, destination, source):
        (root / (destination + ".png")).write_bytes(
            (root / (source + ".png")).read_bytes())

    def test_accept_synthetic_six_cycle_sequence(self):
        self.scenario()

    def test_reject_cycle_zero_not_armed(self):
        self.scenario(lambda p: self.replace(p, "cycle0_armed", "second"),
                      "shield was not armed")

    def test_reject_cycle_four_not_armed(self):
        self.scenario(lambda p: self.replace(p, "cycle4_armed", "second"),
                      "shield was not armed")

    def test_reject_stale_y_reset(self):
        self.scenario(lambda p: self.replace(
            p, "cycle0_second", "cycle0_armed"), "retained battle state")

    def test_reject_roster_change_state_leak(self):
        self.scenario(lambda p: self.replace(
            p, "cycle1_second", "cycle1_armed"), "retained battle state")

    def test_reject_scene_change_state_leak(self):
        self.scenario(lambda p: self.replace(
            p, "cycle2_second", "cycle2_armed"), "retained battle state")

    def test_reject_chord_exit_state_leak(self):
        self.scenario(lambda p: self.replace(
            p, "cycle3_second", "cycle3_armed"), "retained battle state")

    def test_reject_unhealed_hp_after_guard_block_exit(self):
        self.scenario(lambda p: self.replace(
            p, "cycle4_second", "cycle4_blocked"), "retained battle state")

    def test_reject_minus_reentry_state_leak(self):
        self.scenario(lambda p: self.replace(
            p, "cycle5_second", "cycle5_armed"), "retained battle state")

    def test_reject_stale_legacy_after_chord(self):
        self.scenario(lambda p: self.replace(
            p, "cycle3_legacy", "second"), "approved original MAP02")

    def test_reject_stale_legacy_after_actual_hit(self):
        self.scenario(lambda p: self.replace(
            p, "cycle4_legacy", "second"), "approved original MAP02")

    def test_reject_first_arena_after_reentry(self):
        self.scenario(lambda p: self.replace(
            p, "cycle5_primary", "second"), "original expanded arena")

    def test_reject_extra_ally_in_3v3(self):
        self.scenario(lambda p: self.replace(
            p, "cycle1_three", "second"), "phantom 4th ally")

    def test_reject_extra_ally_in_1v4(self):
        self.scenario(lambda p: self.replace(
            p, "cycle1_one", "second"), "retained absent ally")

    def test_reject_fake_guard_not_unavailable_in_1v4(self):
        def forge(root):
            frame = run.read(root, "cycle1_one")
            tag(frame, READY)
            frame.save(root / "cycle1_one.png")
        self.scenario(forge, "unavailable guard")

    def test_reject_scene_a_contamination_during_l(self):
        self.scenario(lambda p: self.replace(
            p, "cycle2_scene_a", "second"), "scene change preserved")

    def test_reject_no_real_guarded_ai_hit(self):
        self.scenario(lambda p: self.replace(
            p, "cycle4_blocked", "cycle4_pre_hit"), "protected enemy hit")

    def test_reject_armed_label_without_blocked_transition(self):
        self.scenario(lambda p: self.replace(
            p, "cycle4_blocked", "cycle4_armed"), "protected enemy hit")

    def test_reject_fake_minus_exit(self):
        self.scenario(lambda p: self.replace(
            p, "cycle5_free_roam", "legacy"), "did not actually leave")

    def test_reject_wrong_screenshot_dimensions(self):
        self.scenario(lambda p: Image.new("RGB", (320, 180)).save(
            p / "cycle4_blocked.png"), "unexpected NeXium screenshot")


if __name__ == "__main__":
    unittest.main()
