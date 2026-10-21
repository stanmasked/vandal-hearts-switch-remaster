"""Private two-run candidate screenshot comparison: fictional files only."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_two_capture_audit import audit_pair, main

ROWS = [(1, "before", 3000, "held"),
        (1, "middle", 3250, "neutral"),
        (1, "after", 3500, "held")]


class TwoPrivateCaptureAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.first = self.root / "cold-01"
        self.second = self.root / "cold-02"
        self.first.mkdir(mode=0o700)
        self.second.mkdir(mode=0o700)
        self.first.chmod(0o700)
        self.second.chmod(0o700)
        self.movie = self.root / "fictional.bk2"
        self.plan = self.root / "fictional-plan.txt"
        self.movie.write_bytes(b"fictional only")
        self.plan.write_bytes(b"fictional only")
        self.names = [
            "vh_review_w%02d_%s_counter_%07d.png" % (g, role, idx + 1)
            for g, role, idx, held in ROWS
        ]
        for group in (self.first, self.second):
            (group / "vh_private_capture.log").write_text("synthetic only")
            for index, filename in enumerate(self.names):
                (group / filename).write_bytes(b"fictional-PNG-" + bytes([index]))

    def call(self, **kwargs):
        first = kwargs.pop("first", self.first)
        second = kwargs.pop("second", self.second)
        count_a = kwargs.pop("count_a", len(ROWS))
        count_b = kwargs.pop("count_b", len(ROWS))
        with patch(
            "tools.map02_private_two_capture_audit.verify",
            side_effect=[{"screenshot_count": count_a},
                         {"screenshot_count": count_b}],
        ) as verifier, patch(
            "tools.map02_private_two_capture_audit.parse_plan",
            return_value=("fictional plan", ROWS),
        ):
            result = audit_pair(self.movie, self.plan, first, second)
        self.assertFalse(kwargs)
        return result, verifier

    def test_matching_two_private_capture_chains(self):
        report, verifier = self.call()
        self.assertEqual(verifier.call_count, 2)
        self.assertTrue(report["two_private_capture_chains_passed"])
        self.assertTrue(report["distinct_capture_directories"])
        self.assertEqual(report["screenshot_pairs_checked"], 3)
        self.assertEqual(report["byte_identical_png_pairs"], 3)
        self.assertEqual(report["byte_different_png_pairs"], 0)
        self.assertTrue(report["all_png_file_bytes_identical"])
        self.assertFalse(report["independent_cold_boots_authenticated"])
        self.assertFalse(report["actual_octoshock_playback_authenticated"])
        self.assertFalse(report["rendered_pixel_parity_verified"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("fictional-PNG", json.dumps(report))

    def test_different_screenshot_bytes_are_reported_not_authenticated(self):
        (self.second / self.names[1]).write_bytes(b"synthetic changed")
        report, _ = self.call()
        self.assertEqual(report["byte_identical_png_pairs"], 2)
        self.assertEqual(report["byte_different_png_pairs"], 1)
        self.assertFalse(report["all_png_file_bytes_identical"])
        self.assertTrue(report["byte_differences_require_manual_visual_review"])
        self.assertFalse(report["rendered_pixel_parity_verified"])

    def test_same_directory_rejected_before_capture_verification(self):
        with self.assertRaisesRegex(ValueError, "separate private directories"):
            self.call(second=self.first)

    def test_cross_run_hardlink_rejected(self):
        # Cross-platform synthetic inode collision without relying on link
        # support on the host filesystem.
        with patch(
            "tools.map02_private_two_capture_audit.os.stat",
            side_effect=ValueError("injected simulated cross-run collision"),
        ):
            with self.assertRaises(ValueError):
                self.call()

    def test_cross_run_actual_hardlink_rejected_where_supported(self):
        if os.name == "nt":
            self.skipTest("hardlink semantics vary on Windows")
        name = self.names[1]
        (self.second / name).unlink()
        os.link(self.first / name, self.second / name)
        with self.assertRaisesRegex(ValueError, "reuse screenshot inodes"):
            self.call()

    def test_symlink_png_rejected(self):
        name = self.names[1]
        (self.second / name).unlink()
        (self.second / name).symlink_to(self.first / name)
        with self.assertRaises(ValueError):
            self.call()

    def test_world_accessible_capture_root_rejected(self):
        if os.name == "nt":
            self.skipTest("POSIX mode bits are not Windows ACLs")
        self.second.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.call()

    def test_git_checkout_capture_root_rejected(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.call()

    def test_different_chain_counts_rejected(self):
        with self.assertRaisesRegex(ValueError, "counts differ"):
            self.call(count_b=2)

    def test_main_reports_only_aggregate_fields(self):
        args = ["audit", str(self.movie), str(self.plan), str(self.first),
                str(self.second)]
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_two_capture_audit.verify",
            side_effect=[{"screenshot_count": 3}, {"screenshot_count": 3}],
        ), patch(
            "tools.map02_private_two_capture_audit.parse_plan",
            return_value=("fictional plan", ROWS),
        ):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = main()
        self.assertEqual(status, 0)
        output = buffer.getvalue()
        self.assertTrue(json.loads(output)["all_png_file_bytes_identical"])
        self.assertNotIn(str(self.root), output)


if __name__ == "__main__":
    unittest.main()
