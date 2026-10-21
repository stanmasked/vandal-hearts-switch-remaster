"""Synthetic owner-local two-emulator-run coordination checks (no game)."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.map02_private_two_replay_runner import (
    PLAN_NAME, RUN_NAMES, _disc_source_snapshot, _private_movie_identity,
    capture_twice, main, _require_full_bin_unchanged,
)
from tools.map02_private_disc_movie_preflight import (
    EXPECTED_BIN_BYTES, MAP02_LBA, SECTOR_BYTES,
)


PAIR_OK = {
    "screenshot_pairs_checked": 3,
    "same_reported_bizhawk_runtime_profile": True,
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
        self.bin = self.root / "fictional.bin"
        self.program.write_text("fictional-emulator-only")
        self.movie.write_text("synthetic-only")
        self.disc.write_text(
            'FILE "fictional.bin" BINARY\n'
            '  TRACK 01 MODE2/2352\n'
            '    INDEX 01 00:00:00\n',
            encoding="ascii",
        )
        # Sparse fiction, no original sectors, no 665 MB written to disk.
        with self.bin.open("wb") as handle:
            handle.truncate(EXPECTED_BIN_BYTES)
        self.args = (self.program, self.disc, self.movie, self.workspace)

    def run_mocked(self, *, processes=None, match=True, digest=None,
                   emulator_timeout_seconds=None):
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
                report = capture_twice(
                    *self.args, start=True,
                    emulator_timeout_seconds=emulator_timeout_seconds,
                )
            else:
                with patch(
                    "tools.map02_private_two_replay_runner.read_private_full_bin_sha256",
                    return_value="a" * 64,
                ) as reference, patch(
                    "tools.map02_private_two_replay_runner._full_image_sha256",
                    return_value="a" * 64,
                ) as complete_hash:
                    report = capture_twice(
                        *self.args, start=True, expected_digest_file=digest,
                        emulator_timeout_seconds=emulator_timeout_seconds,
                    )
                    self.assertGreaterEqual(reference.call_count, 2)
                    for call in reference.call_args_list:
                        self.assertEqual(call.args, (digest,))
                    self.assertEqual(complete_hash.call_count, 3)
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
        self.assertTrue(report["owner_bk2_stable_during_preflight"])
        self.assertTrue(report["disc_source_stable_during_preflight"])
        self.assertEqual(report["private_capture_plan_rows_checked"], 3)
        self.assertFalse(report["full_bin_sha256_checked"])
        self.assertEqual(report["emulator_timeout_seconds"], 28800)
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
        self.assertGreaterEqual(loader.call_count, 2)
        for call in loader.call_args_list:
            self.assertEqual(call.args, (private_ref,))
        media.assert_called_once_with(
            self.disc, self.movie,
            verify_full_bin_sha256=True, expected_bin_sha256="f" * 64,
        )
        self.assertTrue(report["full_bin_sha256_checked"])
        self.assertTrue(report["full_bin_reference_stable_during_preflight"])
        process.assert_not_called()

    def test_two_separate_emulator_subprocesses_and_independent_audits(self):
        result, media, planning, process, chain, paired = self.run_mocked()
        self.assertTrue(result["all_supported_png_pixel_content_equal"])
        self.assertEqual(result["emulator_processes_started"], 2)
        self.assertEqual(result["capture_attempts_audited"], 2)
        self.assertTrue(result["same_bk2_bytes_across_capture_attempts"])
        self.assertTrue(result["same_cue_and_sampled_bin_sectors_across_attempts"])
        self.assertFalse(result["full_disc_content_equality_authenticated"])
        self.assertEqual(result["full_bin_postprocess_checks_performed"], 0)
        self.assertFalse(result["full_bin_final_postaudit_check_performed"])
        self.assertFalse(result["on_disk_full_bin_matched_private_reference_at_checkpoints"])
        self.assertFalse(result["emulator_mounted_disc_identity_authenticated"])
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

    def test_custom_timeout_forwarded_to_both_emulator_processes(self):
        report, media, plan, process, chain, paired = self.run_mocked(
            emulator_timeout_seconds=9600,
        )
        self.assertEqual(report["emulator_timeout_seconds"], 9600)
        self.assertEqual(process.call_count, 2)
        for c in process.call_args_list:
            self.assertEqual(
                c.args[0][-3:],
                ["--emulator-timeout-seconds", "9600", "--launch"],
            )
            self.assertFalse(c.kwargs["shell"])

    def test_invalid_optional_timeout_rejected_before_private_processing(self):
        for bad in (0, 299, 86401, -1, True, "abc"):
            with self.subTest(seconds=bad), patch(
                "tools.map02_private_two_replay_runner.inspect_pair",
            ) as inspector, patch(
                "tools.map02_private_two_replay_runner.subprocess.run",
            ) as process:
                with self.assertRaisesRegex(ValueError, "timeout seconds"):
                    capture_twice(
                        *self.args, start=True, emulator_timeout_seconds=bad,
                    )
                inspector.assert_not_called()
                process.assert_not_called()
                self.assertEqual(list(self.workspace.iterdir()), [])

    def _private_reference(self):
        reference = self.root / "fictional-private-full-bin.sha256"
        reference.write_text("a" * 64, encoding="ascii")
        if os.name != "nt":
            reference.chmod(0o600)
        return reference

    def test_reference_mutated_during_preflight_blocks_planning(self):
        reference = self._private_reference()
        def swap_reference(*args, **kwargs):
            reference.write_text("b" * 64, encoding="ascii")
            return {"media_preflight_ready_for_owner_replay": True}
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            side_effect=swap_reference,
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
        ) as planning, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
        ) as launched:
            with self.assertRaisesRegex(ValueError, "digest reference changed"):
                capture_twice(*self.args, expected_digest_file=reference, start=True)
        planning.assert_not_called()
        launched.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_reference_mutated_during_first_process_blocks_second(self):
        reference = self._private_reference()
        def alter_reference(*args, **kwargs):
            reference.write_text("b" * 64, encoding="ascii")
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=alter_reference,
        ) as launched, patch(
            "tools.map02_private_two_replay_runner.verify",
        ) as auditing:
            with self.assertRaisesRegex(ValueError, "digest reference changed"):
                capture_twice(*self.args, expected_digest_file=reference, start=True)
        launched.assert_called_once()
        auditing.assert_not_called()
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_reference_mutated_during_second_process_blocks_comparison(self):
        reference = self._private_reference()
        attempts = [0]
        def alter_on_second(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 2:
                reference.write_text("b" * 64, encoding="ascii")
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=alter_on_second,
        ) as launched, patch(
            "tools.map02_private_two_replay_runner._full_image_sha256",
            return_value="a" * 64,
        ), patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count": 3},
        ) as auditing, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
        ) as comparison:
            with self.assertRaisesRegex(ValueError, "digest reference changed"):
                capture_twice(*self.args, expected_digest_file=reference, start=True)
        self.assertEqual(launched.call_count, 2)
        auditing.assert_called_once()
        comparison.assert_not_called()

    def test_disc_cue_mutated_during_first_process_blocks_second(self):
        def changed_cue(*args, **kwargs):
            self.disc.write_text(
                'FILE "fictional.bin" BINARY\n'
                'TRACK 01 MODE2/2352\n'
                'INDEX 01 00:00:00\n',
                encoding="ascii",
            )
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=changed_cue,
        ) as launched, patch(
            "tools.map02_private_two_replay_runner.verify",
        ) as audit:
            with self.assertRaisesRegex(ValueError, "disc source changed"):
                capture_twice(*self.args, start=True)
        launched.assert_called_once()
        audit.assert_not_called()
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_disc_sector_mutated_during_second_process_blocks_comparison(self):
        attempts = [0]
        def corrupt_sector(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 2:
                with self.bin.open("r+b") as media:
                    media.seek(MAP02_LBA * SECTOR_BYTES + 24)
                    media.write(b"NOTIGINAL")
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=corrupt_sector,
        ) as launched, patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count": 3},
        ) as audit, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
        ) as compare:
            with self.assertRaisesRegex(ValueError, "disc source changed"):
                capture_twice(*self.args, start=True)
        self.assertEqual(launched.call_count, 2)
        audit.assert_called_once()
        compare.assert_not_called()

    def test_disc_identity_same_files_stable_and_sample_sector_changes(self):
        before = _disc_source_snapshot(self.disc)
        self.assertEqual(before, _disc_source_snapshot(self.disc))
        with self.bin.open("r+b") as media:
            media.seek(MAP02_LBA * SECTOR_BYTES)
            media.write(b"fictional changed sector")
        self.assertNotEqual(before, _disc_source_snapshot(self.disc))

    def test_disc_identity_rejects_bin_symlink(self):
        target = self.root / "backup-fake.bin"
        self.bin.rename(target)
        try:
            self.bin.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported")
        with self.assertRaisesRegex(ValueError, "nonsymlink"):
            _disc_source_snapshot(self.disc)

    def test_disc_identity_does_not_attest_untouched_full_bin(self):
        # The source receipt intentionally probes only PVD and MAP02.
        # A change in a remote unprobed sector cannot be called whole-BIN
        # equality even though metadata (ctime) normally catches mutation.
        report, *_ = self.run_mocked()
        self.assertFalse(report["full_disc_content_equality_authenticated"])

    def test_movie_mutated_during_first_process_blocks_second(self):
        def first_capture(*args, **kwargs):
            self.movie.write_text("synthetic-only-but-now-modified")
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=first_capture,
        ) as launch, patch(
            "tools.map02_private_two_replay_runner.verify",
        ) as verifier, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
        ) as comparison:
            with self.assertRaisesRegex(ValueError, "BK2 changed between"):
                capture_twice(*self.args, start=True)
        launch.assert_called_once()
        verifier.assert_not_called()
        comparison.assert_not_called()
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_movie_mutated_during_second_process_blocks_comparison(self):
        attempts = [0]
        def captured_process(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 2:
                self.movie.write_bytes(b"synthetic-second-run-different")
            return Mock(returncode=0)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=captured_process,
        ) as launch, patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count": 3},
        ) as verifier, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
        ) as comparison:
            with self.assertRaisesRegex(ValueError, "BK2 changed between"):
                capture_twice(*self.args, start=True)
        self.assertEqual(launch.call_count, 2)
        verifier.assert_called_once()
        comparison.assert_not_called()

    def test_movie_identity_ignores_filename_but_not_bytes(self):
        another = self.root / "another-fictional.bk2"
        another.write_bytes(self.movie.read_bytes())
        self.assertEqual(
            _private_movie_identity(self.movie),
            _private_movie_identity(another),
        )
        another.write_bytes(b"changed")
        self.assertNotEqual(
            _private_movie_identity(self.movie),
            _private_movie_identity(another),
        )

    def test_movie_identity_rejects_symlink(self):
        mirror = self.root / "fictional-symlink.bk2"
        try:
            mirror.symlink_to(self.movie)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation not available")
        with self.assertRaises((OSError, ValueError)):
            _private_movie_identity(mirror)

    def test_movie_identity_rejects_oversized_file_before_full_read(self):
        oversized = self.root / "too-big-fictional.bk2"
        with oversized.open("wb") as handle:
            handle.truncate(8 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "bounded size"):
            _private_movie_identity(oversized)

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

    def test_full_bin_postcheck_detects_different_bytes_outside_map02(self):
        # Standalone helper with tiny invented bytes: no huge original image.
        payload = b"FICTIONAL_CD_IMAGE" * 8
        self.bin.write_bytes(payload)
        expected = hashlib.sha256(payload).hexdigest()
        with patch(
            "tools.map02_private_two_replay_runner.EXPECTED_BIN_BYTES",
            len(payload),
        ):
            _require_full_bin_unchanged(self.disc, expected)
            with self.bin.open("r+b") as handle:
                handle.seek(-1, os.SEEK_END)
                handle.write(b"!")
            with self.assertRaisesRegex(ValueError, "full BIN content changed"):
                _require_full_bin_unchanged(self.disc, expected)

    def test_no_private_reference_skips_full_image_postcheck(self):
        with patch(
            "tools.map02_private_two_replay_runner._full_image_sha256"
        ) as hashed:
            result, _, _, process, _, _ = self.run_mocked()
        self.assertEqual(process.call_count, 2)
        hashed.assert_not_called()
        self.assertEqual(result["full_bin_postprocess_checks_performed"], 0)
        self.assertFalse(result["on_disk_full_bin_matched_private_reference_at_checkpoints"])

    def _run_private_source_change(self, stage):
        """Fictional digest observes one unprobed last-byte mutation.

        Mock only the sector-snapshot gate: actual filesystem timestamps
        would already catch this mutation, but this isolates the *entire
        image* hashing check from that weaker sample.
        """
        reference = self._private_reference()
        subprocess_count = [0]
        def simulated_emulator(*args, **kwargs):
            subprocess_count[0] += 1
            if (stage == "first" and subprocess_count[0] == 1
                    or stage == "second" and subprocess_count[0] == 2):
                with self.bin.open("r+b") as handle:
                    handle.seek(-1, os.SEEK_END)
                    handle.write(b"!")
            return Mock(returncode=0)
        def fake_full_hash(fd, file_size):
            self.assertEqual(file_size, EXPECTED_BIN_BYTES)
            final_byte = os.pread(fd, 1, file_size - 1)
            return "a" * 64 if final_byte == b"\x00" else "b" * 64
        def simulated_comparison(*args, **kwargs):
            if stage == "final":
                with self.bin.open("r+b") as handle:
                    handle.seek(-1, os.SEEK_END)
                    handle.write(b"!")
            return dict(PAIR_OK)
        with patch(
            "tools.map02_private_two_replay_runner.inspect_pair",
            return_value={"media_preflight_ready_for_owner_replay": True},
        ), patch(
            "tools.map02_private_two_replay_runner.write_private_plan",
            side_effect=self._write_plan,
        ), patch(
            "tools.map02_private_two_replay_runner._require_disc_unchanged",
        ), patch(
            "tools.map02_private_two_replay_runner._full_image_sha256",
            side_effect=fake_full_hash,
        ) as full_hash, patch(
            "tools.map02_private_two_replay_runner.subprocess.run",
            side_effect=simulated_emulator,
        ) as launched, patch(
            "tools.map02_private_two_replay_runner.verify",
            return_value={"screenshot_count": 3},
        ) as chain, patch(
            "tools.map02_private_two_replay_runner.audit_pair",
            side_effect=simulated_comparison,
        ) as paired:
            with self.assertRaisesRegex(ValueError, "full BIN content changed"):
                capture_twice(
                    *self.args, expected_digest_file=reference, start=True,
                )
        return launched, chain, paired, full_hash

    def test_first_emulator_modifies_unprobed_bin_byte_blocks_second(self):
        launched, audited, paired, hashed = self._run_private_source_change("first")
        self.assertEqual(launched.call_count, 1)
        audited.assert_not_called()
        paired.assert_not_called()
        self.assertEqual(hashed.call_count, 1)
        self.assertFalse((self.workspace / RUN_NAMES[1]).exists())

    def test_second_emulator_modifies_unprobed_bin_byte_blocks_pair_audit(self):
        launched, audited, paired, hashed = self._run_private_source_change("second")
        self.assertEqual(launched.call_count, 2)
        self.assertEqual(audited.call_count, 1)
        paired.assert_not_called()
        self.assertEqual(hashed.call_count, 2)

    def test_final_png_audit_modifies_bin_byte_blocks_success_report(self):
        launched, audited, paired, hashed = self._run_private_source_change("final")
        self.assertEqual(launched.call_count, 2)
        self.assertEqual(audited.call_count, 2)
        paired.assert_called_once()
        self.assertEqual(hashed.call_count, 3)

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
        self.assertEqual(report["full_bin_postprocess_checks_performed"], 2)
        self.assertTrue(report["full_bin_final_postaudit_check_performed"])
        self.assertTrue(report["on_disk_full_bin_matched_private_reference_at_checkpoints"])
        self.assertFalse(report["emulator_mounted_disc_identity_authenticated"])

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
