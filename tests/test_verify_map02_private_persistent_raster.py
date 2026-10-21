"""All images are fabricated 16x16 PNGs; no owner BK2 or PS1 frames."""
from __future__ import annotations

from io import BytesIO
import hashlib
from pathlib import Path
import unittest

from PIL import Image

import test_verify_map02_private_start_candidate_order as parent_fixtures
from tools.verify_map02_private_persistent_raster import (
    SCHEMA, verify, persistent_witness, select_window,
)


class PersistentRasterSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.fixture = parent_fixtures.HandoffTests(
            "test_consistent_start_then_later_private_candidate")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for run in (0, 1):
            self.replace_png(run, 0, (10, 20, 30))
            self.replace_png(run, 1, (100, 20, 30))
            self.replace_png(run, 2, (100, 20, 30))

    def replace_png(self, run, observation, color, *,
                    dimensions=(16, 16), changed=()):
        _, _, folder, manifest = self.fixture.source.runs[run]
        picture = Image.new("RGB", dimensions, color)
        for x, y, rgb in changed:
            picture.putpixel((x, y), rgb)
        buffer = BytesIO()
        picture.save(buffer, format="PNG", compress_level=(1 if run else 6))
        contents = buffer.getvalue()
        (folder / manifest[observation]["png_file"]).write_bytes(contents)
        manifest[observation]["sha256"] = hashlib.sha256(contents).hexdigest()
        self.fixture.source.rewrite(run)

    def call(self):
        f = self.fixture
        a, b = f.source.runs
        return verify(f.inspection, f.anchor, *a[:3], *b[:3])

    def test_distributed_persistent_change_across_two_replays_passes(self):
        result = self.call()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertTrue(result["two_supplied_raster_windows_pass"])
        self.assertTrue(result["persistent_candidate_post_rgba_values_identical"])
        self.assertTrue(result["post_capture_within_120_counters"])
        for name in (
            "original_ps1_game_authenticated",
            "real_independent_emulator_runs_authenticated",
            "input_to_displayed_frame_offset_authenticated",
            "actual_map02_scene_transition_authenticated",
            "gameplay_or_gpu_vram_parity_authenticated",
            "private_png_logs_or_hashes_uploaded",
        ):
            self.assertFalse(result[name])
        self.assertNotIn("png_file", str(result))
        self.assertNotIn("sha256", str(result))

    def test_two_runs_use_different_png_compression_without_false_difference(self):
        a, b = self.fixture.source.runs
        self.assertNotEqual((a[2] / a[3][1]["png_file"]).read_bytes(),
                            (b[2] / b[3][1]["png_file"]).read_bytes())
        self.assertTrue(self.call()["two_supplied_raster_windows_pass"])

    def test_one_pixel_cursor_only_is_rejected(self):
        for run in (0, 1):
            for i in (1, 2):
                self.replace_png(
                    run, i, (10, 20, 30),
                    changed=((0, 0, (11, 20, 30)),))
        with self.assertRaisesRegex(ValueError, "insufficient persistent"):
            self.call()

    def test_sixteen_changed_pixels_confined_to_one_tile_rejected(self):
        changed = tuple((x, y, (100, 20, 30))
                        for x in range(4) for y in range(4))
        for run in (0, 1):
            for i in (1, 2):
                self.replace_png(run, i, (10, 20, 30), changed=changed)
        with self.assertRaisesRegex(ValueError, "too spatially localized"):
            self.call()

    def test_large_candidate_change_that_disappears_in_post_rejected(self):
        for run in (0, 1):
            self.replace_png(run, 2, (10, 20, 30))
        with self.assertRaisesRegex(ValueError, "insufficient persistent"):
            self.call()

    def test_two_big_changes_at_same_positions_do_not_mean_stable(self):
        # Former false positive: PRE=10, candidate=100, POST=120 over
        # all 256 pixels. Same coordinates differ twice, yet no pixel's
        # candidate RGBA value survives to the post frame.
        for run in (0, 1):
            self.replace_png(run, 2, (120, 20, 30))
        with self.assertRaisesRegex(
            ValueError, "insufficient persistent same-value"
        ):
            self.call()

    def test_fifteen_exact_stable_pixels_do_not_meet_minimum(self):
        # 241 moving pixels cannot inflate the 15 truly stable pixels.
        stable = tuple(
            (x, y, (100, 20, 30))
            for x, y in ((1,1),(2,1),(3,1),(1,2),
                         (5,1),(6,1),(7,1),(5,2),
                         (9,1),(10,1),(11,1),(9,2),
                         (13,1),(14,1),(15,1))
        )
        for run in (0, 1):
            self.replace_png(run, 2, (120, 20, 30), changed=stable)
        with self.assertRaisesRegex(
            ValueError, "insufficient persistent same-value"
        ):
            self.call()

    def test_sixteen_exact_stable_pixels_across_tiles_passes(self):
        # Exactly 16 pixels persist with equal candidate/post color,
        # distributed over 16 different grid tiles; other pixels move.
        stable = tuple(
            (x, y, (100, 20, 30))
            for x in (1, 5, 9, 13) for y in (1, 5, 9, 13)
        )
        for run in (0, 1):
            self.replace_png(run, 2, (120, 20, 30), changed=stable)
        report = self.call()
        self.assertTrue(report["persistent_candidate_post_rgba_values_identical"])
        self.assertEqual(report["schema"], SCHEMA)
        self.assertFalse(report["actual_map02_scene_transition_authenticated"])

    def test_sixteen_stable_pixels_only_one_tile_is_rejected(self):
        stable = tuple(
            (x, y, (100, 20, 30))
            for x in range(4) for y in range(4)
        )
        for run in (0, 1):
            self.replace_png(run, 2, (120, 20, 30), changed=stable)
        with self.assertRaisesRegex(
            ValueError, "persistent change too spatially localized"
        ):
            self.call()

    def test_alpha_only_post_change_invalidates_rgba_stability(self):
        pre = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
        candidate = Image.new("RGBA", (16, 16), (100, 20, 30, 255))
        post = Image.new("RGBA", (16, 16), (100, 20, 30, 254))
        with self.assertRaisesRegex(
            ValueError, "insufficient persistent same-value"
        ):
            persistent_witness(pre, candidate, post)

    def test_post_captured_too_late_rejected(self):
        self.fixture.change_counters((2000, 2100, 2221))
        with self.assertRaisesRegex(ValueError, "post observation too remote"):
            self.call()

    def test_post_exactly_120_frames_later_allowed(self):
        self.fixture.change_counters((2000, 2100, 2220))
        self.assertTrue(self.call()["post_capture_within_120_counters"])

    def test_missing_post_label_rejected(self):
        for run in (0, 1):
            self.fixture.source.runs[run][3][2]["label"] = "map02_candidate"
            self.fixture.source.rewrite(run)
        with self.assertRaisesRegex(ValueError, "pre, candidate and post"):
            self.call()

    def test_different_capture_dimensions_across_scene_rejected(self):
        for run in (0, 1):
            self.replace_png(run, 1, (100, 20, 30), dimensions=(20, 16))
        with self.assertRaisesRegex(ValueError, "dimensions incompatible"):
            self.call()

    def test_one_run_different_post_frame_fails_parent_repeatability(self):
        self.replace_png(1, 2, (120, 10, 30))
        with self.assertRaisesRegex(ValueError, "decoded PNG pixels differ"):
            self.call()

    def test_forged_start_provenance_rejected(self):
        start = parent_fixtures.anchor_report()
        start["real_independent_emulator_runs_authenticated"] = True
        # The parent expects strictly defined keys; overclaim must fail.
        self.fixture.write_start(start)
        with self.assertRaises(ValueError):
            self.call()

    def test_small_icon_sized_raster_rejected(self):
        for run in (0, 1):
            self.replace_png(run, 0, (10, 20, 30), dimensions=(1, 1))
            self.replace_png(run, 1, (100, 20, 30), dimensions=(1, 1))
            self.replace_png(run, 2, (100, 20, 30), dimensions=(1, 1))
        with self.assertRaisesRegex(ValueError, "too small"):
            self.call()

    def test_strong_change_without_early_pre_fails_closed(self):
        obs = [
            {"label": "map02_candidate", "emulator_counter": 3000},
            {"label": "post_map02", "emulator_counter": 3010},
        ]
        with self.assertRaisesRegex(ValueError, "pre, candidate and post"):
            select_window(obs)

    def test_three_frames_with_identical_pixels_never_count_as_transition(self):
        with self.assertRaisesRegex(ValueError, "insufficient persistent"):
            picture = Image.new("RGBA", (16, 16), (100, 2, 3, 255))
            persistent_witness(picture, picture.copy(), picture.copy())


if __name__ == "__main__":
    unittest.main()
