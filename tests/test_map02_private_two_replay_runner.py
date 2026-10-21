"""Synthetic owner-local two-emulator-run coordination checks (no game)."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.map02_private_two_replay_runner import (
    PLAN_NAME, RUN_NAMES, capture_twice, main,
)


PAIR_OK = {
    "screenshot_pairs_checked": 3,
    "decoded_pixel_equal_pairs": 3,
    "decoded_pixel_different_pairs": 0,
    "decoded_pixel_unsupported_pairs": 0,
    "all_supported_png_pixel_content_equal": True,
}


class PrivateTwoReplayRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / "owner-workspace"
        self.workspace.mkdir(mode=0o700)
        self.workspace.chmod(0o700)
        self.program = self.root / "fictional-emulator"
        self.disc = self.root / "fictional.cue"
        self.movie = self.root / "fictional.bk2"
        for path in (self.program, self.disc, self.movie):
            path.write_text("synthetic-only")
        self.args = (self.program, self.disc, self.movie, self.workspace)

    def run_mocked(self, *, processes=None, match=True, digest=None):
        subprocess_mock = (processes if processes is not None else [
            Mock(returncode=0), Mock(returncode=0),
        ])
        pair = dict(PAIR_OK)
        pair["all_supported_png_pixel_content_equal"] = match
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ) as media, patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ) as planning, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=subprocess_mock,
        ) as process, patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count": 3},
        ) as chain, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
            return_value=pair,
        ) as comparison:
            if digest is None:
                report = capture_twice(*self.args, start=True)
            else:
                with patch(
                    "tools.map02_private_two_replay_runner.read_private_full_bin_sha256",
                    return_value="a" * 64,
                ) as reference:
                    report = capture_twice(
                        *self.args, start=True, expected_digest_file=digest,
                    )
                    reference.assert_called_once_with(digest)
        return report, media, planning, process, chain, comparison

    def _write_plan(self, movie, path, **kwargs):
        Path(path).write_text("synthetic-only-plan", encoding="ascii")
        self.assertEqual(movie, self.movie)
        self.assertEqual(kwargs["limit"], 4)
        return 3

    def test_default_validates_real_media_and_plan_without_outputs(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ) as media, patch(
            "tools.map02_private_two_replay_runner.plan_lines",
            return_value=["fictional-header", "fictional-length",
                          "fictional-count", "frame1", "frame2", "frame3"],
        ) as plan, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as process, patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
        ) as writer:
            report = capture_twice(*self.args)
        media.assert_called_once()
        plan.assert_called_once_with(self.movie, limit=4)
        process.assert_not_called()
        writer.assert_not_called()
        self.assertTrue(report["media_preflight_passed"])
        self.assertEqual(report["private_capture_plan_rows_checked"], 3)
        self.assertFalse(report["full_bin_sha256_checked"])
        self.assertEqual(report["emulator_processes_started"], 0)
        self.assertFalse((self.workspace / PLAN_NAME).exists())

    def test_dry_run_rejects_media_mismatch_without_outputs(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": False},
        ) as media, patch(
            "tools.map02_private_two_replay_runner.plan_lines",
        ) as plan, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as process:
            with self.assertRaisesRegex(ValueError, "media preflight failed"):
                capture_twice(*self.args)
        media.assert_called_once()
        plan.assert_not_called()
        process.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_dry_run_rejects_invalid_movie_plan_without_outputs(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.plan_lines",
            side_effect=ValueError("no suitable movie windows"),
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as process:
            with self.assertRaisesRegex(ValueError, "no suitable movie windows"):
                capture_twice(*self.args)
        process.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_dry_run_rejects_missing_emulator_before_reading_movie(self):
        self.program.unlink()
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
        ) as media:
            with self.assertRaisesRegex(ValueError, "absolute EmuHawk executable"):
                capture_twice(*self.args)
        media.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_dry_run_checks_private_reference_when_requested(self):
        private_ref = self.root / "fictional-private-digest.sha256"
        private_ref.write_text("f" * 64, encoding="ascii")
        with patch(
            "tools.map02_private_two_replay_runner.read_private_full_bin_sha256",
            return_value="f" * 64,
        ) as loader, patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ) as media, patch(
            "tools.map02_private_two_replay_runner.plan_lines",
            return_value=["h", "l", "c", "a", "b", "c"],
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as process:
            report = capture_twice(
                *self.args, expected_digest_file=private_ref,
            )
        loader.assert_called_once_with(private_ref)
        media.assert_called_once_with(
            self.disc, self.movie,
            verify_full_bin_sha256=True, expected_bin_sha256="f" * 64,
        )
        self.assertTrue(report["full_bin_sha256_checked"])
        process.assert_not_called()

    def test_two_separate_emulator_subprocesses_and_independent_audits(self):
        result, media, planning, process, chain, paired = self.run_mocked()
        self.assertTrue(result["all_supported_png_pixel_content_equal"])
        self.assertEqual(result["emulator_processes_started"], 2)
        self.assertEqual(result["capture_attempts_audited"], 2)
        self.assertFalse(result["independent_cold_boots_authenticated"])
        self.assertFalse(result["original_map02_scene_authenticated"])
        self.assertEqual(media.call_count, 1)
        self.assertEqual(planning.call_count, 1)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(chain.call_count, 2)
        paired.assert_called_once()
        for index, process_call in enumerate(process.call_args_list):
            argv = process_call.args[0]
            self.assertEqual(argv[:3], [
                sys.executable, "-m", "tools.map02_private_bizhawk_poweron_launch",
            ])
            self.assertEqual(argv[-1], "--launch")
            # macOS aliases /var to /private/var; compare canonical roots.
            self.assertEqual(
                Path(argv[-2]).resolve(strict=True),
                (self.workspace / RUN_NAMES[index]).resolve(strict=True),
            )
            self.assertFalse(process_call.kwargs["shell"])
            self.assertIs(process_call.kwargs["stdout"], subprocess.DEVNULL)
            self.assertIs(process_call.kwargs["stderr"], subprocess.DEVNULL)
            path = self.workspace / RUN_NAMES[index]
            self.assertTrue(path.is_dir())
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertNotEqual(
            process.call_args_list[0].args[0][-2],
            process.call_args_list[1].args[0][-2],
        )

    def test_first_process_failure_stops_before_second(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            return_value=Mock(returncode=13),
        ) as process, patch(
            "tools.map02_private_two_replay_runner.verify",
        ) as verifier:
            with self.assertRaisesRegex(ValueError, "capture process failed"):
                capture_twice(*self.args, start=True)
        process.assert_called_once()
        verifier.assert_not_called()
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_first_incomplete_capture_blocks_second_process(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            return_value=Mock(returncode=0),
        ) as process, patch(
            "tools.map02_private_two_replay_runner.verify",
            side_effect=ValueError("invented Lua incomplete"),
        ):
            with self.assertRaisesRegex(ValueError, "Lua incomplete"):
                capture_twice(*self.args, start=True)
        process.assert_called_once()
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_requested_private_digest_is_used_before_both_runs(self):
        digest_file = self.root / "fictional.sha256"
        digest_file.write_text("a" * 64)
        report, media, _, process, _, _ = self.run_mocked(digest=digest_file)
        media.assert_called_once_with(
            self.disc, self.movie,
            verify_full_bin_sha256=True, expected_bin_sha256="a" * 64,
        )
        for item in process.call_args_list:
            argv = item.args[0]
            self.assertEqual(
                argv[-3:],
                ["--private-full-bin-sha256-file", str(digest_file), "--launch"],
            )
        self.assertFalse(report["owner_private_assets_uploaded"])

    def test_media_mismatch_rejected_before_any_private_outputs(self):
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": False},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
        ) as writing, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as launching:
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                capture_twice(*self.args, start=True)
        writing.assert_not_called()
        launching.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_preexisting_first_run_refused_without_overwrite(self):
        (self.workspace / RUN_NAMES[0]).mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            capture_twice(*self.args, start=True)

    def test_git_root_refused(self):
        (self.root / ".git").mkdir()
        with self.assertRaisesRegex(ValueError, "outside Git"):
            capture_twice(*self.args, start=True)

    def test_world_readable_workspace_refused(self):
        if os.name == "nt":
            self.skipTest("Windows ACL not covered by POSIX permissions")
        self.workspace.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            capture_twice(*self.args, start=True)

    def test_reject_invalid_number_of_windows(self):
        with self.assertRaisesRegex(ValueError, "1..10"):
            capture_twice(*self.args, max_windows=0)

    def test_main_no_optin_prints_redacted_validated_no_launch(self):
        command = ["test", *(str(item) for item in self.args)]
        with patch.object(sys, "argv", command), patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.plan_lines",
            return_value=["h", "l", "c", "a", "b", "c"],
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as process:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main()
        self.assertEqual(result, 0)
        self.assertIn('"media_preflight_passed": true', output.getvalue())
        self.assertIn('"emulator_processes_started": 0', output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        process.assert_not_called()

    def test_review_mismatch_is_not_reported_as_success(self):
        report, *_ = self.run_mocked(match=False)
        self.assertFalse(report["all_supported_png_pixel_content_equal"])


if __name__ == "__main__":
    unittest.main()
