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
        self.track = self.root / "fictional.bin"
        self.bk2 = self.root / "fictional.bk2"
        self.plan = self.root / "private-plan.txt"
        self.lua = self.root / "capture.lua"
        self.output = self.root / "private-png"
        self.output.mkdir()
        self.output.chmod(0o700)
        for path in (self.program, self.track, self.bk2, self.lua):
            path.write_bytes(b"synthetic only")
        self.disc.write_text(
            'FILE "fictional.bin" BINARY\nTRACK 01 MODE2/2352\nINDEX 01 00:00:00\n',
            encoding="ascii",
        )
        self.plan.write_text("\n".join(ROWS) + "\n", encoding="ascii")

    def call(self, **kwargs):
        program = kwargs.pop("program", self.program)
        disc = kwargs.pop("disc", self.disc)
        movie = kwargs.pop("movie", self.bk2)
        plan = kwargs.pop("plan", self.plan)
        output = kwargs.pop("output", self.output)
        lua = kwargs.pop("lua", self.lua)
        rows = kwargs.pop("source_rows", ROWS)
        with patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=rows,
        ) as source, patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ) as media:
            result = build_launch(
                program, disc, movie, plan, output, script=lua,
                minimum=kwargs.pop("minimum", 180),
                maximum=kwargs.pop("maximum", 1800),
                after=kwargs.pop("after", 1663),
                before=kwargs.pop("before", 933949),
                auto_core_witness_plugin=kwargs.pop("auto_core_witness_plugin", None),
            )
        self.assertFalse(kwargs)
        self.assertEqual(source.call_args.kwargs["limit"], 1)
        self.assertEqual(media.call_count, 1)
        self.assertEqual(media.call_args.args, (Path(disc).resolve(), Path(movie).resolve()))
        return result

    def test_exact_bizhawk_argv_and_environment_without_shell(self):
        argv, env, count = self.call()
        self.assertEqual(count, 3)
        self.assertEqual(argv, [
            str(self.program.resolve()), "--movie=" + str(self.bk2.resolve()),
            "--lua=" + str(self.lua.resolve()), str(self.disc.resolve()),
        ])
        self.assertEqual(env["VH_PRIVATE_CAPTURE_PLAN"], str(self.plan.resolve()))
        self.assertEqual(env["VH_PRIVATE_EXPECTED_MOVIE"], str(self.bk2.resolve()))
        self.assertEqual(env["VH_PRIVATE_PNG_DIR"], str(self.output.resolve()))
        self.assertEqual(env["VH_PRIVATE_CAPTURE_LOG"],
                         str((self.output / "vh_private_capture.log").resolve()))
        self.assertEqual(env["VH_PRIVATE_PROCESS_LOG"],
                         str((self.output / "vh_emuhawk_process.log").resolve()))
        self.assertNotIn("github", str(argv).lower())

    def test_refuses_cue_with_missing_track_file(self):
        self.track.unlink()
        with self.assertRaisesRegex(ValueError, "CUE track file is missing"):
            self.call()

    def test_refuses_cue_track_path_escape(self):
        self.disc.write_text(
            'FILE "../outside.bin" BINARY\nTRACK 01 MODE2/2352\nINDEX 01 00:00:00\n',
            encoding="ascii",
        )
        with self.assertRaisesRegex(ValueError, "remain under descriptor directory"):
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

    def test_optional_private_full_disc_digest_is_passed_to_media_gate(self):
        digest = "a" * 64  # invented checksum, not a game-file hash
        reference = self.root / "owner-only.sha256"
        reference.write_text(digest + "\n", encoding="ascii")
        reference.chmod(0o600)
        with patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ) as media, patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=ROWS,
        ):
            _, _, count = build_launch(
                self.program, self.disc, self.bk2, self.plan, self.output,
                script=self.lua,
                private_full_bin_sha256_file=reference,
            )
        self.assertEqual(count, 3)
        media.assert_called_once_with(
            self.disc.resolve(), self.bk2.resolve(),
            verify_full_bin_sha256=True, expected_bin_sha256=digest,
        )

    def test_private_full_disc_digest_mismatch_blocks_launch(self):
        reference = self.root / "owner-only.sha256"
        reference.write_text("b" * 64 + "\n", encoding="ascii")
        reference.chmod(0o600)
        with patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": False},
        ) as media, patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
        ) as planner:
            with self.assertRaisesRegex(ValueError, "disc/movie media preflight"):
                build_launch(
                    self.program, self.disc, self.bk2, self.plan, self.output,
                    script=self.lua,
                    private_full_bin_sha256_file=reference,
                )
        media.assert_called_once()
        planner.assert_not_called()

    def test_disc_movie_profile_mismatch_blocks_plan_and_launch(self):
        with patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": False},
        ) as media, patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines"
        ) as planner:
            with self.assertRaisesRegex(ValueError, "disc/movie media preflight"):
                build_launch(
                    self.program, self.disc, self.bk2, self.plan, self.output,
                    script=self.lua,
                )
        media.assert_called_once_with(self.disc.resolve(), self.bk2.resolve())
        planner.assert_not_called()

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
                       return_value=ROWS), patch(
                    "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
                    return_value={"media_preflight_ready_for_owner_replay": True},
                ):
                with patch("tools.map02_private_bizhawk_poweron_launch.run_owned_process") as run:
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
                       return_value=ROWS), patch(
                    "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
                    return_value={"media_preflight_ready_for_owner_replay": True},
                ):
                with patch("tools.map02_private_bizhawk_poweron_launch.run_owned_process",
                           return_value=Mock(returncode=0)) as run:
                    stream = io.StringIO()
                    with contextlib.redirect_stdout(stream):
                        status = main()
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)
        c = run.call_args
        self.assertEqual(c.kwargs["timeout"], 28800)
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
        self.assertIn("original_ps1_authenticated=0", stream.getvalue())
        self.assertNotIn(str(self.bk2.resolve()), stream.getvalue())

    def test_custom_local_emulator_timeout_is_enforced(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()),
            str(self.bk2.resolve()), str(self.plan.resolve()),
            str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--emulator-timeout-seconds", "7200", "--launch",
        ]
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=ROWS,
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process",
            return_value=Mock(returncode=0),
        ) as runner:
            with contextlib.redirect_stdout(io.StringIO()):
                status = main()
        self.assertEqual(status, 0)
        self.assertEqual(runner.call_args.kwargs["timeout"], 7200)

    def test_invalid_emulator_timeout_rejected_without_launch_or_files(self):
        for invalid in ("0", "299", "86401", "-10"):
            with self.subTest(timeout=invalid):
                args = [
                    "program", str(self.program.resolve()),
                    str(self.disc.resolve()), str(self.bk2.resolve()),
                    str(self.plan.resolve()), str(self.output.resolve()),
                    "--emulator-timeout-seconds", invalid, "--launch",
                ]
                with patch.object(sys, "argv", args), patch(
                    "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
                ) as inspect, patch(
                    "tools.map02_private_bizhawk_poweron_launch.run_owned_process",
                ) as runner, contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main()
                self.assertNotEqual(error.exception.code, 0)
                inspect.assert_not_called()
                runner.assert_not_called()
                self.assertFalse((self.output / "vh_private_capture.log").exists())

    def test_emulator_timeout_refuses_to_claim_success_or_leak_paths(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()),
            str(self.bk2.resolve()), str(self.plan.resolve()),
            str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--emulator-timeout-seconds", "500", "--launch",
        ]
        timeout_error = subprocess.TimeoutExpired(
            cmd=[str(self.program.resolve()), "--movie=" + str(self.bk2.resolve())],
            timeout=500,
        )
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=ROWS,
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process",
            side_effect=timeout_error,
        ) as runner:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main()
        self.assertEqual(status, 1)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["timeout"], 500)
        audit = (self.output / "vh_private_capture.log").read_text(encoding="ascii")
        self.assertIn("VH_PRIVATE_BIZHAWK_LAUNCH_ERROR process_started=1 reason=emulator_timeout", audit)
        self.assertNotIn("exit_success=1", audit)
        self.assertNotIn(str(self.bk2.resolve()), stdout.getvalue())
        self.assertNotIn(str(self.disc.resolve()), audit)
        process_log = self.output / "vh_emuhawk_process.log"
        self.assertTrue(process_log.exists())
        self.assertEqual(process_log.stat().st_mode & 0o777, 0o600)

    def test_emuhawk_start_failure_is_logged_without_private_paths(self):
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()), str(self.bk2.resolve()),
            str(self.plan.resolve()), str(self.output.resolve()), "--capture-lua", str(self.lua.resolve()),
            "--launch",
        ]
        with patch.object(sys, "argv", args):
            with patch("tools.map02_private_bizhawk_poweron_launch.plan_lines",
                       return_value=ROWS), patch(
                    "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
                    return_value={"media_preflight_ready_for_owner_replay": True},
                ):
                with patch("tools.map02_private_bizhawk_poweron_launch.run_owned_process",
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
                       return_value=ROWS), patch(
                    "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
                    return_value={"media_preflight_ready_for_owner_replay": True},
                ):
                with patch("tools.map02_private_bizhawk_poweron_launch.run_owned_process",
                           return_value=Mock(returncode=9)):
                    with contextlib.redirect_stdout(io.StringIO()):
                        status = main()
        self.assertEqual(status, 1)

    def test_process_receipt_option_rejects_posix_execution_before_process(self):
        if os.name == "nt":
            self.skipTest("this guard exists only on non-Windows platforms")
        args = [
            "program", str(self.program.resolve()), str(self.disc.resolve()),
            str(self.bk2.resolve()), str(self.plan.resolve()),
            str(self.output.resolve()), "--capture-lua",
            str(self.lua.resolve()), "--record-process-identity", "--launch",
        ]
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=ROWS,
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process",
        ) as process:
            with self.assertRaises(SystemExit):
                main()
        process.assert_not_called()
        self.assertFalse((self.output / "vh_emuhawk_process_identity.txt").exists())


    # Stage509: invented plugin DLLs and witness receipts only; no PS1 media.
    def make_auto_plugin(self):
        folder = self.root / "ExternalTools"
        folder.mkdir(exist_ok=True)
        plugin = folder / "VhMap02CoreWitness.dll"
        plugin.write_bytes(b"fictional external DLL placeholder")
        return plugin

    def test_autowrite_optin_adds_only_installed_plugin_and_child_private_env(self):
        plugin = self.make_auto_plugin()
        argv, env, count = self.call(auto_core_witness_plugin=plugin)
        self.assertEqual(count, 3)
        self.assertEqual(argv[-2], "--open-ext-tool-dll=VhMap02CoreWitness.dll")
        self.assertEqual(argv[-1], str(self.disc.resolve()))
        self.assertEqual(env["VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR"],
                         str(self.output.resolve()))
        self.assertNotIn(str(plugin), " ".join(argv))

    def test_ambient_auto_env_cannot_enable_writes_without_flag(self):
        with patch.dict(os.environ, {
            "VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR": str(self.output)
        }):
            argv, env, count = self.call()
        self.assertNotIn("VH_MAP02_CORE_AUTOWRITE_PRIVATE_DIR", env)
        self.assertNotIn("--open-ext-tool-dll", " ".join(argv))

    def test_refuse_auto_plugin_from_unrelated_directory(self):
        plugin = self.root / "wrong" / "VhMap02CoreWitness.dll"
        plugin.parent.mkdir()
        plugin.write_bytes(b"fictional")
        with self.assertRaisesRegex(ValueError, "matching installed"):
            self.call(auto_core_witness_plugin=plugin)

    def test_refuse_renamed_auto_plugin(self):
        plugin = self.root / "ExternalTools" / "unsafe.dll"
        plugin.parent.mkdir()
        plugin.write_bytes(b"fictional")
        with self.assertRaisesRegex(ValueError, "matching installed"):
            self.call(auto_core_witness_plugin=plugin)

    def test_refuse_symlinked_auto_plugin(self):
        original = self.root / "test.dll"
        original.write_bytes(b"fictional")
        target = self.root / "ExternalTools" / "VhMap02CoreWitness.dll"
        target.parent.mkdir()
        target.symlink_to(original)
        with self.assertRaisesRegex(ValueError, "matching installed"):
            self.call(auto_core_witness_plugin=target)

    def test_refuse_preexisting_auto_witness(self):
        plugin = self.make_auto_plugin()
        destination = self.output / "vh-map02-runtime-core-auto.txt"
        destination.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.call(auto_core_witness_plugin=plugin)
        self.assertEqual(destination.read_bytes(), b"do not overwrite")

    def test_direct_cli_refuses_auto_without_kernel_pid_receipt(self):
        plugin = self.make_auto_plugin()
        args = ["launcher", str(self.program), str(self.disc), str(self.bk2),
                str(self.plan), str(self.output), "--capture-lua", str(self.lua),
                "--auto-core-witness-plugin", str(plugin), "--launch"]
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process"
        ) as runner:
            with self.assertRaises(SystemExit):
                main()
            runner.assert_not_called()

    def test_direct_cli_optin_preflight_never_creates_receipts_or_runs(self):
        plugin = self.make_auto_plugin()
        args = ["launcher", str(self.program), str(self.disc), str(self.bk2),
                str(self.plan), str(self.output), "--capture-lua", str(self.lua),
                "--auto-core-witness-plugin", str(plugin),
                "--record-process-identity"]
        with patch.object(sys, "argv", args), patch(
            "tools.map02_private_bizhawk_poweron_launch.plan_lines",
            return_value=ROWS,
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_bizhawk_poweron_launch.run_owned_process"
        ) as runner, contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main(), 0)
        runner.assert_not_called()
        self.assertFalse((self.output / "vh-map02-runtime-core-auto.txt").exists())
        self.assertFalse((self.output / "vh_emuhawk_process_identity.txt").exists())
        self.assertIn("emulator_started=0", stream.getvalue())

    def test_local_auto_witness_requires_matching_pid_and_birth(self):
        from tools.map02_private_bizhawk_poweron_launch import verify_private_auto_witness
        from tools.map02_private_process_witness_binding import MAGIC
        pid, birth = 3030, 639000000000000001
        (self.output / "vh_emuhawk_process_identity.txt").write_bytes(
            (f"{MAGIC}\nprocess_id={pid}\n"
             f"process_start_utc_ticks={birth}\n").encode("ascii"))
        witness = self.output / "vh-map02-runtime-core-auto.txt"
        def core(when):
            return (
                "VH_MAP02_RUNTIME_CORE_WITNESS_V1\nsystem=PSX\n"
                "loaded_core=Octoshock\n"
                "core_source=IEmulator.Attributes.CoreName\n"
                f"process_id={pid}\nprocess_start_utc_ticks={when}\n"
                "frame_count=1666\nbios=unverified\ndisc=unverified\n"
                "movie_sync=unverified\n"
            ).encode("ascii")
        with self.assertRaises((OSError, ValueError)):
            verify_private_auto_witness(self.output)
        witness.write_bytes(core(birth + 1))
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_private_auto_witness(self.output)
        witness.write_bytes(core(birth))
        self.assertIsNone(verify_private_auto_witness(self.output))
        witness.write_bytes(core(birth).replace(b"Octoshock", b"Nymashock"))
        with self.assertRaisesRegex(ValueError, "unsupported evidence"):
            verify_private_auto_witness(self.output)



if __name__ == "__main__":
    unittest.main()
