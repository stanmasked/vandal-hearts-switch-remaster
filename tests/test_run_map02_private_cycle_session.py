"""Synthetic one-shot MAP02 execution sequencing; never launch owned game."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import tools.run_map02_private_cycle_session as runner


class PrivateOneShotCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vh-map02-one-shot-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roles = ("source", "native", "scoped", "handoff",
                      "cycle", "preview", "rgb", "seal")
        self.folders = [self.root / name for name in self.roles]
        for folder in self.folders:
            folder.mkdir(mode=0o700)
        self.disc = self.root / "owned-synthetic-disc"
        self.upstream = self.root / "pinned-synthetic-source"
        self.elf = self.root / "synthetic-elf"
        self.receipt = self.root / "synthetic-build-receipt"
        self.bundle = self.root / "synthetic-build-bundle"
        self.plan = b'{"test":"only synthetic input"}\n'
        self.plan_identity = (1, 11, 22, 0o100600, 1, len(self.plan), 3, 4)
        self.mocks = {}
        self.ready_report = {
            "schema": "vh.map02.private-pc-cycle-readiness.v1",
            "private_directories_checked": 7,
            "capture_folders_empty": 5,
            "source_bound_plan_checked": True,
            "original_pc_source_identity_checked": True,
            "complete_pc_elf_symbols_checked": True,
            "complete_pc_elf_bytes_checked": True,
            "private_original_image_bytes_checked": True,
            "pinned_full_elf_build_receipt_checked": True,
            "prelaunch_inputs_stable_across_checks": True,
            "ready_for_controlled_local_launch": True,
            "gameplay_process_started": False,
            "original_map02_rendering_proven": False,
            "hardware_ps1_equivalence_proven": False,
            "game_content_emitted": False,
        }
        simulated = {
            "private_file": (self.plan, self.plan_identity),
            "_validate_plan": {"target_gpu_draw_frame": 12},
            "verify_private_cycle_readiness": self.ready_report,
            "launch_observed_pc": {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True},
            "finalize_private_capture": {
                "independently_verified_cd_gpu_process_and_rgb24_png": True,
                "gpu_draw_frame": 12,
                "original_map02_rendering_proven": False},
            "seal_final_capture": {
                "two_independent_readonly_final_audits": True,
                "postpublication_independent_verification_completed": True,
                "gpu_draw_frame": 12,
                "private_final_seal_sha256": "a" * 64},
            "verify_final_seal": {
                "sealed_evidence_independently_reverified": True,
                "gpu_draw_frame": 12,
                "private_final_seal_sha256": "a" * 64,
                "original_map02_rendering_proven": False},
        }
        for name, result in simulated.items():
            handle = patch.object(runner, name, return_value=result)
            self.mocks[name] = handle.start()
            self.addCleanup(handle.stop)

    def execute(self, **kwargs):
        options = dict(frame=12, x=10, y=20,
                       allow_local_completion=True)
        options.update(kwargs)
        return runner.execute_private_map02_cycle(
            *self.folders, self.disc, self.upstream, self.elf,
            self.receipt, self.bundle, **options)

    def test_full_one_shot_order_and_only_non_game_report(self):
        order = []
        for name in ("verify_private_cycle_readiness",
                     "launch_observed_pc", "finalize_private_capture",
                     "seal_final_capture", "verify_final_seal"):
            original = self.mocks[name].return_value
            self.mocks[name].side_effect = lambda *a, _name=name, _r=original, **kw: (
                order.append(_name) or _r)
        result = self.execute()
        self.assertEqual(order, [
            "verify_private_cycle_readiness", "launch_observed_pc",
            "finalize_private_capture", "seal_final_capture",
            "verify_final_seal"])
        self.assertEqual(result["gpu_draw_frame"], 12)
        self.assertEqual(result["private_final_seal_sha256"], "a" * 64)
        self.assertTrue(result["private_completion_seal_independently_reverified"])
        self.assertFalse(result["original_map02_rendering_proven"])
        self.assertFalse(result["physical_ps1_equivalence_proven"])
        self.assertFalse(result["private_game_files_uploaded"])
        options = self.mocks["launch_observed_pc"].call_args.kwargs
        self.assertIs(options["require_complete_preflight"], True)
        self.assertIs(options["stop_after_present"], True)
        self.assertIs(self.mocks["finalize_private_capture"].call_args.kwargs[
            "complete_missing"], True)
        self.assertEqual(
            self.mocks["verify_final_seal"].call_count, 1)

    def test_stage_callback_tracks_only_fixed_public_diagnostic_stages(self):
        recorded = []
        result = self.execute(stage_callback=recorded.append)
        self.assertTrue(result["private_completion_seal_independently_reverified"])
        self.assertEqual(recorded, list(runner.SAFE_STAGES))
        self.assertNotIn(str(self.elf), repr(recorded))
        self.assertNotIn(str(self.disc), repr(recorded))

    def test_cli_failed_stages_do_not_disclose_original_paths_or_exceptions(self):
        private = "/private/owned-original/SLUS_004.47"
        args = ["private-one-shot"] + [str(x) for x in self.folders] + [
            str(self.disc), "--upstream-checkout", str(self.upstream),
            "--pc-binary", str(self.elf), "--build-receipt-dir",
            str(self.receipt), "--build-bundle-dir", str(self.bundle),
            "--frame", "12", "--x", "10", "--y", "20",
            "--allow-local-completion"]
        for function, phase in (
            ("verify_private_cycle_readiness", "full-preflight"),
            ("launch_observed_pc", "observed-process"),
            ("finalize_private_capture", "capture-finalization"),
            ("seal_final_capture", "seal-publication"),
            ("verify_final_seal", "seal-verification"),
        ):
            with self.subTest(phase=phase):
                stderr = io.StringIO()
                original = self.mocks[function].side_effect
                self.mocks[function].side_effect = ValueError(
                    "private source unavailable: " + private)
                try:
                    with patch("sys.argv", args), redirect_stderr(stderr):
                        with self.assertRaises(SystemExit) as exit_result:
                            runner.main()
                    self.assertEqual(exit_result.exception.code, 2)
                    self.assertIn("stage=" + phase, stderr.getvalue())
                    self.assertIn("one-shot execution/finalization unavailable",
                                  stderr.getvalue())
                    self.assertNotIn(private, stderr.getvalue())
                    self.assertNotIn(str(self.elf), stderr.getvalue())
                finally:
                    self.mocks[function].side_effect = original

    def test_dry_run_reuses_private_readiness_but_never_starts_game(self):
        milestones = []
        status = self.execute(
            dry_run=True, allow_local_completion=False,
            stage_callback=milestones.append)
        self.assertEqual(status["schema"], "vh.map02.private-one-shot-dry-run.v1")
        self.assertEqual(status["gpu_draw_frame"], 12)
        self.assertTrue(status["ready_for_controlled_local_launch"])
        self.assertTrue(status["full_private_original_elf_disc_preflight_checked"])
        for key in ("gameplay_process_started", "private_witnesses_written",
                    "private_final_seal_published",
                    "original_map02_rendering_proven",
                    "physical_ps1_equivalence_proven",
                    "private_game_files_uploaded"):
            self.assertFalse(status[key])
        self.assertEqual(milestones, list(runner.SAFE_STAGES[:4]) + ["complete"])
        self.mocks["verify_private_cycle_readiness"].assert_called_once()
        self.assertEqual(self.mocks["private_file"].call_count, 2)
        for name in ("launch_observed_pc", "finalize_private_capture",
                     "seal_final_capture", "verify_final_seal"):
            self.mocks[name].assert_not_called()
        self.assertFalse(list(self.folders[-1].iterdir()))

    def test_dry_run_is_fail_closed_when_private_plan_or_seal_is_wrong(self):
        with self.assertRaisesRegex(ValueError, "requested frame differs"):
            self.execute(frame=13, dry_run=True, allow_local_completion=False)
        self.mocks["verify_private_cycle_readiness"].return_value = {
            "ready_for_controlled_local_launch": False}
        with self.assertRaisesRegex(ValueError, "preflight was not confirmed"):
            self.execute(dry_run=True, allow_local_completion=False)
        self.mocks["verify_private_cycle_readiness"].return_value = {
            "ready_for_controlled_local_launch": True}
        extra = self.folders[-1] / "unexpected"
        extra.write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            self.execute(dry_run=True, allow_local_completion=False)
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_dry_run_rejects_byte_identical_capture_folder_replacement(self):
        # A new, empty 0700 folder is not the same private session root.
        source = self.folders[0]
        archived = self.root / "old-source-capture"

        def replace_folder(*args, **kwargs):
            source.rename(archived)
            source.mkdir(mode=0o700)
            return self.ready_report

        self.mocks["verify_private_cycle_readiness"].side_effect = replace_folder
        with self.assertRaisesRegex(ValueError, "capture folders changed"):
            self.execute(dry_run=True, allow_local_completion=False)
        self.assertTrue(archived.is_dir())
        for name in ("launch_observed_pc", "finalize_private_capture",
                     "seal_final_capture", "verify_final_seal"):
            self.mocks[name].assert_not_called()
        self.assertFalse(list(self.folders[-1].iterdir()))

    def test_dry_run_rejects_new_capture_output_during_preflight(self):
        native = self.folders[1]

        def inject_output(*args, **kwargs):
            (native / "unexpected-synthetic-output").write_bytes(b"synthetic")
            return self.ready_report

        self.mocks["verify_private_cycle_readiness"].side_effect = inject_output
        with self.assertRaisesRegex(ValueError, "capture folders changed"):
            self.execute(dry_run=True, allow_local_completion=False)
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_real_one_shot_rejects_folder_swap_before_child_process(self):
        handoff = self.folders[3]
        archived = self.root / "old-handoff"

        def replace_handoff(*args, **kwargs):
            handoff.rename(archived)
            handoff.mkdir(mode=0o700)
            return self.ready_report

        self.mocks["verify_private_cycle_readiness"].side_effect = replace_handoff
        with self.assertRaisesRegex(ValueError, "capture folders changed"):
            self.execute()
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["finalize_private_capture"].assert_not_called()

    def test_readiness_contract_rejects_forged_or_partial_reports(self):
        # A single ready=True field must never become process authorization.
        cases = (
            {"ready_for_controlled_local_launch": True},
            {**self.ready_report, "schema": "foreign-schema"},
            {**self.ready_report, "private_directories_checked": True},
            {**self.ready_report, "capture_folders_empty": 4},
            {**self.ready_report, "complete_pc_elf_bytes_checked": False},
            {**self.ready_report, "prelaunch_inputs_stable_across_checks": None},
            {**self.ready_report, "gameplay_process_started": True},
            {**self.ready_report, "game_content_emitted": True},
            {**self.ready_report, "original_map02_rendering_proven": True},
            {**self.ready_report, "hardware_ps1_equivalence_proven": True},
        )
        for report in cases:
            with self.subTest(report=report):
                self.mocks["verify_private_cycle_readiness"].return_value = report
                with self.assertRaisesRegex(ValueError, "report contract mismatch"):
                    self.execute(dry_run=True, allow_local_completion=False)
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()
        self.assertFalse(list(self.folders[-1].iterdir()))

    def test_dry_run_and_publish_permission_mutually_exclusive(self):
        with self.assertRaisesRegex(ValueError, "forbids local completion"):
            self.execute(dry_run=True)
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            self.execute(dry_run="true", allow_local_completion=False)
        self.mocks["verify_private_cycle_readiness"].assert_not_called()
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_dry_run_cli_emits_only_safe_status_not_game_paths(self):
        args = ["private-one-shot"] + [str(x) for x in self.folders] + [
            str(self.disc), "--upstream-checkout", str(self.upstream),
            "--pc-binary", str(self.elf), "--build-receipt-dir",
            str(self.receipt), "--build-bundle-dir", str(self.bundle),
            "--frame", "12", "--x", "10", "--y", "20", "--dry-run"]
        output = io.StringIO()
        with patch("sys.argv", args), redirect_stdout(output):
            runner.main()
        result = json.loads(output.getvalue())
        self.assertTrue(result["ready_for_controlled_local_launch"])
        self.assertFalse(result["gameplay_process_started"])
        self.assertNotIn(str(self.disc), output.getvalue())
        self.assertNotIn(str(self.elf), output.getvalue())
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_local_completion_requires_explicit_consent_before_process(self):
        with self.assertRaisesRegex(ValueError, "explicit private"):
            self.execute(allow_local_completion=False)
        self.mocks["verify_private_cycle_readiness"].assert_not_called()
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_wrong_frame_and_invalid_sample_fail_before_game_process(self):
        for option, expected in (
            ({"frame": 13}, "requested frame differs"),
            ({"x": -1}, "pixel X"),
            ({"y": 512}, "pixel Y"),
            ({"timeout": 0}, "timeout"),
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(ValueError, expected):
                    self.execute(**option)
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_refuse_overlapping_and_dirty_seal_directory_before_launch(self):
        dirty = self.folders[-1] / "previous-run.jsonl"
        dirty.write_bytes(b"synthetic")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            self.execute()
        dirty.unlink()
        with self.assertRaisesRegex(ValueError, "separate"):
            runner.execute_private_map02_cycle(
                *self.folders[:-1], self.folders[0],
                self.disc, self.upstream, self.elf, self.receipt,
                self.bundle, frame=12, x=10, y=20,
                allow_local_completion=True)
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_refuse_changed_plan_between_preflight_and_spawn(self):
        self.mocks["private_file"].side_effect = [
            (self.plan, self.plan_identity),
            (b'{"changed":"plan"}\n', self.plan_identity)]
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.execute()
        self.mocks["launch_observed_pc"].assert_not_called()

    def test_identical_bytes_plan_replacement_inode_rejected(self):
        replaced = tuple(
            999 if index == 1 else value
            for index, value in enumerate(self.plan_identity))
        self.mocks["private_file"].side_effect = [
            (self.plan, self.plan_identity), (self.plan, replaced)]
        with self.assertRaisesRegex(ValueError, "plan changed"):
            self.execute()
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["finalize_private_capture"].assert_not_called()

    def test_seal_directory_swap_during_process_rejected(self):
        original = self.folders[-1]
        archived = self.root / "old-seal-directory"

        def swap_instead_of_private_child(*args, **kwargs):
            original.rename(archived)
            original.mkdir(mode=0o700)
            return {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True,
            }

        self.mocks["launch_observed_pc"].side_effect = swap_instead_of_private_child
        with self.assertRaisesRegex(ValueError, "seal directory changed"):
            self.execute()
        self.assertTrue(archived.is_dir())
        self.mocks["finalize_private_capture"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_seal_directory_populated_during_process_rejected(self):
        original = self.folders[-1]

        def create_rogue_output(*args, **kwargs):
            (original / "unrelated-private-run").write_bytes(b"synthetic")
            return {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True,
            }

        self.mocks["launch_observed_pc"].side_effect = create_rogue_output
        with self.assertRaisesRegex(ValueError, "unexpectedly populated"):
            self.execute()
        self.mocks["finalize_private_capture"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_negative_readiness_prohibits_process_and_artifact_publication(self):
        self.mocks["verify_private_cycle_readiness"].return_value = {
            "ready_for_controlled_local_launch": False}
        with self.assertRaisesRegex(ValueError, "not confirmed"):
            self.execute()
        self.mocks["launch_observed_pc"].assert_not_called()
        self.mocks["finalize_private_capture"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_failed_process_never_finalizes_or_seals(self):
        self.mocks["launch_observed_pc"].side_effect = ValueError(
            "synthetic CD/GPU did not complete")
        with self.assertRaisesRegex(ValueError, "did not complete"):
            self.execute()
        self.mocks["finalize_private_capture"].assert_not_called()
        self.mocks["seal_final_capture"].assert_not_called()

    def test_failed_finalizer_never_seals_and_failed_seal_not_reported(self):
        self.mocks["finalize_private_capture"].return_value = {
            "independently_verified_cd_gpu_process_and_rgb24_png": False,
            "gpu_draw_frame": 12,
            "original_map02_rendering_proven": False}
        with self.assertRaisesRegex(ValueError, "not verified"):
            self.execute()
        self.mocks["seal_final_capture"].assert_not_called()
        self.mocks["finalize_private_capture"].return_value = {
            "independently_verified_cd_gpu_process_and_rgb24_png": True,
            "gpu_draw_frame": 12,
            "original_map02_rendering_proven": False}
        self.mocks["seal_final_capture"].side_effect = ValueError(
            "synthetic sealed evidence inconsistent")
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            self.execute()
        self.mocks["verify_final_seal"].assert_not_called()

    def test_final_receipt_mismatch_fails_closed(self):
        self.mocks["verify_final_seal"].return_value = {
            "sealed_evidence_independently_reverified": True,
            "gpu_draw_frame": 12,
            "private_final_seal_sha256": "f" * 64,
            "original_map02_rendering_proven": False}
        with self.assertRaisesRegex(ValueError, "seal changed"):
            self.execute()

    def test_cli_does_not_show_private_file_error(self):
        private_path = "/private/owned-MAP02/SLUS_004.47"
        args = ["private-one-shot"] + [str(x) for x in self.folders] + [
            str(self.disc), "--upstream-checkout", str(self.upstream),
            "--pc-binary", str(self.elf), "--build-receipt-dir",
            str(self.receipt), "--build-bundle-dir", str(self.bundle),
            "--frame", "12", "--x", "10", "--y", "20",
            "--allow-local-completion"]
        for failure in (OSError(private_path), ValueError(private_path),
                        subprocess.TimeoutExpired([private_path], 2)):
            with self.subTest(kind=type(failure).__name__):
                errors = io.StringIO()
                with (patch("sys.argv", args),
                      patch.object(runner, "execute_private_map02_cycle",
                                   side_effect=failure),
                      redirect_stderr(errors)):
                    with self.assertRaises(SystemExit) as raised:
                        runner.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("one-shot execution/finalization unavailable",
                              errors.getvalue())
                self.assertNotIn(private_path, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
