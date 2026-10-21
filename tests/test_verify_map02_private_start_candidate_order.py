"""Synthetic-only chronological handoff of Start anchor to later BK2 frames."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from tools.verify_map02_private_start_candidate_order import (
    START_SCHEMA, HANDOFF_SCHEMA, verify,
)
from test_compare_map02_private_replay_rasters import TwoReplayRasterTests, tiny_png


def anchor_report():
    return {
        "schema": START_SCHEMA,
        "separate_capture_bundle_count": 2,
        "capture_run_independence_authenticated": False,
        "matching_screenshot_counter_count": 3,
        "first_start_input_index_zero_based": 1661,
        "capture_counters_one_based": [1661, 1662, 1663],
        "png_sha256_repeats_identically": True,
        "recorded_movie_start_input_matches_expected_anchor": True,
        "emulator_playback_executed_authenticated": False,
        "screen_pixel_provenance_verified": False,
        "input_to_displayed_image_offset_independently_verified": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_or_vram_verified": False,
        "owner_private_files_uploaded": False,
    }


class HandoffTests(unittest.TestCase):
    def setUp(self):
        source = TwoReplayRasterTests(
            "test_decoded_pixels_equal_with_different_zlib_payloads")
        source.setUp()
        self.addCleanup(source.doCleanups)
        self.source = source
        self.root = source.root
        self.inspection = source.inspection
        report = json.loads(self.inspection.read_text(encoding="utf-8"))
        report["input_log_frame_count"] = 933949
        self.inspection.write_text(json.dumps(report), encoding="utf-8")
        self.anchor = self.root / "start-report.json"
        self.anchor.write_text(json.dumps(anchor_report()), encoding="utf-8")
        self.change_counters((2000, 2100, 2200))

    def change_counters(self, counters, run_index=None):
        indices = (0, 1) if run_index is None else (run_index,)
        for index in indices:
            markers, manifest, images, records = self.source.runs[index]
            for shot, counter in zip(records, counters):
                shot["emulator_counter"] = counter
                shot["movie_input_candidate"] = counter - 1
            markers.write_text("\n".join(
                f"VH_PRIVATE_REPLAY_MARKER counter={counter} "
                f"candidate_input={counter-1} mode=PLAY scene=unverified"
                for counter in counters) + "\n", encoding="utf-8")
            self.source.rewrite(index)

    def call(self):
        a, b = self.source.runs
        return verify(self.inspection, self.anchor, *a[:3], *b[:3])

    def write_start(self, data):
        self.anchor.write_text(json.dumps(data), encoding="utf-8")

    def test_consistent_start_then_later_private_candidate(self):
        result = self.call()
        self.assertEqual(result["schema"], HANDOFF_SCHEMA)
        self.assertEqual(result["later_candidate_observation_pairs"], 3)
        self.assertTrue(result["all_candidate_observations_after_start_capture"])
        self.assertTrue(result["decoded_raster_repeatable_and_visibly_changed"])
        for key in (
            "start_png_bytes_reverified_by_this_tool",
            "original_ps1_disc_authenticated", "real_emulator_runs_authenticated",
            "input_to_video_timing_verified", "map02_scene_frame_identified",
            "gameplay_or_ps1_vram_parity_verified", "private_content_uploaded",
        ):
            self.assertFalse(result[key])
        self.assertNotIn("png_file", str(result))
        self.assertNotIn("sha256", str(result))

    def test_reject_pre_candidate_capture_equal_to_last_start(self):
        self.change_counters((1663, 2100, 2200))
        with self.assertRaisesRegex(ValueError, "overlaps or precedes"):
            self.call()

    def test_reject_initial_start_input_as_scene_candidate(self):
        self.change_counters((1662, 1663, 2200))
        with self.assertRaisesRegex(ValueError, "overlaps or precedes"):
            self.call()

    def test_accept_just_after_start_boundary(self):
        self.change_counters((1664, 1665, 1666))
        report = self.call()
        self.assertTrue(report["all_candidate_observations_after_start_capture"])

    def test_reject_claimed_start_index_drift(self):
        start = anchor_report()
        start["first_start_input_index_zero_based"] = 1662
        self.write_start(start)
        with self.assertRaisesRegex(ValueError, "incompatible Start"):
            self.call()

    def test_reject_wrong_three_start_counters(self):
        start = anchor_report()
        start["capture_counters_one_based"] = [1661, 1662, 1664]
        self.write_start(start)
        with self.assertRaisesRegex(ValueError, "incompatible Start"):
            self.call()

    def test_reject_start_report_asserting_actual_ps1_scene(self):
        start = anchor_report()
        start["map02_scene_frame_identified"] = True
        self.write_start(start)
        with self.assertRaisesRegex(ValueError, "overclaims"):
            self.call()

    def test_reject_start_report_claiming_independent_emulator_runs(self):
        start = anchor_report()
        start["capture_run_independence_authenticated"] = True
        self.write_start(start)
        with self.assertRaisesRegex(ValueError, "overclaims"):
            self.call()

    def test_reject_missing_start_report_field(self):
        start = anchor_report()
        del start["recorded_movie_start_input_matches_expected_anchor"]
        self.write_start(start)
        with self.assertRaisesRegex(ValueError, "incompatible Start"):
            self.call()

    def test_reject_duplicate_private_report_json_key(self):
        self.anchor.write_text(
            '{"schema":"x","schema":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate private"):
            self.call()

    def test_reject_incorrect_movie_frame_count(self):
        inspection = json.loads(self.inspection.read_text(encoding="utf-8"))
        inspection["input_log_frame_count"] = 5000
        self.inspection.write_text(json.dumps(inspection), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match Start"):
            self.call()

    def test_reject_differently_marked_private_sessions(self):
        self.change_counters((2000, 2101, 2200), run_index=1)
        with self.assertRaisesRegex(ValueError, "unequal input-frame"):
            self.call()

    def test_reject_modified_png_even_after_updating_its_hash(self):
        # The parent stage checks decoded RGBA equality, not merely a PNG hash.
        self.source.set_frame_pixels(1, 1, (250, 10, 1))
        with self.assertRaisesRegex(ValueError, "decoded PNG pixels differ"):
            self.call()

    def test_reject_static_candidate_screen(self):
        for run in (0, 1):
            self.source.set_frame_pixels(run, 1, (1, 3, 7))
        with self.assertRaisesRegex(ValueError, "no decoded raster change"):
            self.call()

    def test_reject_using_same_start_report_as_movie_inspection(self):
        a, b = self.source.runs
        with self.assertRaises(ValueError):
            verify(self.anchor, self.anchor, *a[:3], *b[:3])


if __name__ == "__main__":
    unittest.main()
