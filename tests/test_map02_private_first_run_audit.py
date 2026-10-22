"""Stage513 offline one-run tests: entirely invented receipts; no original PS1."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.map02_private_bizhawk_poweron_launch import AUTO_WITNESS_NAME
from tools.map02_private_first_run_audit import (
    review_first_capture, main,
)
from tools.map02_private_process_witness_binding import (
    MAGIC as START_MAGIC, NAME as START_NAME,
)
from tools.map02_private_two_replay_runner import PLAN_NAME, RUN_NAMES

TICKS = 639000000000000123
PID = 4041
ROWS = [(1, "before", 3000, "held"), (1, "middle", 3100, "neutral"),
        (1, "after", 3200, "held")]
CHAIN = {
    "screenshot_count": 3,
    "private_plan_rebuilt_from_direct_bk2": True,
    "capture_logs_match_each_planned_input_and_counter": True,
    "owner_launcher_reports_successful_process_exit": True,
    "owner_log_reports_psx_core_fallback_disabled": True,
    "all_png_crc_zlib_scanlines_pass": True,
    "owner_log_reports_auto_core_witness_before_first_png": True,
}


def launch_bytes(pid=PID, ticks=TICKS):
    return (f"{START_MAGIC}\nprocess_id={pid}\n"
            f"process_start_utc_ticks={ticks}\n").encode("ascii")


def witness_bytes(pid=PID, ticks=TICKS, frame=1800):
    return ("VH_MAP02_RUNTIME_CORE_WITNESS_V1\n"
            "system=PSX\nloaded_core=Octoshock\n"
            "core_source=IEmulator.Attributes.CoreName\n"
            f"process_id={pid}\nprocess_start_utc_ticks={ticks}\n"
            f"frame_count={frame}\nbios=unverified\ndisc=unverified\n"
            "movie_sync=unverified\n").encode("ascii")


class OwnerFirstCaptureAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "owner-private"
        self.workspace.mkdir(mode=0o700)
        self.workspace.chmod(0o700)
        self.first = self.workspace / RUN_NAMES[0]
        self.first.mkdir(mode=0o700)
        self.first.chmod(0o700)
        self.movie = self.root / "fictional-input.bk2"
        self.movie.write_bytes(b"FICTIONAL_MOVIE_ONLY")
        self.plan = self.workspace / PLAN_NAME
        self.plan.write_bytes(b"FICTIONAL_PLAN_ONLY")
        (self.first / START_NAME).write_bytes(launch_bytes())
        (self.first / AUTO_WITNESS_NAME).write_bytes(witness_bytes())
        self.fake = self.root / "manual-fictional-octoshock.txt"
        self.fake.write_bytes(witness_bytes())

    def review(self, *, manual=None, chain=None, rows=None):
        data = dict(CHAIN if chain is None else chain)
        planned = ROWS if rows is None else rows
        with patch(
            "tools.map02_private_first_run_audit.verify",
            return_value=data,
        ) as verify, patch(
            "tools.map02_private_first_run_audit.parse_plan",
            return_value=("fictional plan", planned),
        ) as parse:
            report = review_first_capture(self.movie, self.workspace, manual)
        verify.assert_called_once_with(
            self.movie.resolve(strict=True), self.plan,
            self.first.resolve(strict=True) / "vh_private_capture.log",
            self.first.resolve(strict=True),
        )
        parse.assert_called_once_with(self.plan)
        return report

    def test_single_automatic_owner_receipt_and_three_screenshots(self):
        original_files = sorted(str(p) for p in self.workspace.rglob("*"))
        result = self.review()
        self.assertEqual(result["owner_private_capture_attempts_reaudited"], 1)
        self.assertEqual(result["capture_screenshot_count"], 3)
        self.assertTrue(result["private_octoshock_core_witness_matches_launched_pid_and_birth"])
        self.assertTrue(result["owner_log_reports_automatic_witness_before_first_png"])
        self.assertTrue(result["auto_core_frame_not_later_than_first_png"])
        for key in ("two_run_repeatability_audited",
                    "authentic_map02_scene_identified",
                    "bk2_controller_delivery_authenticated",
                    "independent_cold_boot_authenticated",
                    "original_ps1_disc_or_bios_authenticated"):
            self.assertFalse(result[key])
        self.assertEqual(original_files, sorted(str(p) for p in self.workspace.rglob("*")))
        report = json.dumps(result)
        for secret in (str(self.root), str(TICKS), str(PID), "fictional-input",
                       "FICTIONAL_MOVIE_ONLY"):
            self.assertNotIn(secret, report)

    def test_same_frame_witness_is_allowed_not_game_proof(self):
        (self.first / AUTO_WITNESS_NAME).write_bytes(witness_bytes(frame=3001))
        result = self.review()
        self.assertTrue(result["auto_core_frame_not_later_than_first_png"])
        self.assertFalse(result["authentic_map02_scene_identified"])

    def test_future_frame_rejected(self):
        (self.first / AUTO_WITNESS_NAME).write_bytes(witness_bytes(frame=3002))
        with self.assertRaisesRegex(ValueError, "later than first PNG"):
            self.review()

    def test_missing_or_wrong_process_receipt_rejected(self):
        target = self.first / START_NAME
        for payload in (launch_bytes(pid=42), launch_bytes(ticks=TICKS+1)):
            with self.subTest(payload=payload[:30]):
                target.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, "PID/birth"):
                    self.review()
        target.unlink()
        with self.assertRaises((OSError, ValueError)):
            self.review()

    def test_wrong_core_or_malformed_receipt_rejected(self):
        target = self.first / AUTO_WITNESS_NAME
        target.write_bytes(witness_bytes().replace(b"Octoshock", b"Nymashock"))
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            self.review()
        target.write_bytes(b"fake")
        with self.assertRaisesRegex(ValueError, "schema|LF"):
            self.review()

    def test_missing_auto_core_witness_rejected(self):
        (self.first / AUTO_WITNESS_NAME).unlink()
        with self.assertRaises((OSError, ValueError)):
            self.review()

    def test_manual_core_witness_allowed_only_with_manual_log_mode(self):
        manual_chain = dict(CHAIN, owner_log_reports_auto_core_witness_before_first_png=False)
        result = self.review(manual=self.fake, chain=manual_chain)
        self.assertFalse(result["owner_log_reports_automatic_witness_before_first_png"])
        self.assertFalse(result["auto_core_frame_not_later_than_first_png"])
        self.assertFalse(result["two_run_repeatability_audited"])

    def test_manual_witness_can_be_saved_after_first_png(self):
        manual_chain = dict(CHAIN, owner_log_reports_auto_core_witness_before_first_png=False)
        self.fake.write_bytes(witness_bytes(frame=4000))
        result = self.review(manual=self.fake, chain=manual_chain)
        self.assertTrue(result["private_octoshock_core_witness_matches_launched_pid_and_birth"])

    def test_mixed_automatic_and_manual_logs_rejected(self):
        for manual, value in ((self.fake, True), (None, False)):
            with self.subTest(manual=manual, value=value):
                with self.assertRaisesRegex(ValueError, "mode"):
                    self.review(
                        manual=manual,
                        chain=dict(CHAIN, owner_log_reports_auto_core_witness_before_first_png=value),
                    )

    def test_missing_invalid_or_false_audit_flags_rejected(self):
        for key in ("private_plan_rebuilt_from_direct_bk2",
                    "capture_logs_match_each_planned_input_and_counter",
                    "owner_launcher_reports_successful_process_exit",
                    "owner_log_reports_psx_core_fallback_disabled",
                    "all_png_crc_zlib_scanlines_pass"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    self.review(chain=dict(CHAIN, **{key: False}))
        for count in (0, 2, True, "3"):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "incomplete"):
                    self.review(chain=dict(CHAIN, screenshot_count=count))

    def test_no_second_run_folder_allowed(self):
        second = self.workspace / RUN_NAMES[1]
        second.mkdir(mode=0o700)
        second.chmod(0o700)
        with self.assertRaisesRegex(ValueError, "two-run"):
            self.review()

    def test_no_second_run_symlink_allowed(self):
        second = self.workspace / RUN_NAMES[1]
        try:
            second.symlink_to(self.first, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "two-run"):
            self.review()

    def test_private_plan_symlink_rejected(self):
        self.plan.unlink()
        try:
            self.plan.symlink_to(self.fake)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "regular workspace"):
            self.review()

    def test_git_workspace_refused(self):
        (self.workspace / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            self.review()

    def test_missing_private_log_or_wrong_image_plan_detected_by_audit(self):
        with patch(
            "tools.map02_private_first_run_audit.verify",
            side_effect=ValueError("fictional missing PNG"),
        ), patch(
            "tools.map02_private_first_run_audit.parse_plan",
            return_value=("fake", ROWS),
        ):
            with self.assertRaisesRegex(ValueError, "fictional missing PNG"):
                review_first_capture(self.movie, self.workspace)

    def test_one_run_cli_outputs_only_redacted_fields(self):
        with patch.object(sys, "argv", [
            "owner-single-audit", str(self.movie), str(self.workspace),
        ]), patch(
            "tools.map02_private_first_run_audit.review_first_capture",
            return_value={
                "schema": "fictional", "capture_screenshot_count": 3,
                "two_run_repeatability_audited": False,
                "authentic_map02_scene_identified": False,
            },
        ) as reviewer, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(), 0)
        reviewer.assert_called_once_with(self.movie, self.workspace, None)
        serialized = out.getvalue()
        self.assertNotIn(str(self.root), serialized)
        self.assertFalse(json.loads(serialized)["authentic_map02_scene_identified"])

    def test_cli_error_never_discloses_input_path(self):
        with patch.object(sys, "argv", [
            "owner-single-audit", str(self.movie), str(self.workspace),
        ]), patch(
            "tools.map02_private_first_run_audit.review_first_capture",
            side_effect=ValueError("original private path is not readable"),
        ), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit):
                main()
        self.assertNotIn(str(self.root), err.getvalue())
        self.assertNotIn("original private path", err.getvalue())


if __name__ == "__main__":
    unittest.main()
