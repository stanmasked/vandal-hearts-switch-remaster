"""Only invented screenshots; underlying source BK2 chain is mocked in CI."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tools.map02_private_visual_diff_triage import (
    triage, save_private_report,
)


def chunk(kind, data):
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


def png(rgb, *, width=2, height=1, color=2, alpha=255):
    if color == 2:
        pixel = bytes(rgb)
    else:
        pixel = bytes(rgb) + bytes((alpha,))
    row = b"\x00" + pixel * width
    payload = row * height
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(payload)) +
            chunk(b"IEND", b""))


class PrivateVisualTriageTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.movie = self.root / "fictional-source.bk2"
        self.plan = self.root / "private-plan.txt"
        self.log = self.root / "private-console.log"
        self.pictures = self.root / "review-png"
        self.pictures.mkdir()
        self.report = self.root / "review-only.json"
        self.groups = (
            (1, ("before", "middle", "after"), (3000, 3250, 3500)),
            (2, ("before", "middle", "after"), (5000, 5250, 5500)),
        )
        rows = ["VH_MAP02_CAPTURE_PLAN_V1", "movie_frames=933949",
                "capture_count=6"]
        for group, roles, frames in self.groups:
            for role, index in zip(roles, frames):
                rows.append("%d,%s,%d,%s" %
                            (group, role, index, "neutral" if role == "middle" else "held"))
                name = "vh_review_w%02d_%s_counter_%07d.png" % (group, role, index + 1)
                color = (20, 20, 20) if group == 1 or role == "before" else (250, 250, 250)
                (self.pictures / name).write_bytes(png(color))
        self.plan.write_text("\n".join(rows) + "\n", encoding="ascii")

    def fake_chain(self):
        return patch(
            "tools.map02_private_visual_diff_triage.verify_chain",
            return_value={"screenshot_count": 6},
        )

    def call(self, **kwargs):
        with self.fake_chain() as audit:
            result = triage(
                self.movie, self.plan, self.log, self.pictures,
                minimum=kwargs.get("minimum", 180),
                maximum=kwargs.get("maximum", 1800),
                pixel_threshold=kwargs.get("threshold", 32),
            )
        self.assertEqual(audit.call_args.args,
                         (self.movie, self.plan, self.log, self.pictures))
        return result

    def test_prominent_pixel_change_ranks_first_but_not_map02(self):
        result = self.call()
        candidates = result["private_visual_review_candidates"]
        self.assertEqual([x["review_group"] for x in candidates], [2, 1])
        self.assertTrue(candidates[0]["prominent_unmasked_pixel_difference"])
        self.assertEqual(candidates[0]["before_to_middle"]["fraction_pixels_above_threshold"], 1.0)
        self.assertFalse(candidates[1]["prominent_unmasked_pixel_difference"])
        self.assertEqual(candidates[1]["before_to_after"]["fraction_pixels_above_threshold"], 0)
        self.assertEqual(result["screenshot_count"], 6)
        self.assertNotIn(str(self.root), str(result))

    def test_neither_color_change_nor_valid_png_means_map_identified(self):
        result = self.call()
        for key in ("map02_identified", "scene_transition_authenticated",
                    "bizhawk_replay_authenticated",
                    "real_ps1_input_to_display_offset_verified",
                    "gpu_vram_frame_authenticated", "owner_private_data_uploaded"):
            self.assertFalse(result[key])
        self.assertTrue(all(not x["actual_scene_transition_verified"]
                            for x in result["private_visual_review_candidates"]))

    def test_output_records_only_indices_metrics_and_dimensions(self):
        row = self.call()["private_visual_review_candidates"][0]
        self.assertEqual(row["zero_based_input_indices"], [5000, 5250, 5500])
        self.assertEqual(row["screenshot_dimensions"], [2, 1])
        self.assertNotIn("vh_review", json.dumps(row))

    def test_different_png_encoding_same_color_reports_no_difference(self):
        name = "vh_review_w01_middle_counter_0003251.png"
        (self.pictures / name).write_bytes(png((20, 20, 20), color=6))
        self.assertFalse(self.call()["private_visual_review_candidates"][1]
                         ["prominent_unmasked_pixel_difference"])

    def test_nonopaque_alpha_rejected_without_unsafe_compositing(self):
        name = "vh_review_w01_middle_counter_0003251.png"
        (self.pictures / name).write_bytes(png((20, 20, 20), color=6, alpha=0))
        with self.assertRaises(ValueError):
            self.call()

    def test_bad_png_crc_rejected(self):
        name = "vh_review_w02_after_counter_0005501.png"
        f = self.pictures / name
        raw = bytearray(f.read_bytes())
        raw[25] ^= 1
        f.write_bytes(raw)
        with self.assertRaises(ValueError):
            self.call()

    def test_wrong_image_resolution_rejected(self):
        name = "vh_review_w02_middle_counter_0005251.png"
        (self.pictures / name).write_bytes(png((250, 250, 250), width=1))
        with self.assertRaises(ValueError):
            self.call()

    def test_missing_image_refused(self):
        (self.pictures / "vh_review_w02_after_counter_0005501.png").unlink()
        with self.assertRaises(OSError):
            self.call()

    def test_bad_threshold_rejected(self):
        with self.assertRaises(ValueError):
            self.call(threshold=True)

    def test_underlying_chain_failure_prevents_visual_ranking(self):
        with patch("tools.map02_private_visual_diff_triage.verify_chain",
                   side_effect=ValueError("wrong BK2")),
                self.assertRaises(ValueError):
            triage(self.movie, self.plan, self.log, self.pictures)

    def test_save_report_0600_with_no_image_bytes(self):
        result = self.call()
        save_private_report(result, self.report)
        self.assertEqual(self.report.stat().st_mode & 0o777, 0o600)
        data = self.report.read_text()
        self.assertNotIn(str(self.root), data)
        self.assertNotIn("vh_review_", data)

    def test_existing_report_never_overwritten(self):
        self.report.write_text("keep")
        with self.assertRaises(ValueError):
            save_private_report(self.call(), self.report)
        self.assertEqual(self.report.read_text(), "keep")

    def test_symlink_report_target_never_overwritten(self):
        original = self.root / "original"
        original.write_text("private")
        self.report.symlink_to(original)
        with self.assertRaises(ValueError):
            save_private_report(self.call(), self.report)
        self.assertEqual(original.read_text(), "private")

    def test_report_inside_git_repository_refused(self):
        (self.root / ".git").mkdir()
        with self.assertRaises(ValueError):
            save_private_report(self.call(), self.report)
        self.assertFalse(self.report.exists())

    def test_relative_report_path_refused(self):
        with self.assertRaises(ValueError):
            save_private_report(self.call(), Path("relative-private-output.json"))


if __name__ == "__main__":
    unittest.main()
