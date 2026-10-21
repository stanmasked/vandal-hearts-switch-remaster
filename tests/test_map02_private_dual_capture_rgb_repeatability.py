"""Fictional PNG and capture paths only; source BK2 audit is mocked."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tools.map02_private_dual_capture_rgb_repeatability import verify
from tools.map02_private_visual_diff_triage import save_private_report


def chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def synthetic_png(rgb, *, metadata=False, width=2, alpha=None):
    if alpha is None:
        color = 2
        px = bytes(rgb)
    else:
        color = 6
        px = bytes(rgb) + bytes((alpha,))
    chunks = [
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, color, 0, 0, 0)),
    ]
    if metadata:
        chunks.append(chunk(b"tEXt", b"fake\x00different private metadata"))
    chunks.extend((
        chunk(b"IDAT", zlib.compress(b"\x00" + px * width)),
        chunk(b"IEND", b""),
    ))
    return b"\x89PNG\r\n\x1a\n" + b"".join(chunks)


LINES = [
    "VH_MAP02_CAPTURE_PLAN_V1",
    "movie_frames=933949",
    "capture_count=3",
    "1,before,3000,held",
    "1,middle,3250,neutral",
    "1,after,3500,held",
]
ROWS = (
    (1, "before", 3000, "held"),
    (1, "middle", 3250, "neutral"),
    (1, "after", 3500, "held"),
)
COLORS = ((5, 15, 25), (40, 50, 60), (100, 110, 120))


class PrivateDualRGBTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.movie = self.root / "fictional-source.bk2"
        self.movie.write_bytes(b"fictional BK2 source for synthetic audit only")
        self.plan = self.root / "private-plan.txt"
        self.plan.write_text("\n".join(LINES) + "\n", encoding="ascii")
        self.logs = [self.root / "first-console.log", self.root / "second-console.log"]
        self.folders = [self.root / "first-png", self.root / "second-png"]
        self.report = self.root / "private-rgb-repeatability.json"
        for log, folder in zip(self.logs, self.folders):
            log.write_text("fictional console content\n", encoding="utf-8")
            folder.mkdir()
            for (group, role, index, _), color in zip(ROWS, COLORS):
                (folder / self.name(group, role, index)).write_bytes(
                    synthetic_png(color))

    @staticmethod
    def name(group, role, index):
        return "vh_review_w%02d_%s_counter_%07d.png" % (group, role, index + 1)

    def image(self, bundle, role):
        row = next(r for r in ROWS if r[1] == role)
        return self.folders[bundle] / self.name(row[0], row[1], row[2])

    def call(self, *, count=3, threshold=0):
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
            return_value={"screenshot_count": count},
        ) as audit:
            result = verify(
                self.movie, self.plan, *(
                    self.logs[0], self.folders[0],
                    self.logs[1], self.folders[1],
                ),
                pixel_threshold=threshold, minimum=200, maximum=1000,
            )
        self.assertEqual(audit.call_count, 2)
        self.assertEqual(audit.call_args_list[0].kwargs["minimum"], 200)
        self.assertEqual(audit.call_args_list[1].kwargs["maximum"], 1000)
        return result

    def test_two_supplied_identical_pixel_sets_are_exact(self):
        result = self.call()
        self.assertEqual(result["compared_screenshot_positions"], 3)
        self.assertEqual(result["exact_decoded_rgb_matches"], 3)
        self.assertEqual(result["identical_png_file_bytes"], 3)
        self.assertEqual(result["decoded_rgb_discrepancy_positions"], 0)
        self.assertTrue(result["all_decoded_rgb_images_repeated_exactly"])
        self.assertEqual(len(result["matches_and_differences_by_review_position"]), 3)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_aggregate_source_evidence_digest_has_no_private_paths_or_frames(self):
        result = self.call()
        digest = result["source_capture_evidence_sha256"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertNotIn(str(self.root), json.dumps(result))
        public_fields = {
            key: value for key, value in result.items()
            if key != "source_capture_evidence_sha256"
        }
        self.assertNotIn("3000", json.dumps(public_fields))
        self.assertNotIn("vh_review_w", json.dumps(result))

    def test_git_checkout_source_is_rejected_before_evidence_hashing(self):
        (self.root / ".git").mkdir()
        with patch(
            "tools.map02_private_dual_capture_rgb_repeatability.capture_evidence_digest"
        ) as digest:
            with self.assertRaisesRegex(ValueError, "outside Git"):
                self.call()
        digest.assert_not_called()

    def test_source_evidence_digest_changes_when_a_planned_png_changes(self):
        first = self.call()["source_capture_evidence_sha256"]
        self.image(1, "middle").write_bytes(synthetic_png((240, 240, 240)))
        second = self.call()["source_capture_evidence_sha256"]
        self.assertNotEqual(first, second)

    def test_all_real_emulation_and_map_provenance_flags_remain_false(self):
        report = self.call()
        for key in (
            "two_actual_octoshock_runs_authenticated",
            "independent_replay_executions_authenticated",
            "correct_input_to_display_offset_verified",
            "scene_transition_verified", "map02_start_frame_identified",
            "source_native_gpu_vram_verified", "private_png_or_bk2_uploaded",
        ):
            self.assertFalse(report[key], key)

    def test_different_png_metadata_does_not_falsely_change_rgb(self):
        self.image(1, "middle").write_bytes(synthetic_png(COLORS[1], metadata=True))
        result = self.call()
        self.assertEqual(result["exact_decoded_rgb_matches"], 3)
        self.assertEqual(result["identical_png_file_bytes"], 2)
        mid = next(row for row in result["matches_and_differences_by_review_position"]
                   if row["frame_role"] == "middle")
        self.assertTrue(mid["same_decoded_rgb_pixels"])
        self.assertFalse(mid["same_png_file_bytes"])

    def test_single_position_pixel_change_is_reported_not_mislabelled_map02(self):
        self.image(1, "middle").write_bytes(synthetic_png((240, 240, 240)))
        result = self.call()
        self.assertFalse(result["all_decoded_rgb_images_repeated_exactly"])
        self.assertEqual(result["decoded_rgb_discrepancy_positions"], 1)
        self.assertEqual(result["matches_and_differences_by_review_position"][0]["frame_role"], "middle")
        self.assertFalse(result["map02_start_frame_identified"])

    def test_pixel_threshold_changes_fraction_but_not_exactness(self):
        self.image(1, "before").write_bytes(synthetic_png((6, 16, 26)))
        report = self.call(threshold=4)
        before = next(row for row in report["matches_and_differences_by_review_position"]
                      if row["frame_role"] == "before")
        self.assertEqual(before["cross_bundle"]["fraction_pixels_above_threshold"], 0.0)
        self.assertEqual(before["cross_bundle"]["mean_absolute_rgb_channel_delta"], 1.0)
        self.assertFalse(before["same_decoded_rgb_pixels"])
        self.assertEqual(report["decoded_rgb_discrepancy_positions"], 1)

    def test_both_logs_must_be_separate(self):
        self.logs[1].unlink()
        os.link(self.logs[0], self.logs[1])
        with self.assertRaises(ValueError):
            self.call()

    def test_both_image_roots_must_be_separate(self):
        self.folders[1].rename(self.root / "discarded")
        self.folders[1].symlink_to(self.folders[0], target_is_directory=True)
        with self.assertRaises(ValueError):
            self.call()

    def test_same_png_inode_across_bundles_refused(self):
        target = self.image(1, "middle")
        target.unlink()
        os.link(self.image(0, "middle"), target)
        with self.assertRaises(ValueError):
            self.call()

    def test_cross_role_hardlink_across_bundles_refused(self):
        target = self.image(1, "after")
        target.unlink()
        os.link(self.image(0, "before"), target)
        with self.assertRaises(ValueError):
            self.call()

    def test_symlink_png_refused(self):
        target = self.image(1, "before")
        target.unlink()
        target.symlink_to(self.image(0, "before"))
        with self.assertRaises(ValueError):
            self.call()

    def test_corrupt_png_is_rejected(self):
        p = self.image(1, "middle")
        p.write_bytes(b"not a PNG")
        with self.assertRaises(ValueError):
            self.call()

    def test_png_with_nonopaque_alpha_rejected(self):
        self.image(1, "middle").write_bytes(synthetic_png(COLORS[1], alpha=0))
        with self.assertRaises(ValueError):
            self.call()

    def test_resolution_mismatch_refused(self):
        self.image(1, "after").write_bytes(synthetic_png(COLORS[2], width=1))
        with self.assertRaises(ValueError):
            self.call()

    def test_source_chain_failure_rejected_before_image_comparison(self):
        with patch("tools.map02_private_dual_capture_rgb_repeatability.verify_chain",
                   side_effect=ValueError("fictional source mismatch")):
            with self.assertRaises(ValueError):
                verify(self.movie, self.plan, self.logs[0], self.folders[0],
                       self.logs[1], self.folders[1])

    def test_mismatched_proof_capture_count_refused(self):
        with self.assertRaises(ValueError):
            self.call(count=2)

    def test_out_of_bounds_pixel_threshold_refused(self):
        for threshold in (-1, 255, True, 1.2):
            with self.subTest(threshold=threshold):
                with self.assertRaises(ValueError):
                    self.call(threshold=threshold)

    def test_private_report_saved_0600_with_no_pixels(self):
        save_private_report(self.call(), self.report)
        self.assertEqual(self.report.stat().st_mode & 0o777, 0o600)
        body = self.report.read_text()
        self.assertNotIn(str(self.folders[0]), body)
        self.assertNotIn("vh_review_w01_", body)
        self.assertNotIn("3000", body)

    def test_private_report_overwrite_is_rejected(self):
        self.report.write_text("private preexisting content")
        with self.assertRaises(ValueError):
            save_private_report(self.call(), self.report)
        self.assertEqual(self.report.read_text(), "private preexisting content")


if __name__ == "__main__":
    unittest.main()
