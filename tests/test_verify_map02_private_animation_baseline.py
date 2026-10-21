"""Invented 16x16 PNGs only: no user BK2, PS1, game image or source frames."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import unittest

from PIL import Image

import test_verify_map02_private_persistent_raster as prior
from tools.verify_map02_private_animation_baseline import (
    SCHEMA, select_animation_window, check_animated_background, verify,
)


class AnimationBaselineSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.base = prior.PersistentRasterSyntheticTests(
            "test_distributed_persistent_change_across_two_replays_passes")
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.fixture = self.base.fixture
        # Previous synthetic images: pre@2000, candidate@2100, post@2200.
        # Add distinct second pre@2050 for both entirely fabricated runs.
        for run in (0, 1):
            markers, manifest, root, shots = self.fixture.source.runs[run]
            earlier = shots[0]
            second_pre = copy.deepcopy(earlier)
            second_pre["emulator_counter"] = 2050
            second_pre["movie_input_candidate"] = 2049
            second_pre["png_file"] = "synthetic-second-pre.png"
            image = (root / earlier["png_file"]).read_bytes()
            (root / second_pre["png_file"]).write_bytes(image)
            second_pre["sha256"] = hashlib.sha256(image).hexdigest()
            shots.insert(1, second_pre)
            self._write_run(run)

    def _write_run(self, run):
        markers, manifest, root, shots = self.fixture.source.runs[run]
        markers.write_text("\n".join(
            f"VH_PRIVATE_REPLAY_MARKER counter={shot['emulator_counter']} "
            f"candidate_input={shot['movie_input_candidate']} "
            "mode=PLAY scene=unverified"
            for shot in shots) + "\n", encoding="utf-8")
        self.fixture.source.rewrite(run)

    def paint(self, run, index, color, changed=()):
        self.base.replace_png(run, index, color, changed=changed)

    def check(self):
        a, b = self.fixture.source.runs
        return verify(self.fixture.inspection, self.fixture.anchor,
                      *a[:3], *b[:3])

    def change_counters(self, counters):
        for run in (0, 1):
            shots = self.fixture.source.runs[run][3]
            for shot, counter in zip(shots, counters):
                shot["emulator_counter"] = counter
                shot["movie_input_candidate"] = counter - 1
            self._write_run(run)

    def test_two_pre_and_persistent_distributed_change_pass(self):
        report = self.check()
        self.assertEqual(report["schema"], SCHEMA)
        self.assertTrue(report["pre_existing_animation_pixels_excluded"])
        self.assertTrue(report["new_changed_pixels_stable_into_post"])
        for field in (
            "original_ps1_game_authenticated",
            "two_real_emulator_processes_authenticated",
            "movie_to_video_offset_authenticated",
            "map02_scene_start_authenticated",
            "ps1_gpu_vram_parity_authenticated",
            "owner_private_files_uploaded",
        ):
            self.assertFalse(report[field])
        self.assertNotIn("png_file", str(report))
        self.assertNotIn("sha256", str(report))

    def test_entire_screen_animated_in_pre_is_excluded(self):
        # Prior gate would PASS (pre2=10, cand=100, post=100), but the
        # first pre already had another color, i.e. full-screen animation.
        for run in (0, 1):
            self.paint(run, 0, (50, 20, 30))
        with self.assertRaisesRegex(ValueError, "outside prior animation"):
            self.check()

    def test_small_prior_cursor_motion_is_ignored(self):
        changes = tuple((x, y, (90, 20, 30))
                        for x in range(4) for y in range(4))
        for run in (0, 1):
            self.paint(run, 0, (10, 20, 30), changed=changes)
        self.assertTrue(self.check()["pre_existing_animation_pixels_excluded"])

    def test_fifteen_stationary_pre_positions_fail_minimum(self):
        stationary = tuple(
            (x, y, (10, 20, 30))
            for x, y in ((1,1),(2,1),(3,1),(1,2),
                         (5,1),(6,1),(7,1),(5,2),
                         (9,1),(10,1),(11,1),(9,2),
                         (13,1),(14,1),(15,1))
        )
        for run in (0, 1):
            self.paint(run, 0, (50, 20, 30), changed=stationary)
        with self.assertRaisesRegex(ValueError, "outside prior animation"):
            self.check()

    def test_sixteen_stationary_pre_positions_across_tiles_pass(self):
        stationary = tuple(
            (x, y, (10, 20, 30))
            for x in (1,5,9,13) for y in (1,5,9,13)
        )
        for run in (0, 1):
            self.paint(run, 0, (50, 20, 30), changed=stationary)
        self.assertTrue(self.check()["new_changed_pixels_stable_into_post"])

    def test_sixteen_stationary_pre_positions_one_tile_fail(self):
        stationary = tuple(
            (x, y, (10, 20, 30))
            for x in range(4) for y in range(4)
        )
        for run in (0, 1):
            self.paint(run, 0, (50, 20, 30), changed=stationary)
        with self.assertRaisesRegex(ValueError, "too few screen tiles"):
            self.check()

    def test_earlier_pre_too_far_from_later_pre_rejected(self):
        self.change_counters((1929, 2050, 2100, 2200))
        with self.assertRaisesRegex(ValueError, "pre-animation baseline"):
            self.check()

    def test_recent_pre_too_far_from_candidate_rejected(self):
        self.change_counters((1900, 1950, 2100, 2200))
        with self.assertRaisesRegex(ValueError, "too remote from recent pre"):
            self.check()

    def test_pre_interval_exactly_120_accepted(self):
        self.change_counters((1880, 2000, 2100, 2200))
        self.assertTrue(self.check()["pre_baseline_and_post_intervals_within_120_counters"])

    def test_missing_second_pre_rejected(self):
        shots = [
            {"label": "pre_map02", "emulator_counter": 2000},
            {"label": "map02_candidate", "emulator_counter": 2100},
            {"label": "post_map02", "emulator_counter": 2200},
        ]
        with self.assertRaisesRegex(ValueError, "two pre"):
            select_animation_window(shots)

    def test_alpha_only_prior_animation_is_excluded(self):
        old = Image.new("RGBA", (16, 16), (10, 20, 30, 254))
        recent = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        candidate = Image.new("RGBA", (16, 16), (100, 20, 30, 255))
        post = candidate.copy()
        with self.assertRaisesRegex(ValueError, "outside prior animation"):
            check_animated_background(old, recent, candidate, post)

    def test_parent_still_rejects_candidate_post_color_drift(self):
        for run in (0, 1):
            self.paint(run, 3, (110, 20, 30))
        with self.assertRaisesRegex(ValueError, "insufficient persistent"):
            self.check()


if __name__ == "__main__":
    unittest.main()
