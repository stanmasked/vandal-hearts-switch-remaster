"""Synthetic-only invented PNGs testing three-frame pre-candidate history.

No owner's BK2, original game, BIOS, private log or authentic screenshot.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import unittest
from PIL import Image

import test_verify_map02_private_animation_baseline as parent_fixture
from tools.verify_map02_private_three_pre_history import (
    SCHEMA, check_three_pre_history, select_five_frame_window, verify,
)


class ThreePreHistorySyntheticTests(unittest.TestCase):
    def setUp(self):
        self.parent = parent_fixture.AnimationBaselineSyntheticTests(
            "test_two_pre_and_persistent_distributed_change_pass")
        self.parent.setUp()
        self.addCleanup(self.parent.doCleanups)
        self.fixture = self.parent.fixture
        for run in (0, 1):
            _, _, folder, observations = self.fixture.source.runs[run]
            earlier = copy.deepcopy(observations[0])
            earlier["emulator_counter"] = 1950
            earlier["movie_input_candidate"] = 1949
            earlier["png_file"] = "synthetic-earliest-pre.png"
            contents = (folder / observations[0]["png_file"]).read_bytes()
            (folder / earlier["png_file"]).write_bytes(contents)
            earlier["sha256"] = hashlib.sha256(contents).hexdigest()
            observations.insert(0, earlier)
            self.parent._write_run(run)

    def paint(self, run, index, color, changed=()):
        self.parent.paint(run, index, color, changed=changed)

    def call(self):
        x, y = self.fixture.source.runs
        return verify(self.fixture.inspection, self.fixture.anchor,
                      *x[:3], *y[:3])

    def counters(self, clocks, run=None):
        for index in ((0, 1) if run is None else (run,)):
            _, _, _, records = self.fixture.source.runs[index]
            for shot, counter in zip(records, clocks):
                shot["emulator_counter"] = counter
                shot["movie_input_candidate"] = counter - 1
            self.parent._write_run(index)

    def test_three_equal_pre_samples_new_distributed_pixels_pass(self):
        receipt = self.call()
        self.assertEqual(receipt["schema"], SCHEMA)
        self.assertTrue(receipt["three_pre_rgba_samples_stable_for_counted_pixels"])
        self.assertTrue(receipt["two_supplied_five_frame_windows_checked"])
        self.assertEqual(receipt["owner_supplied_pre_frame_samples"], 3)
        for field in (
            "original_ps1_game_authenticated",
            "separate_real_emulator_processes_authenticated",
            "input_to_video_offset_authenticated",
            "actual_map02_scene_authenticated",
            "ps1_gpu_vram_parity_authenticated",
            "private_data_uploaded",
        ):
            self.assertFalse(receipt[field])
        self.assertNotIn("png_file", str(receipt))
        self.assertNotIn("sha256", str(receipt))

    def test_two_latest_equal_pre_images_hide_earlier_animation(self):
        # Previously admitted by the v1 two-pre gate:
        # third-pre=B, second-pre=A, last-pre=A, candidate=C, post=C.
        self.assertTrue(self.parent.check()["pre_existing_animation_pixels_excluded"])
        for run in (0, 1):
            self.paint(run, 0, (70, 20, 30))
        self.assertTrue(self.parent.check()["pre_existing_animation_pixels_excluded"])
        with self.assertRaisesRegex(ValueError, "outside three-pre animation"):
            self.call()

    def test_small_old_pre_cursor_motion_keeps_other_new_pixels(self):
        changed = tuple(
            (x, y, (50, 20, 30)) for x in range(4) for y in range(4))
        for run in (0, 1):
            self.paint(run, 0, (10, 20, 30), changed=changed)
        self.assertTrue(self.call()["new_stable_pixels_at_least_one_percent_and_four_tiles"])

    def test_fourteen_static_pre_positions_fail_minimum(self):
        stable = tuple(
            (x, y, (10, 20, 30))
            for x, y in ((1, 1), (2, 1), (3, 1), (1, 2),
                         (5, 1), (6, 1), (7, 1), (5, 2),
                         (9, 1), (10, 1), (11, 1), (9, 2),
                         (13, 1), (14, 1)))
        for run in (0, 1):
            self.paint(run, 0, (70, 20, 30), changed=stable)
        with self.assertRaisesRegex(ValueError, "insufficient new stable"):
            self.call()

    def test_sixteen_static_pre_positions_across_tiles_pass(self):
        stable = tuple(
            (x, y, (10, 20, 30))
            for x in (1, 5, 9, 13) for y in (1, 5, 9, 13))
        for run in (0, 1):
            self.paint(run, 0, (70, 20, 30), changed=stable)
        self.assertTrue(self.call()["three_pre_rgba_samples_stable_for_counted_pixels"])

    def test_sixteen_static_pre_positions_only_one_tile_fail(self):
        stable = tuple(
            (x, y, (10, 20, 30)) for x in range(4) for y in range(4))
        for run in (0, 1):
            self.paint(run, 0, (70, 20, 30), changed=stable)
        with self.assertRaisesRegex(ValueError, "too spatially localized"):
            self.call()

    def test_alpha_only_old_pre_animation_is_excluded(self):
        old = Image.new("RGBA", (16, 16), (10, 20, 30, 254))
        mid = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        recent = mid.copy()
        candidate = Image.new("RGBA", (16, 16), (100, 20, 30, 255))
        with self.assertRaisesRegex(ValueError, "outside three-pre animation"):
            check_three_pre_history(old, mid, recent, candidate, candidate.copy())

    def test_missing_third_pre_rejected_even_if_parent_accepts(self):
        for run in (0, 1):
            shots = self.fixture.source.runs[run][3]
            del shots[0]
            self.parent._write_run(run)
        self.assertTrue(self.parent.check()["pre_existing_animation_pixels_excluded"])
        with self.assertRaisesRegex(ValueError, "three pre"):
            self.call()

    def test_first_pre_outside_120_frame_gap_rejected(self):
        self.counters((1879, 2000, 2050, 2100, 2200))
        with self.assertRaisesRegex(ValueError, "too far apart"):
            self.call()

    def test_exact_120_gap_between_pre_images_allowed(self):
        self.counters((1880, 2000, 2050, 2100, 2200))
        self.assertTrue(self.call()["consecutive_pre_and_candidate_gaps_at_most_120"])

    def test_latest_three_pre_selected_with_four_pre_images(self):
        shots = [
            {"label": "pre_map02", "emulator_counter": 1800},
            {"label": "pre_map02", "emulator_counter": 1950},
            {"label": "pre_map02", "emulator_counter": 2000},
            {"label": "pre_map02", "emulator_counter": 2050},
            {"label": "map02_candidate", "emulator_counter": 2100},
            {"label": "post_map02", "emulator_counter": 2200},
        ]
        selected = select_five_frame_window(shots)
        self.assertEqual([x["emulator_counter"] for x in selected],
                         [1950, 2000, 2050, 2100, 2200])

    def test_changed_candidate_post_value_rejected_by_parent(self):
        for run in (0, 1):
            self.paint(run, 4, (120, 20, 30))
        with self.assertRaisesRegex(ValueError, "insufficient persistent"):
            self.call()

    def test_mismatched_private_run_movie_frame_counter_fails(self):
        self.counters((1950, 2000, 2051, 2100, 2200), run=1)
        with self.assertRaises(ValueError):
            self.call()

    def test_64_by_64_image_one_percent_rounds_up_to_41(self):
        # 64x64 = 4096; 1% needs ceil(40.96)=41, not 40.
        pre = Image.new("RGBA", (64, 64), (10, 20, 30, 255))
        candidate = Image.new("RGBA", (64, 64), (100, 20, 30, 255))
        post = Image.new("RGBA", (64, 64), (120, 20, 30, 255))
        positions = [(x, y) for x in (1, 17, 33, 49)
                     for y in (1, 17, 33, 49)]
        positions.extend([(x, y) for x in (2, 18, 34, 50)
                          for y in (2, 18, 34, 50)])
        positions.extend([(x, y) for x in (3, 19, 35, 51)
                          for y in (3, 19, 35, 51)])
        for x, y in positions[:40]:
            post.putpixel((x, y), (100, 20, 30, 255))
        with self.assertRaisesRegex(ValueError, "insufficient new stable"):
            check_three_pre_history(pre, pre, pre, candidate, post)
        x, y = positions[40]
        post.putpixel((x, y), (100, 20, 30, 255))
        check_three_pre_history(pre, pre, pre, candidate, post)


if __name__ == "__main__":
    unittest.main()
