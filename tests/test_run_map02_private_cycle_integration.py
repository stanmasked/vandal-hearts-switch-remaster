"""Cross-module MAP02 coordinator integration with real SYNTHETIC evidence.

Only strict readiness and the unavailable original PC child are mocked.
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
        self.preflight = patch(
            "tools.run_map02_private_cycle_session.verify_private_cycle_readiness",
            return_value={"ready_for_controlled_local_launch": True})
        self.preflight_mock = self.preflight.start()
        self.addCleanup(self.preflight.stop)
        self.plan_read = patch(
            "tools.run_map02_private_cycle_session.private_file",
            return_value=b'{"synthetic":"plan"}\n')
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
