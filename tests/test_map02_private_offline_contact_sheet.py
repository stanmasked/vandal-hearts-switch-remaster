"""Entirely invented BK2 review metrics for an offline HTML viewer.

No original PlayStation game, real BK2, real screenshot or private log.
"""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_offline_contact_sheet import (
    render_private_html, write_private_contact_sheet,
    main,
)


def synthetic_report():
    return {
        "screenshot_count": 3,
        "map02_identified": False,
        "bizhawk_replay_authenticated": False,
        "private_visual_review_candidates": [{
            "review_group": 1,
            "zero_based_input_indices": [3000, 3250, 3500],
            "screenshot_dimensions": [2, 1],
            "before_to_middle": {
                "fraction_pixels_above_threshold": .5,
                "mean_absolute_rgb_channel_delta": 50.0,
            },
            "middle_to_after": {
                "fraction_pixels_above_threshold": 0.0,
                "mean_absolute_rgb_channel_delta": 0.0,
            },
            "prominent_unmasked_pixel_difference": True,
        }],
    }


class PrivateOfflineHTMLTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.plan = self.folder / "private-plan.txt"
        self.movie = self.folder / "private-original.bk2"
        self.log = self.folder / "private-console.log"
        self.html = self.folder / "private-bk2-contact-sheet.html"
        self.report = synthetic_report()

    def test_valid_html_contains_local_three_role_pngs(self):
        text = render_private_html(self.report)
        for target in (
            "vh_review_w01_before_counter_0003001.png",
            "vh_review_w01_middle_counter_0003251.png",
            "vh_review_w01_after_counter_0003501.png",
        ):
            self.assertIn('src="' + target + '"', text)
        self.assertEqual(text.count('<img src="'), 3)
        self.assertIn("3000", text)
        self.assertIn("Ввод", text.replace("ввод", "Ввод"))

    def test_offline_csp_rejects_network_scripts_forms_and_external_css(self):
        text = render_private_html(self.report)
        self.assertIn("script-src 'none'", text)
        self.assertIn("connect-src 'none'", text)
        self.assertIn("default-src 'none'", text)
        self.assertIn("form-action 'none'", text)
        self.assertIn("no-referrer", text)
        self.assertNotIn("<script", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("@import", text)

    def test_html_explicitly_does_not_claim_map02_or_ps1_timing(self):
        text = render_private_html(self.report)
        self.assertIn("Не доказано", text)
        self.assertIn("MAP02", text)
        self.assertIn("GPU/VRAM", text)
        self.assertIn("не доказанными кадрами", text)

    def test_duplicate_review_groups_rejected(self):
        copy = deepcopy(self.report)
        copy["private_visual_review_candidates"].append(
            deepcopy(copy["private_visual_review_candidates"][0]))
        copy["screenshot_count"] = 6
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_missing_provenance_false_rejected(self):
        copy = deepcopy(self.report)
        copy["map02_identified"] = True
        with self.assertRaises(ValueError):
            render_private_html(copy)
        copy = deepcopy(self.report)
        copy.pop("bizhawk_replay_authenticated")
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_incorrect_screenshot_count_rejected(self):
        copy = deepcopy(self.report)
        copy["screenshot_count"] = 2
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_forged_boolean_frame_counter_rejected(self):
        copy = deepcopy(self.report)
        copy["private_visual_review_candidates"][0]["zero_based_input_indices"][0] = True
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_misordered_or_duplicate_frames_rejected(self):
        copy = deepcopy(self.report)
        copy["private_visual_review_candidates"][0]["zero_based_input_indices"] = [3000, 3500, 3250]
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_bad_pixel_metrics_rejected(self):
        for fraction in (-1, 1.01, True, float("nan")):
            copy = deepcopy(self.report)
            copy["private_visual_review_candidates"][0]["before_to_middle"]["fraction_pixels_above_threshold"] = fraction
            with self.subTest(value=fraction), self.assertRaises(ValueError):
                render_private_html(copy)

    def test_oversized_screenshot_dimensions_rejected(self):
        copy = deepcopy(self.report)
        copy["private_visual_review_candidates"][0]["screenshot_dimensions"] = [8000, 8000]
        with self.assertRaises(ValueError):
            render_private_html(copy)

    def test_private_html_saved_0600_adjacent_to_png_directory(self):
        count = write_private_contact_sheet(self.report, self.folder, self.html)
        self.assertEqual(count, 1)
        self.assertEqual(self.html.stat().st_mode & 0o777, 0o600)
        data = self.html.read_text()
        self.assertIn("vh_review_w01_middle_counter_0003251.png", data)
        self.assertNotIn(str(self.folder), data)
        self.assertNotIn("/mnt/data", data)

    def test_refuses_existing_output_without_changes(self):
        self.html.write_text("keep private")
        with self.assertRaises(ValueError):
            write_private_contact_sheet(self.report, self.folder, self.html)
        self.assertEqual(self.html.read_text(), "keep private")

    def test_refuses_symbolic_link_target(self):
        original = self.folder / "target"
        original.write_text("keep secret")
        self.html.symlink_to(original)
        with self.assertRaises(ValueError):
            write_private_contact_sheet(self.report, self.folder, self.html)
        self.assertEqual(original.read_text(), "keep secret")

    def test_refuses_output_inside_git_checkout(self):
        (self.folder / ".git").mkdir()
        with self.assertRaises(ValueError):
            write_private_contact_sheet(self.report, self.folder, self.html)
        self.assertFalse(self.html.exists())

    def test_refuses_cross_directory_or_relative_html(self):
        private_subdir = self.folder / "other"
        private_subdir.mkdir()
        with self.assertRaises(ValueError):
            write_private_contact_sheet(
                self.report, self.folder, private_subdir / "contact.html")
        with self.assertRaises(ValueError):
            write_private_contact_sheet(
                self.report, self.folder, Path("contact.html"))

    def test_rejects_non_html_filename(self):
        with self.assertRaises(ValueError):
            write_private_contact_sheet(self.report, self.folder,
                                        self.folder / "contact.txt")

    def test_source_audit_failure_does_not_create_html(self):
        with patch(
            "tools.map02_private_offline_contact_sheet.triage",
            side_effect=ValueError("synthetic source audit failed")
        ):
            with self.assertRaises(SystemExit):
                import sys
                from unittest.mock import patch as again
                with again.object(sys, "argv", [
                    "map02_private_offline_contact_sheet",
                    str(self.movie), str(self.plan), str(self.log),
                    str(self.folder), "--private-html-output", str(self.html),
                ]):
                    main()
        self.assertFalse(self.html.exists())


if __name__ == "__main__":
    unittest.main()
