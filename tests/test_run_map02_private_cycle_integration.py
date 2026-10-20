"""Cross-module MAP02 coordinator integration with real SYNTHETIC evidence.

Only strict readiness, unavailable original PC child, and original-file
identity checks are mocked. Actual finalization and sealing use test assets.
Finalization, CD/GPU/RGB24/PNG matching, final seal and re-verification
execute their real production verifiers against generated synthetic files.
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from tests.test_finalize_map02_private_capture import (
    PrivatePostcaptureCompletionTests,
)
from tools.publish_map02_cd_bound_witness import MANIFEST
from tools.export_map02_native_vram_preview import PNG_NAME
from tools.seal_map02_private_finalization import NAME as SEAL
from tools.run_map02_private_cycle_session import execute_private_map02_cycle


class PrivateOneShotIntegratedEvidenceTests(unittest.TestCase):
    def setUp(self):
        synthetic = PrivatePostcaptureCompletionTests(
            methodName="test_existing_artifacts_read_only_and_no_game_bytes")
        synthetic.setUp()
        self.addCleanup(synthetic.doCleanups)
        self.synthetic = synthetic
        f = synthetic.fixture
        self.seal = Path(f.tmp.name) / "one-shot-integrated-seal"
        self.seal.mkdir(mode=0o700)
        self.paths = (
            synthetic.source, f.base.fixture.root, f.scoped, f.handoff,
            f.base.cycle, synthetic.preview, synthetic.rgb, self.seal)
        self.owned = Path("/not-an-original-disc-image")
        self.upstream = Path("/no-retail-pc-checkout")
        self.binary = Path("/not-a-real-pc-elf")
        self.build_receipt = Path("/no-private-build-receipt")
        self.build_bundle = Path("/no-original-source-overlay")
        # This suite exercises real post-process CD/GPU/RGB24 finalization
        # with synthetic evidence, but has no retail ELF/disc/receipt.
        # Source-bound file/inode checks are exercised with real disposable
        # files in test_check_map02_private_cycle_readiness; keep them
        # synthetic here instead of opening nonexistent original inputs.
        self.file_identity = patch(
            "tools.run_map02_private_cycle_session._private_input_identity",
            return_value=(1, 21, 22, 0o100600, 1, 256, 3, 4))
        self.file_identity.start()
        self.addCleanup(self.file_identity.stop)
        self.receipt_dir_identity = patch(
            "tools.run_map02_private_cycle_session._receipt_directory_identity",
            return_value=(1, 33, 22, 0o40700, 3, 4))
        self.receipt_dir_identity.start()
        self.addCleanup(self.receipt_dir_identity.stop)
        self.preflight = patch(
            "tools.run_map02_private_cycle_session.verify_private_cycle_readiness",
            return_value={
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
            })
        self.preflight_mock = self.preflight.start()
        self.addCleanup(self.preflight.stop)
        # Existing real synthetic evidence is intentionally populated:
        # this integration checks finalization, not the empty prelaunch
        # filesystem gate (covered independently by the unit suite).
        self.layout = patch(
            "tools.run_map02_private_cycle_session.inspect_private_launch_layout",
            return_value={
                "schema": "vh.map02.prelaunch-directory-layout.v1",
                "prelaunch_layout_ready": True,
                "private_directory_roles_checked": 7,
                "capture_output_directories_empty": 5,
                "single_private_handoff_plan_present": True,
                "original_pc_elf_verified": False,
                "original_game_image_verified": False,
                "original_gameplay_executed": False,
                "map02_frame_authenticated": False,
                "private_game_bytes_read": False})
        self.layout_mock = self.layout.start()
        self.addCleanup(self.layout.stop)
        self.plan_read = patch(
            "tools.run_map02_private_cycle_session.private_file",
            return_value=(b'{"synthetic":"plan"}\n',
                          (1, 111, 222, 0o100600, 1, 21, 33, 44)))
        self.plan_read_mock = self.plan_read.start()
        self.addCleanup(self.plan_read.stop)
        self.parse_plan = patch(
            "tools.run_map02_private_cycle_session._validate_plan",
            return_value={"target_gpu_draw_frame": 7})
        self.parse_plan_mock = self.parse_plan.start()
        self.addCleanup(self.parse_plan.stop)
        self.launch = patch(
            "tools.run_map02_private_cycle_session.launch_observed_pc",
            return_value={
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True})
        self.launch_mock = self.launch.start()
        self.addCleanup(self.launch.stop)

    def run_cycle(self):
        return execute_private_map02_cycle(
            *self.paths, self.owned, self.upstream, self.binary,
            self.build_receipt, self.build_bundle,
            frame=7, x=0, y=0, allow_local_completion=True)

    def assert_real_seal(self, report):
        seal_file = self.seal / SEAL
        self.assertEqual({x.name for x in self.seal.iterdir()}, {SEAL})
        self.assertEqual(seal_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            report["private_final_seal_sha256"],
            hashlib.sha256(seal_file.read_bytes()).hexdigest())
        payload = json.loads(seal_file.read_bytes())
        self.assertEqual(payload["gpu_draw_frame"], 7)
        self.assertTrue(payload["independent_postcapture_recheck_completed"])
        self.assertFalse(payload["original_map02_rendering_proven"])
        self.assertFalse(report["original_map02_rendering_proven"])
        self.assertFalse(report["private_game_files_uploaded"])
        self.assertNotIn(self.synthetic.fixture.token, json.dumps(report))
        self.assertNotIn(str(self.paths[0]), json.dumps(report))

    def test_real_finalizer_seal_and_recheck_after_simulated_private_child(self):
        # Real synthetic CD + PNG and OS/cycle/RGB24 receipts, not fake
        # return values from the production finalizer and seal functions.
        report = self.run_cycle()
        self.assert_real_seal(report)
        self.launch_mock.assert_called_once()
        self.assertTrue(self.launch_mock.call_args.kwargs[
            "require_complete_preflight"])
        self.assertTrue(self.launch_mock.call_args.kwargs[
            "stop_after_present"])
        self.preflight_mock.assert_called_once()

    def test_missing_png_is_rebuilt_locally_then_cryptographically_sealed(self):
        preview = self.synthetic.preview / PNG_NAME
        preview.unlink()
        report = self.run_cycle()
        self.assertTrue(preview.exists())
        self.assertEqual(preview.stat().st_mode & 0o777, 0o600)
        self.assert_real_seal(report)

    def test_corrupt_existing_png_after_process_blocks_seal(self):
        preview = self.synthetic.preview / PNG_NAME
        original = preview.read_bytes()

        def replace_pixels(*args, **kwargs):
            preview.write_bytes(b"invalid synthetic png pixels")
            return {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True,
            }

        self.launch_mock.side_effect = replace_pixels
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertNotEqual(preview.read_bytes(), original)
        self.assertFalse(list(self.seal.iterdir()))

    def test_modified_rgb24_after_simulated_child_blocks_any_seal(self):
        rgb_path = self.synthetic.fixture.fixture.rgbfile
        original = rgb_path.read_bytes()
        def tamper(*args, **kwargs):
            rgb_path.write_bytes(b"invalid synthetic rgb24")
            return {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True,
            }
        self.launch_mock.side_effect = tamper
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertNotEqual(rgb_path.read_bytes(), original)
        self.assertFalse(list(self.seal.iterdir()))

    def test_inconsistent_original_cd_witness_after_child_blocks_seal(self):
        receipt = self.synthetic.source / MANIFEST
        original = receipt.read_bytes()
        def tamper(*args, **kwargs):
            receipt.write_bytes(b"corrupt synthetic original-CD receipt")
            return {
                "kernel_executable_hash_matched": True,
                "same_process_gpu_scoped_nonce_checked": True,
                "pc_preoverlay_capture_session_bound": True,
            }
        self.launch_mock.side_effect = tamper
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertNotEqual(receipt.read_bytes(), original)
        self.assertFalse(list(self.seal.iterdir()))


if __name__ == "__main__":
    unittest.main()
