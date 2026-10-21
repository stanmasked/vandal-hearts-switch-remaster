"""Invented-only BizHawk CLI launch preflight and privacy tests."""
import contextlib
import io
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock

from tools.map02_private_bizhawk_poweron_launch import build_launch, main


ROWS = [
    "VH_MAP02_CAPTURE_PLAN_V1", "movie_frames=933949",
    "capture_count=3", "1,before,3000,held",
    "1,middle,3250,neutral", "1,after,3500,held",
]


class PrivateBizHawkBootTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.program = self.root / "EmuHawk.exe"
        self.disc = self.root / "fictional.cue"
        self.bk2 = self.root / "fictional.bk2"
        self.plan = self.root / "private-plan.txt"
        self.lua = self.root / "capture.lua"
        self.output = self.root / "private-png"
        self.output.mkdir()
        self.output.chmod(0o700)
        for path in (self.program, self.disc, self.bk2, self.lua):
            path.write_bytes(b"synthetic only")
        self.plan.write_text("\n".join(ROWS) + "\n", encoding="ascii")

    def call(self, **kwargs):
        with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                   return_value=kwargs.pop("source_rows", ROWS)) as source:
            result = build_launch(
                kwargs.pop("program", self.program),
                kwargs.pop("disc", self.disc),
                kwargs.pop("movie", self.bk2),
                kwargs.pop("plan", self.plan),
                kwargs.pop("output", self.output),
                script=kwargs.pop("lua", self.lua),
                minimum=kwargs.pop("minimum", 180),
                maximum=kwargs.pop("maximum", 1800),
                after=kwargs.pop("after", 1663),
                before=kwargs.pop("before", 933949),
            )
        self.assertFalse(kwargs)
        self.assertEqual(source.call_args.kwargs["limit"], 1)
        return result

    def test_exact_bizhawk_argv_and_environment_without_shell(self):
        argv, env, count = self.call()
        self.assertEqual(count, 3)
        self.assertEqual(argv, [
            str(self.program.resolve()), "--movie=" + str(self.bk2.resolve()),
            "--lua=" + str(self.lua.resolve()), str(self.disc.resolve()),
        ])
        self.assertEqual(env["VH_PRIVATE_CAPTURE_PLAN"], str(self.plan.resolve()))
        self.assertEqual(env["VH_PRIVATE_PNG_DIR"], str(self.output.resolve()))
        self.assertEqual(env["VH_PRIVATE_CAPTURE_LOG"],
                         str((self.output / "vh_private_capture.log").resolve()))
        self.assertEqual(env["VH_PRIVATE_PROCESS_LOG"],
                         str((self.output / "vh_emuhawk_process.log").resolve()))
        self.assertNotIn("github", str(argv).lower())

    def test_owner_original_files_must_not_reside_in_git_checkout(self):
        (self.root / ".git").mkdir()
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_private_movie_symlink(self):
        other = self.root / "shortcut.bk2"
        other.symlink_to(self.bk2)
        with self.assertRaises(ValueError):
            self.call(movie=other)

    def test_refuses_missing_private_disc(self):
        with self.assertRaises(ValueError):
            self.call(disc=self.root / "missing.cue")

    def test_refuses_wrong_bk2_to_plan_relationship(self):
        rows = ROWS[:-1] + ["1,after,3502,held"]
        with self.assertRaises(ValueError):
            self.call(source_rows=rows)

    def test_refuses_existing_capture_log(self):
        (self.output / "vh_private_capture.log").write_text("keep", encoding="ascii")
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_symlink_capture_log(self):
        victim = self.root / "victim.log"
        victim.write_text("keep", encoding="ascii")
        (self.output / "vh_private_capture.log").symlink_to(victim)
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_existing_emuhawk_process_log(self):
        (self.output / "vh_emuhawk_process.log").write_text("keep", encoding="ascii")
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_symlink_emuhawk_process_log(self):
        victim = self.root / "process-victim.log"
        victim.write_text("keep", encoding="ascii")
        (self.output / "vh_emuhawk_process.log").symlink_to(victim)
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_group_or_world_accessible_png_root(self):
        if os.name == "nt":
            self.skipTest("POSIX directory mode bits are not Windows ACLs")
        self.output.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.call()

    def test_refuses_png_root_owned_by_another_user(self):
        if os.name == "nt":
            self.skipTest("POSIX uid ownership is unavailable on Windows")
        with patch("tools.map02_private_bizhawk_poweron_launch.os.geteuid",
                   return_value=self.output.stat().st_uid + 1):
            with self.assertRaisesRegex(ValueError, "owned by current user"):
                self.call()

    def test_refuses_already_existing_screenshot_output(self):
        (self.output / "vh_review_w01_middle_counter_0003251.png").write_bytes(b"old")
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_symlinked_screenshot_output(self):
        actual = self.root / "real-image-dir"
        actual.mkdir()
        self.output.rmdir()
        self.output.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.call()

    def test_refuses_git_inside_resolved_parent_symlink(self):
        actual = self.root / "real"
        actual.mkdir()
        (actual / ".git").write_text("gitdir: elsewhere", encoding="ascii")
        image = actual / "images"
        image.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.call(output=alias / "images")

    def test_refuses_relative_executable_path(self):
        with self.assertRaises(ValueError):
            self.call(program=Path("EmuHawk.exe"))

    def test_refuses_nonexistent_lua_script(self):
        with self.assertRaises(ValueError):
            self.call(lua=self.root / "missing.lua")

    def test_plan_scan_arguments_preserve_movie_clock_bounds(self):
        args, env, count = self.call(
            minimum=240, maximum=1200, after=2000, before=900000)
        self.assertEqual(args[1], "--movie=" + str(self.bk2.resolve()))
        self.assertEqual(count, 3)

    def test_cli_preflight_never_executes_or_echoes_private_paths(self):
        command = [
            "program", str(self.program.resolve()), str(self.disc.resolve()), str(self.bk2.resolve()),
            str(self.plan.resolve()), str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
        ]
        with patch.object(sys, "argv", command):
            with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                       return_value=ROWS):
                with patch("tools.map02_private_bizhawk_poweron_launch.subprocess.run") as run:
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        result = main()
        self.assertEqual(result, 0)
        run.assert_not_called()
        self.assertIn("emulator_started=0", stream.getvalue())
        self.assertFalse((self.output / "vh_private_capture.log").exists())
        self.assertFalse((self.output / "vh_emuhawk_process.log").exists())
        for private in (self.bk2, self.disc, self.plan, self.output):
            self.assertNotIn(str(private), stream.getvalue())

    def test_explicit_launch_uses_argv_without_shell_or_upload(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()), str(self.bk2.resolve()),
            str(self.plan.resolve()), str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--launch",
        ]
        with patch.object(sys, "argv", args):
            with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                       return_value=ROWS):
                with patch("tools.map02_private_bizhawk_poweron_launch.subprocess.run",
                           return_value=Mock(returncode=0)) as run:
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        status = main()
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)
        c = run.call_args
        self.assertFalse(c.kwargs["shell"])
        self.assertEqual(c.args[0][1], "--movie=" + str(self.bk2.resolve()))
        self.assertEqual(c.args[0][2], "--lua=" + str(self.lua.resolve()))
        self.assertEqual(c.kwargs["env"]["VH_PRIVATE_CAPTURE_PLAN"], str(self.plan.resolve()))
        self.assertEqual(c.kwargs["env"]["VH_PRIVATE_CAPTURE_LOG"],
                         str((self.output / "vh_private_capture.log").resolve()))
        logfile = self.output / "vh_private_capture.log"
        self.assertTrue(logfile.is_file())
        self.assertEqual(logfile.stat().st_mode & 0o777, 0o600)
        self.assertIn("exit_success=1", logfile.read_text(encoding="ascii"))
        process_log = self.output / "vh_emuhawk_process.log"
        self.assertTrue(process_log.is_file())
        self.assertEqual(process_log.stat().st_mode & 0o777, 0o600)
        self.assertIsNotNone(c.kwargs["stdout"])
        self.assertIs(c.kwargs["stderr"], subprocess.STDOUT)
        self.assertIn("original_ps1_authenticated=0", stream.getvalue())
        self.assertNotIn(str(self.bk2.resolve()), stream.getvalue())

    def test_emuhawk_start_failure_is_logged_without_private_paths(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()), str(self.bk2.resolve()),
            str(self.plan.resolve()), str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--launch",
        ]
        with patch.object(sys, "argv", args):
            with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                       return_value=ROWS):
                with patch("tools.map02_private_bizhawk_poweron_launch.subprocess.run",
                           side_effect=OSError("synthetic executable failure")):
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        status = main()
        self.assertEqual(status, 1)
        logfile = self.output / "vh_private_capture.log"
        self.assertIn("VH_PRIVATE_BIZHAWK_LAUNCH_ERROR process_started=0",
                      logfile.read_text(encoding="ascii"))
        self.assertNotIn(str(self.bk2.resolve()), stream.getvalue())

    def test_nonzero_emulator_exit_is_not_reported_successful(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()), str(self.bk2.resolve()),
            str(self.plan.resolve()), str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--launch",
        ]
        with patch.object(sys, "argv", args):
            with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                       return_value=ROWS):
                with patch("tools.map02_private_bizhawk_poweron_launch.subprocess.run",
                           return_value=Mock(returncode=9)):
                    with contextlib.redirect_stdout(io.StringIO()):
                        status = main()
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
